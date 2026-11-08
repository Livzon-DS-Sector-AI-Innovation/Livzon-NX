"""作业票气体复检催办 + 证件到期提醒的推送服务。

复检催办：扫描「作业中」的动火/受限空间作业票，按配置间隔（默认
动火 60 分钟、受限空间 120 分钟，可经 work_permit_settings 覆盖）计算
下次复检到期时间，到期/超期时向监护人与作业负责人发飞书卡片；同一
到期窗口只催一次（Redis 窗口去重）。

证件到期：刷新证件状态后按里程碑天数（默认 30/15/7，0=已过期）推送，
同一证件同一节点只推一次（special_work_certificate_reminder_log）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import cache_get, cache_set
from app.modules.safety.models import (
    SafetyFeishuAppSettings,
    SpecialWorkCertificate,
    SpecialWorkCertificateReminderLog,
    WorkPermit,
    WorkPermitGasAnalysis,
    WorkPermitSetting,
)
from app.modules.safety.service.work_certificate import (
    certificates_due_for_expiry,
    refresh_expired_statuses,
)
from app.modules.safety.service.work_permit_templates import (
    PERMIT_STATUS_ACTIVE,
    PERMIT_TEMPLATES,
    gas_cycle_minutes_for,
)

logger = logging.getLogger(__name__)


async def _load_notify_settings(
    session: AsyncSession,
) -> SafetyFeishuAppSettings | None:
    result = await session.execute(
        select(SafetyFeishuAppSettings)
        .where(SafetyFeishuAppSettings.is_deleted.is_(False))
        .order_by(SafetyFeishuAppSettings.updated_at.desc())
        .limit(1)
    )
    settings_row: SafetyFeishuAppSettings | None = result.scalar_one_or_none()
    return settings_row


async def _load_cycle_overrides(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(WorkPermitSetting).where(
            WorkPermitSetting.is_deleted.is_(False),
            WorkPermitSetting.setting_key.like("gas_cycle_minutes.%"),
        )
    )
    overrides: dict[str, int] = {}
    for row in result.scalars().all():
        if isinstance(row.setting_value, (int, float)):
            overrides[row.setting_key.split(".", 1)[1]] = int(row.setting_value)
    return overrides


async def _gas_due_items(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """返回 [{permit, due_at, overdue, cycle_minutes}]（仅作业中的周期票种）。"""
    overrides = await _load_cycle_overrides(session)
    now = datetime.now(UTC)
    result = await session.execute(
        select(WorkPermit).where(
            WorkPermit.is_deleted.is_(False),
            WorkPermit.status == PERMIT_STATUS_ACTIVE,
            WorkPermit.permit_type.in_(
                [t.code for t in PERMIT_TEMPLATES.values() if t.gas_enabled]
            ),
        )
    )
    items: list[dict[str, object]] = []
    for permit in result.scalars().all():
        cycle = gas_cycle_minutes_for(permit.permit_type, overrides)
        if cycle is None:
            continue
        last_result = await session.execute(
            select(WorkPermitGasAnalysis.sampled_at)
            .where(
                WorkPermitGasAnalysis.permit_id == permit.id,
                WorkPermitGasAnalysis.is_deleted.is_(False),
            )
            .order_by(WorkPermitGasAnalysis.sampled_at.desc())
            .limit(1)
        )
        last = last_result.scalar_one_or_none()
        base = last or permit.actual_start_time or permit.planned_start_time
        if base is None:
            continue
        if base.tzinfo is None:
            continue  # 非时区感知数据异常，跳过
        due = base + timedelta(minutes=cycle)
        if due <= now:
            items.append(
                {
                    "permit": permit,
                    "due_at": due,
                    "overdue": True,
                    "cycle_minutes": cycle,
                }
            )
    return items


async def send_gas_due_reminders(
    session: AsyncSession,
) -> tuple[int, list[str]]:
    """推送复检到期/超期催办；返回（成功数, 错误列表）。"""
    from app.modules.safety.service.work_permit_notify import notify_gas_due

    settings_row = await _load_notify_settings(session)
    if settings_row is None or not settings_row.permit_notify_enabled:
        return 0, []

    errors: list[str] = []
    sent = 0
    for item in await _gas_due_items(session):
        permit = cast(WorkPermit, item["permit"])
        due_at = cast(datetime, item["due_at"])
        cycle = cast(int, item["cycle_minutes"])
        window_slot = int(due_at.timestamp()) // (cycle * 60)
        window_key = f"safety:wp_gas_due:{permit.id}:{window_slot}"
        if await cache_get(window_key):
            continue
        await cache_set(window_key, "1", ex=cycle * 60)
        try:
            await notify_gas_due(
                session, permit, due_at=due_at, overdue=bool(item["overdue"])
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 — 单票失败不阻断其他票
            logger.warning(
                "复检催办发送失败: permit=%s", permit.permit_no, exc_info=True
            )
            errors.append(f"{permit.permit_no}: {exc}")
    logger.info(
        "作业票复检催办完成: 成功=%s 错误=%s", sent, errors or "无"
    )
    return sent, errors


async def send_certificate_expiry_notifications(
    session: AsyncSession,
) -> tuple[int, list[str]]:
    """推送证件到期提醒；同一证件同一节点只推一次。"""
    from app.modules.safety.feishu.notification import (
        send_group_card,
        send_user_card,
    )

    settings_row = await _load_notify_settings(session)
    if settings_row is None or not settings_row.cert_expiry_notify_enabled:
        return 0, []

    await refresh_expired_statuses(session)
    milestones_raw = list(settings_row.cert_expiry_notify_milestones or [])
    milestones = [int(m) for m in milestones_raw if m >= 0] or [30, 15, 7]
    chat_ids = [str(c) for c in (settings_row.cert_expiry_notify_chat_ids or [])]
    user_ids = [str(u) for u in (settings_row.cert_expiry_notify_user_ids or [])]
    if not chat_ids and not user_ids:
        return 0, ["未配置提醒目标（chat_ids/user_ids 均为空）"]

    due_items = await certificates_due_for_expiry(session, milestones)
    sent = 0
    errors: list[str] = []
    for item in due_items:
        cert: SpecialWorkCertificate = item["certificate"]
        milestone: int = item["milestone_days"]
        exists = await session.execute(
            select(SpecialWorkCertificateReminderLog.id).where(
                SpecialWorkCertificateReminderLog.certificate_id == cert.id,
                SpecialWorkCertificateReminderLog.milestone_days == milestone,
                SpecialWorkCertificateReminderLog.is_deleted.is_(False),
            )
        )
        if exists.scalar_one_or_none():
            continue

        label = "已过期" if milestone == 0 else f"将于 {milestone} 天后到期"
        content = (
            f"**{cert.person_name}** 的"
            f"{cert.certificate_no or '证件'}{label}"
            f"（有效期至 {cert.expiry_date}），请及时安排复审换证。"
        )
        all_ok = True
        try:
            for chat_id in chat_ids:
                message_id = await send_group_card(
                    chat_id,
                    f"【证件到期提醒】{cert.person_name}",
                    content,
                    header_template="orange",
                )
                all_ok = all_ok and message_id is not None
            for open_id in user_ids:
                delivered = await send_user_card(
                    open_id,
                    f"【证件到期提醒】{cert.person_name}",
                    content,
                )
                all_ok = all_ok and delivered
        except Exception as exc:  # noqa: BLE001 — 单证失败不阻断
            logger.warning(
                "证件到期提醒发送失败: cert=%s", cert.id, exc_info=True
            )
            errors.append(f"{cert.person_name}: {exc}")
            continue
        if all_ok:
            session.add(
                SpecialWorkCertificateReminderLog(
                    certificate_id=cert.id,
                    milestone_days=milestone,
                )
            )
            await session.flush()
            sent += 1
    await session.commit()
    logger.info(
        "证件到期提醒推送完成: 候选=%s 成功=%s 错误=%s",
        len(due_items),
        sent,
        errors or "无",
    )
    return sent, errors


async def send_certificate_expiry_test(
    session: AsyncSession,
) -> tuple[int, list[str]]:
    """设置页「测试发送」：忽略去重记录，只发第一个到期候选。"""
    settings_row = await _load_notify_settings(session)
    if settings_row is None:
        return 0, ["尚未配置安全模块飞书应用"]
    milestones_raw = list(settings_row.cert_expiry_notify_milestones or [])
    milestones = [int(m) for m in milestones_raw if m >= 0] or [30, 15, 7]
    due_items = await certificates_due_for_expiry(session, milestones)
    if not due_items:
        return 0, ["当前没有命中提醒节点的证件"]
    cert: SpecialWorkCertificate = due_items[0]["certificate"]
    milestone = int(due_items[0]["milestone_days"])
    label = "已过期" if milestone == 0 else f"将于 {milestone} 天后到期"
    from app.modules.safety.feishu.notification import (
        send_group_card,
        send_user_card,
    )

    content = (
        f"（测试发送）**{cert.person_name}** 的证件{label}"
        f"（有效期至 {cert.expiry_date}）。"
    )
    sent = 0
    for chat_id in (str(c) for c in (settings_row.cert_expiry_notify_chat_ids or [])):
        if await send_group_card(
            chat_id,
            f"【证件到期提醒·测试】{cert.person_name}",
            content,
        ):
            sent += 1
    for open_id in (str(u) for u in (settings_row.cert_expiry_notify_user_ids or [])):
        if await send_user_card(
            open_id,
            f"【证件到期提醒·测试】{cert.person_name}",
            content,
        ):
            sent += 1
    return sent, []


__all__ = [
    "send_certificate_expiry_notifications",
    "send_certificate_expiry_test",
    "send_gas_due_reminders",
]
