"""Energy-owned bot configuration and durable, bounded message delivery."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.secrets import decrypt_secret, encrypt_secret
from app.modules.energy.ledger_models import (
    EnergyBotConfig,
    EnergyEntryPlan,
    EnergyEntryTask,
    EnergyLedgerRevision,
    EnergyNotificationRun,
    EnergyReading,
)
from app.modules.energy.ledger_schemas import BotDefinition, BotResponse, BotWrite
from app.platform.identity.public_api import notification_recipient_for_user
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.im import (
    build_simple_card_content,
    send_feishu_message,
    update_feishu_message,
)


async def bot_config(db: AsyncSession) -> EnergyBotConfig | None:
    result = await db.scalars(
        select(EnergyBotConfig).where(EnergyBotConfig.name == "default")
    )
    return result.one_or_none()


async def read_bot(db: AsyncSession) -> BotResponse:
    config = await bot_config(db)
    version = (
        await db.scalar(
            select(EnergyLedgerRevision.version)
            .where(
                EnergyLedgerRevision.entity_kind == "bot",
                EnergyLedgerRevision.entity_id == config.id,
            )
            .order_by(EnergyLedgerRevision.version.desc())
            .limit(1)
        )
        if config
        else None
    )
    return BotResponse(
        definition=BotDefinition.model_validate(config.definition)
        if config
        else BotDefinition(),
        secret_configured=bool(config and config.encrypted_secret),
        version=version or 0,
    )


async def save_bot(
    db: AsyncSession, payload: BotWrite, actor_id: UUID | None
) -> BotResponse:
    config = await bot_config(db) or EnergyBotConfig(
        id=uuid4(), name="default", created_by=actor_id
    )
    current = await read_bot(db)
    if current.version != payload.version:
        raise AppException(409, "机器人配置已被修改，请重新载入后保存")
    if (
        current.definition.app_id
        and current.definition.app_id != payload.definition.app_id
        and not payload.app_secret
    ):
        raise AppException(422, "变更应用时必须填写新应用的密钥")
    if payload.app_secret:
        config.encrypted_secret = encrypt_secret(payload.app_secret)
    if payload.definition.enabled and not config.encrypted_secret:
        raise AppException(422, "请先配置机器人应用密钥")
    config.definition = payload.definition.model_dump(mode="json")
    config.updated_by = actor_id
    db.add(config)
    db.add(
        EnergyLedgerRevision(
            id=uuid4(),
            entity_kind="bot",
            entity_id=config.id,
            version=current.version + 1,
            payload={
                "definition": payload.definition.model_dump(mode="json"),
                "secret_configured": bool(config.encrypted_secret),
            },
            reason="更新机器人配置",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    await db.flush()
    return await read_bot(db)


async def enqueue_task_notifications(
    db: AsyncSession, task: EnergyEntryTask, kind: str
) -> None:
    config = await bot_config(db)
    if config is None or not BotDefinition.model_validate(config.definition).enabled:
        return
    plan = await db.get(EnergyEntryPlan, task.plan_id)
    if plan is None or not plan.definition.get("enabled"):
        return
    owners = plan.definition.get("owner_ids", []) if plan else []
    targets = (
        [(str(owner), "user") for owner in owners] if isinstance(owners, list) else []
    )
    chat = task.definition.get("group_chat_id")
    if chat:
        targets.append((str(chat), "chat"))
    for target, target_type in targets:
        key = f"{task.id}:{kind}:{target_type}:{target}"
        existing = await db.scalar(
            select(EnergyNotificationRun.id).where(
                EnergyNotificationRun.delivery_key == key
            )
        )
        if existing is None:
            db.add(
                EnergyNotificationRun(
                    id=uuid4(),
                    task_id=task.id,
                    delivery_key=key,
                    definition={
                        "kind": kind,
                        "target": target,
                        "target_type": target_type,
                    },
                    attempts=0,
                    status="pending",
                )
            )
    await db.flush()


async def deliver_notifications(db: AsyncSession, now: datetime) -> None:
    config = await bot_config(db)
    if config is None or not BotDefinition.model_validate(config.definition).enabled:
        return
    definition = BotDefinition.model_validate(config.definition)
    rows = (
        await db.scalars(
            select(EnergyNotificationRun)
            .where(
                EnergyNotificationRun.status.in_(["pending", "retry", "sending"]),
                EnergyNotificationRun.attempts < 3,
                (
                    EnergyNotificationRun.next_attempt_at.is_(None)
                    | (EnergyNotificationRun.next_attempt_at <= now)
                ),
            )
            .order_by(EnergyNotificationRun.created_at)
            .limit(30)
            .with_for_update(skip_locked=True)
        )
    ).all()
    for run in rows:
        task = await db.get(EnergyEntryTask, run.task_id)
        if task is None:
            run.status, run.error = "failed", "任务不存在"
            continue
        current_plan = await db.get(EnergyEntryPlan, task.plan_id)
        if current_plan is None or not current_plan.definition.get("enabled"):
            run.status = "skipped"
            continue
        readings = list(
            (
                await db.scalars(
                    select(EnergyReading).where(EnergyReading.task_id == task.id)
                )
            ).all()
        )
        completed = sum(item.value is not None for item in readings)
        kind = str(run.definition["kind"])
        if kind == "reminder" and completed == len(readings):
            run.status = "skipped"
            continue
        target = str(run.definition["target"])
        if run.definition["target_type"] == "user":
            plan = await db.get(EnergyEntryPlan, task.plan_id)
            if plan is None or not plan.definition.get("enabled"):
                run.status = "skipped"
                continue
            current_owners = plan.definition.get("owner_ids") if plan else None
            if not isinstance(current_owners, list) or target not in current_owners:
                run.status = "skipped"
                continue
            recipient = await notification_recipient_for_user(db, UUID(target))
        else:
            recipient = (target, "chat_id")
        if recipient is None:
            run.status, run.error = (
                "failed",
                "责任人缺少可用于当前应用的企业身份，请联系管理员完善人员映射",
            )
            continue
        run.attempts += 1
        run.status = "sending"
        run.next_attempt_at = now + timedelta(minutes=5)
        await db.flush()
        title = "能源填报提醒" if kind == "reminder" else "能源填报清单"
        content = build_simple_card_content(
            title=title,
            markdown=(
                f"**{task.definition['name']}**\n抄表日期：{task.task_date}\n"
                f"电量归属：{task.task_date - timedelta(days=1)}\n"
                f"完成：{completed}/{len(readings)}\n"
                f"截止：{task.definition['deadline_time']}（上海时间）"
            ),
            button_text="查看清单" if completed == len(readings) else "填写清单",
            button_url=f"{definition.base_url.rstrip('/')}/energy/entry?task={task.id}&source=feishu",
        )
        try:
            token = await FeishuAuth.get_tenant_access_token(
                definition.app_id, decrypt_secret(config.encrypted_secret or "")
            )
            initial_key = f"{task.id}:initial:{run.definition['target_type']}:{target}"
            initial = await db.scalar(
                select(EnergyNotificationRun).where(
                    EnergyNotificationRun.delivery_key == initial_key
                )
            )
            message_id: str | None
            if kind.startswith("progress:") and initial and initial.message_id:
                result = await update_feishu_message(
                    tenant_access_token=token,
                    message_id=initial.message_id,
                    content=content,
                )
                message_id = initial.message_id
            else:
                result = await send_feishu_message(
                    tenant_access_token=token,
                    receive_id=recipient[0],
                    receive_id_type=recipient[1],
                    msg_type="interactive",
                    content=content,
                    uuid=str(uuid5(NAMESPACE_URL, run.delivery_key)),
                )
                message_id = result.message_id
            if result.ok:
                run.status, run.message_id, run.error = "sent", message_id, None
            else:
                run.error = f"飞书消息未成功，错误码：{result.code}"
                run.status = (
                    "retry"
                    if run.attempts < 3
                    and result.code in {99991400, 99991401, 99991663}
                    else "failed"
                )
        except (httpx.HTTPError, RuntimeError, ValueError, AppException) as exc:
            run.error = "飞书网络或授权失败，请检查应用配置和连接后重试"
            transient = isinstance(exc, httpx.TransportError) or (
                isinstance(exc, httpx.HTTPStatusError)
                and (exc.response.status_code == 429 or exc.response.status_code >= 500)
            )
            run.status = "retry" if run.attempts < 3 and transient else "failed"
        run.next_attempt_at = (
            now + timedelta(minutes=2**run.attempts) if run.status == "retry" else None
        )
        await db.flush()


async def run_native_schedule(db: AsyncSession, now: datetime | None = None) -> None:
    from app.modules.energy.ledger_models import EnergyEntryPlan
    from app.modules.energy.ledger_schemas import EntryPlanDefinition
    from app.modules.energy.ledger_service import EnergyLedgerService

    local = (now or datetime.now(UTC)).astimezone(ZoneInfo("Asia/Shanghai"))
    service = EnergyLedgerService(db)
    await service.repo.serialize_write()
    plans = await service.repo.all(EnergyEntryPlan)
    days = set()
    for plan in plans:
        definition = EntryPlanDefinition.model_validate(plan.definition)
        if not definition.enabled or definition.publish_time > local.strftime("%H:%M"):
            continue
        latest = await db.scalar(
            select(EnergyEntryTask.task_date)
            .where(EnergyEntryTask.plan_id == plan.id)
            .order_by(EnergyEntryTask.task_date.desc())
            .limit(1)
        )
        begin = (
            latest
            if latest == local.date()
            else latest + timedelta(days=1)
            if latest
            else min(
                plan.created_at.astimezone(ZoneInfo("Asia/Shanghai")).date(),
                local.date(),
            )
        )
        for offset in range(min(7, (local.date() - begin).days + 1)):
            days.add(begin + timedelta(days=offset))
    for day in sorted(days):
        await service.generate_tasks(
            day,
            scheduled=True,
            publish_clock=local.strftime("%H:%M") if day == local.date() else "23:59",
        )
    tasks = (
        await db.scalars(
            select(EnergyEntryTask).where(EnergyEntryTask.task_date == local.date())
        )
    ).all()
    for task in tasks:
        if str(task.definition["reminder_time"]) <= local.strftime("%H:%M"):
            await enqueue_task_notifications(db, task, "reminder")
