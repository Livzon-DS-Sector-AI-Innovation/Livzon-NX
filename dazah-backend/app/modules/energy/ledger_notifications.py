"""Energy-owned bot configuration and durable, bounded message delivery."""

import hashlib
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.secrets import decrypt_secret, encrypt_secret
from app.modules.energy.ledger_models import (
    EnergyBotConfig,
    EnergyLedgerRevision,
    EnergyNotificationRun,
)
from app.modules.energy.ledger_schemas import BotDefinition, BotResponse, BotWrite
from app.platform.identity.public_api import notification_recipient_for_user
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.im import (
    build_simple_card_content,
    send_feishu_message,
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


async def enqueue_reading_notification(
    db: AsyncSession,
    actor_id: UUID | None,
    dataset: str,
    reading_date: str,
    versions: str,
    count: int,
) -> None:
    config = await bot_config(db)
    if (
        actor_id is None
        or config is None
        or not BotDefinition.model_validate(config.definition).enabled
    ):
        return
    key = (
        "direct:"
        + hashlib.sha256(
            f"{dataset}:{reading_date}:{actor_id}:{versions}".encode()
        ).hexdigest()
    )
    if await db.scalar(
        select(EnergyNotificationRun.id).where(
            EnergyNotificationRun.delivery_key == key
        )
    ):
        return
    db.add(
        EnergyNotificationRun(
            id=uuid4(),
            task_id=uuid5(NAMESPACE_URL, key),
            delivery_key=key,
            definition={
                "target": str(actor_id),
                "dataset": dataset,
                "reading_date": reading_date,
                "count": count,
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
        if not run.definition.get("dataset") or not run.definition.get("reading_date"):
            run.status, run.error = "skipped", "旧责任分组消息已停用"
            continue
        target = str(run.definition["target"])
        recipient = await notification_recipient_for_user(db, UUID(target))
        if recipient is None:
            run.status, run.error = (
                "failed",
                "提交人缺少可用于当前应用的企业身份，请联系管理员完善人员映射",
            )
            continue
        run.attempts += 1
        run.status = "sending"
        run.next_attempt_at = now + timedelta(minutes=5)
        await db.flush()
        content = build_simple_card_content(
            title="能源原始数据已更新",
            markdown=(
                f"**{run.definition['dataset']}**\n"
                f"数据日期：{run.definition['reading_date']}\n"
                f"本次提交：{run.definition['count']} 项"
            ),
            button_text="查看原始数据",
            button_url=definition.base_url.rstrip("/")
            + "/energy/entry?"
            + urlencode(
                {
                    "date": str(run.definition["reading_date"]),
                    "dataset": str(run.definition["dataset"]),
                    "source": "feishu",
                }
            ),
        )
        try:
            token = await FeishuAuth.get_tenant_access_token(
                definition.app_id, decrypt_secret(config.encrypted_secret or "")
            )
            result = await send_feishu_message(
                receive_id=recipient[0],
                receive_id_type=recipient[1],
                tenant_access_token=token,
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
