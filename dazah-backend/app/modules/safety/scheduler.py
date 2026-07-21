"""Scheduled task engine — asyncio loop for cron-based task execution."""

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter

logger = logging.getLogger(__name__)

# Stop flag, set during app shutdown
stop_scheduled_task_flag = asyncio.Event()

# Tick interval in seconds
TICK_INTERVAL = 30


def compute_next_run(cron_expression: str, from_time: datetime | None = None) -> datetime:
    """Compute the next run time from a cron expression."""
    base = from_time or datetime.now(timezone.utc)
    # croniter expects naive datetime; we use local time for cron scheduling
    local_base = base.astimezone()
    cron = croniter(cron_expression, local_base.replace(tzinfo=None))
    next_run_naive = cron.get_next(datetime)
    # Return as the same timezone-aware datetime
    return next_run_naive.replace(tzinfo=local_base.tzinfo)


async def execute_single_task(task, safety_repo) -> None:
    """Execute one scheduled task: fetch data, build card, send to Feishu."""
    from app.modules.safety.card_builder import (
        build_card_json,
        fetch_data_sources,
        render_template,
    )

    task_start = datetime.now(timezone.utc)

    # Create execution log
    log_data = {
        "task_id": task.id,
        "started_at": task_start,
        "status": "running",
    }
    log = await safety_repo.create_task_log(log_data)
    log_id = log.id

    try:
        # Determine enabled data sources
        data_sources = list(task.data_sources or [])
        enabled_keys = [ds["key"] for ds in data_sources if ds.get("enabled", True)]

        # Fetch data
        aggregated = await fetch_data_sources(safety_repo, enabled_keys)

        # Build variable dict for template rendering
        variables: dict[str, str] = {}
        for ds in data_sources:
            key = ds["key"]
            if key in aggregated:
                variables[key] = aggregated[key]

        # Add runtime variables
        variables["runtime.timestamp"] = task_start.strftime("%Y-%m-%d %H:%M")

        # Render template
        template = task.card_template or ""
        rendered = render_template(template, variables)

        # Build and send card
        card_json = await build_card_json(
            title=task.name,
            rendered_markdown=rendered,
            header_color=task.header_color or "blue",
        )

        from app.modules.safety.feishu.notification import send_group_card

        result = await send_group_card(
            chat_id=task.feishu_chat_id,
            title=task.name,
            content=rendered,
            header_template=task.header_color or "blue",
        )

        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - task_start).total_seconds() * 1000)

        # Update log
        await safety_repo.update_task_log(
            log_id,
            {
                "status": "success",
                "completed_at": completed_at,
                "data_snapshot": aggregated,
                "card_content": card_json,
                "feishu_msg_id": result,
                "duration_ms": duration_ms,
            },
        )

        # Update task last_run status
        await safety_repo.update_scheduled_task(
            task.id,
            {
                "last_run_at": task_start,
                "last_run_status": "success",
                "last_error": None,
                "next_run_at": compute_next_run(task.cron_expression, completed_at),
            },
        )

        logger.info("Scheduled task '%s' executed successfully, duration=%dms", task.name, duration_ms)

    except Exception as e:
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - task_start).total_seconds() * 1000)
        error_msg = str(e)

        logger.exception("Scheduled task '%s' failed: %s", task.name, error_msg)

        # Update log with error
        try:
            await safety_repo.update_task_log(
                log_id,
                {
                    "status": "failure",
                    "completed_at": completed_at,
                    "error_message": error_msg,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:
            logger.exception("Failed to update task log for '%s'", task.name)

        # Update task status
        try:
            await safety_repo.update_scheduled_task(
                task.id,
                {
                    "last_run_at": task_start,
                    "last_run_status": "failure",
                    "last_error": error_msg,
                    "next_run_at": compute_next_run(task.cron_expression, completed_at),
                },
            )
        except Exception:
            logger.exception("Failed to update task status for '%s'", task.name)


async def scheduled_task_loop():
    """Main scheduler loop — checks for due tasks every TICK_INTERVAL seconds.

    Launched in the FastAPI lifespan, runs until stop_scheduled_task_flag is set.
    """
    from app.core.database import async_session_factory
    from app.modules.safety.repository import SafetyRepository

    logger.info("Scheduled task loop started (tick=%ds)", TICK_INTERVAL)

    while not stop_scheduled_task_flag.is_set():
        try:
            async with async_session_factory() as db:
                repo = SafetyRepository(db)

                # Get all due tasks
                due_tasks = await repo.get_due_scheduled_tasks()

                for task in due_tasks:
                    logger.info("Executing scheduled task: %s (chat=%s)", task.name, task.feishu_chat_id)
                    await execute_single_task(task, repo)

                await db.commit()

        except Exception:
            logger.exception("Scheduled task loop iteration error")

        # Wait for next tick or stop signal
        try:
            await asyncio.wait_for(stop_scheduled_task_flag.wait(), timeout=TICK_INTERVAL)
        except asyncio.TimeoutError:
            pass  # Normal tick timeout, loop continues

    logger.info("Scheduled task loop stopped")
