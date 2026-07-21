"""Safety business workflows."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    ScheduledTask,
    ScheduledTaskLog,
)
from app.modules.safety.repository import SafetyRepository
from app.modules.safety.schemas import (
    CardPreviewRequest,
    ScheduledTaskCreate,
    ScheduledTaskUpdate,
)

logger = logging.getLogger(__name__)


class ScheduledTaskService:
    """Scheduled task business logic — CRUD, preview, manual trigger."""

    def __init__(self, session: AsyncSession):
        self.repo = SafetyRepository(session)
        self.session = session

    async def get_tasks(
        self,
        skip: int = 0,
        limit: int = 20,
        is_enabled: bool | None = None,
        search: str | None = None,
    ) -> tuple[list[ScheduledTask], int]:
        return await self.repo.get_scheduled_tasks(skip, limit, is_enabled, search)

    async def get_task(self, task_id: uuid.UUID) -> ScheduledTask | None:
        return await self.repo.get_scheduled_task_by_id(task_id)

    async def create_task(self, data: ScheduledTaskCreate) -> ScheduledTask:
        from app.modules.safety.card_builder import build_default_template
        from app.modules.safety.scheduler import compute_next_run

        task_data = data.model_dump()
        # Auto-generate default template if not provided
        if not task_data.get("card_template") and task_data.get("data_sources"):
            task_data["card_template"] = build_default_template(task_data["data_sources"])
        # Compute initial next_run_at
        if task_data.get("is_enabled", True):
            task_data["next_run_at"] = compute_next_run(task_data["cron_expression"])
        return await self.repo.create_scheduled_task(task_data)

    async def update_task(self, task_id: uuid.UUID, data: ScheduledTaskUpdate) -> ScheduledTask | None:
        from app.modules.safety.scheduler import compute_next_run

        update_data = data.model_dump(exclude_unset=True)
        # Recompute next_run_at if cron or enabled changed
        if "cron_expression" in update_data or "is_enabled" in update_data:
            task = await self.repo.get_scheduled_task_by_id(task_id)
            if task and task.is_enabled:
                cron = update_data.get("cron_expression", task.cron_expression)
                update_data["next_run_at"] = compute_next_run(cron)
        return await self.repo.update_scheduled_task(task_id, update_data)

    async def delete_task(self, task_id: uuid.UUID) -> bool:
        return await self.repo.delete_scheduled_task(task_id)

    async def toggle_task(self, task_id: uuid.UUID, enabled: bool) -> ScheduledTask | None:
        from app.modules.safety.scheduler import compute_next_run

        task = await self.repo.get_scheduled_task_by_id(task_id)
        if not task:
            return None
        update_data = {"is_enabled": enabled}
        if enabled:
            update_data["next_run_at"] = compute_next_run(task.cron_expression)
        else:
            update_data["next_run_at"] = None
        return await self.repo.update_scheduled_task(task_id, update_data)

    async def run_task_now(self, task_id: uuid.UUID) -> ScheduledTaskLog | None:
        """Manually trigger a task execution."""
        from app.modules.safety.scheduler import execute_single_task

        task = await self.repo.get_scheduled_task_by_id(task_id)
        if not task:
            return None
        await execute_single_task(task, self.repo)
        await self.session.flush()
        # Return the most recent log
        logs, _ = await self.repo.get_task_logs(task_id, skip=0, limit=1)
        return logs[0] if logs else None

    async def get_logs(
        self, task_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> tuple[list[ScheduledTaskLog], int]:
        return await self.repo.get_task_logs(task_id, skip, limit)

    @staticmethod
    def get_data_source_options() -> list[dict]:
        from app.modules.safety.card_builder import DATA_SOURCE_DEFINITIONS
        return DATA_SOURCE_DEFINITIONS

    @staticmethod
    async def preview_card(data: CardPreviewRequest) -> dict:
        from datetime import datetime as dt

        from app.modules.safety.card_builder import (
            build_card_json,
            build_default_template,
            render_template,
        )

        enabled_keys = [ds.key for ds in data.data_sources if ds.enabled]
        # Build mock variables
        variables: dict[str, str] = {}
        for ds in data.data_sources:
            variables[ds.key] = f"<{ds.label}>"
        variables["runtime.timestamp"] = dt.now().strftime("%Y-%m-%d %H:%M")

        template = data.card_template
        if not template:
            template = build_default_template(
                [ds.model_dump() for ds in data.data_sources]
            )

        rendered = render_template(template, variables)
        card_json = await build_card_json(
            title="预览",
            rendered_markdown=rendered,
            header_color=data.header_color.value if hasattr(data.header_color, 'value') else data.header_color,
        )

        return {
            "card_json": card_json,
            "markdown_preview": rendered,
            "variables": variables,
        }
