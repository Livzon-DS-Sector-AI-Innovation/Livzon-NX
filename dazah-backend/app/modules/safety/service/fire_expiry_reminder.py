"""消防器材有效期到期提醒：按「有效日期」的提醒节点推送飞书卡片。

与隐患到期提醒同口径（见 ``hazard_due_reminder``）：设置里配置提醒节点
天数列表（如 [30,15,7]）。每天定时检查一次，器材进入某个节点（剩余
天数首次 ≤ 节点值）或已过期时推送——每台器材每个节点只推一次（推送
记录表查重），没有新触发的节点当天静默跳过。

数据来自 ``fire_equipment`` 台账投影的 ``expiry_date``（飞书 有效日期
等字段）。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.feishu.notification import send_group_card, send_user_card
from app.modules.safety.models import (
    FireEquipment,
    FireExpiryNotificationLog,
    SafetyFeishuAppSettings,
)
from app.modules.safety.service.hazard_due_reminder import milestone_for

logger = logging.getLogger(__name__)

# 到期提醒的默认节点：一个月 / 半个月 / 一周（过期再推一次）
DEFAULT_MILESTONES: tuple[int, ...] = (30, 15, 7)
# 过期节点用 0 表示
OVERDUE_MILESTONE = 0
# 单条消息每个节点分组最多列出的条数
MESSAGE_LINE_LIMIT = 10
# 推送记录保留时长（防表膨胀）
NOTIFY_LOG_RETENTION = timedelta(days=365)


def _today() -> date:
    return datetime.now().date()


def _milestone_label(milestone: int) -> str:
    if milestone == OVERDUE_MILESTONE:
        return "已过期"
    if milestone >= 30 and milestone % 30 == 0:
        return f"有效期还剩{milestone // 30}个月"
    if milestone == 15:
        return "有效期还剩半个月"
    if milestone == 7:
        return "有效期还剩一周"
    return f"有效期还剩{milestone}天"


def _person_names(value: Any) -> str:
    if isinstance(value, list):
        names = [
            str(item.get("name") or "").strip()
            for item in value
            if isinstance(item, dict) and item.get("name")
        ]
        return "、".join(names)
    return str(value or "").strip()


def _days_left_of(equipment: FireEquipment) -> int:
    """剩余有效天数（调用前已过滤无日期的器材；兜底返回 0 当天到期）。"""
    expiry = equipment.expiry_date
    if expiry is None:
        return 0
    return (expiry - _today()).days


def _message_line(equipment: FireEquipment, days_left: int) -> str:
    badge = (
        f"已过期{-days_left}天" if days_left < 0 else f"{days_left}天后到期"
    )
    owner = _person_names((equipment.fields or {}).get("责任人"))
    expiry_text = (
        equipment.expiry_date.isoformat()
        if equipment.expiry_date is not None
        else "—"
    )
    return (
        f"- {equipment.department or '未知部门'}｜"
        f"{equipment.equipment_no or '（未填编号）'}｜"
        f"位置：{equipment.location or '—'}"
        + (f"｜责任人：{owner}" if owner else "")
        + f"｜有效期至 {expiry_text}（{badge}）"
    )


async def _load_settings(db: AsyncSession) -> SafetyFeishuAppSettings | None:
    return (
        await db.execute(select(SafetyFeishuAppSettings).limit(1))
    ).scalar_one_or_none()


async def _purge_stale_logs(db: AsyncSession) -> None:
    cutoff = datetime.now(UTC) - NOTIFY_LOG_RETENTION
    await db.execute(
        delete(FireExpiryNotificationLog).where(
            FireExpiryNotificationLog.notified_at < cutoff
        )
    )


def _build_pending(
    equipment_rows: Sequence[FireEquipment],
    milestones: list[int],
    logged: set[tuple[str, int]],
) -> dict[int, list[FireEquipment]]:
    """按节点分组「新触发且未推送过」的器材。"""
    pending: dict[int, list[FireEquipment]] = {}
    for equipment in equipment_rows:
        if equipment.expiry_date is None:
            continue
        days_left = _days_left_of(equipment)
        milestone = milestone_for(days_left, milestones)
        if milestone is None:
            continue  # 还没进入任何节点
        if (str(equipment.id), milestone) in logged:
            continue
        pending.setdefault(milestone, []).append(equipment)
    for items in pending.values():
        items.sort(key=_days_left_of)
    return pending


async def send_fire_expiry_notifications(
    db: AsyncSession,
    *,
    is_test: bool = False,
) -> tuple[int, list[str] | None]:
    """按节点推送有效期提醒卡片，返回 (成功条数, 错误列表)。

    未启用/未配置目标/无新触发节点时静默跳过（返回 (0, None)）；测试
    模式强制发送一条样例卡片并给出明确错误。
    """
    settings = await _load_settings(db)
    if settings is None:
        return 0, None
    if not settings.fire_expiry_notify_enabled and not is_test:
        logger.info("消防器材有效期提醒未启用，跳过推送")
        return 0, None
    chat_ids = [
        str(c).strip()
        for c in (settings.fire_expiry_notify_chat_ids or [])
        if str(c).strip()
    ]
    user_ids = [
        str(u).strip()
        for u in (settings.fire_expiry_notify_user_ids or [])
        if str(u).strip()
    ]
    if not chat_ids and not user_ids:
        if is_test:
            return 0, ["未配置提醒目标（群 chat_id / 个人 open_id）"]
        logger.info("消防器材有效期提醒未配置目标，跳过推送")
        return 0, None

    pending: dict[int, list[FireEquipment]] | None = None
    if is_test:
        title = "消防器材有效期提醒 · 通知测试"
        content = (
            "这是一条**测试通知**。\n\n"
            "配置验证成功后，每天定时检查消防器材台账：器材进入有效期提醒"
            "节点（如还剩一个月/半个月/一周）或已过期时推送一次，同一台器材"
            "同一节点不重复。"
        )
    else:
        raw_milestones = settings.fire_expiry_notify_milestones
        milestone_source = (
            raw_milestones if raw_milestones else list(DEFAULT_MILESTONES)
        )
        milestones = sorted(
            {int(m) for m in milestone_source if int(m) >= 0},
            reverse=True,
        )
        if not milestones:
            logger.info("消防器材有效期提醒未配置节点，跳过推送")
            return 0, None
        equipment_rows = (
            (
                await db.execute(
                    select(FireEquipment).where(
                        FireEquipment.is_deleted.is_(False),
                        FireEquipment.expiry_date.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        rows = (
            (await db.execute(select(FireExpiryNotificationLog))).scalars().all()
        )
        logged = {
            (str(row.equipment_id), row.milestone_days)
            for row in rows
            if not row.is_deleted
        }
        pending = _build_pending(equipment_rows, milestones, logged)
        if not pending:
            logger.info("无新触发的有效期提醒节点，跳过推送")
            return 0, None

        lines: list[str] = []
        total = 0
        for milestone in sorted(pending, reverse=True):
            items = pending[milestone]
            total += len(items)
            lines.append(f"**{_milestone_label(milestone)}（{len(items)} 台）**")
            lines.extend(
                _message_line(row, _days_left_of(row))
                for row in items[:MESSAGE_LINE_LIMIT]
            )
            if len(items) > MESSAGE_LINE_LIMIT:
                lines.append(f"…… 该节点共 {len(items)} 台")
        lines.append("详见 安全管理 → 灭火器及消防栓点检")
        title = f"消防器材有效期提醒 · {total} 台进入提醒节点"
        content = "\n".join(lines)

    sent, errors = 0, []
    for chat_id in chat_ids:
        try:
            if await send_group_card(chat_id, title, content, header_template="red"):
                sent += 1
            else:
                errors.append(f"群 {chat_id[:12]}… 发送失败")
        except Exception as exc:  # noqa: BLE001 —— 单目标失败不影响其他
            errors.append(f"群 {chat_id[:12]}… {type(exc).__name__}")
    for user_id in user_ids:
        try:
            if await send_user_card(user_id, title, content):
                sent += 1
            else:
                errors.append(f"个人 {user_id[:12]}… 发送失败")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"个人 {user_id[:12]}… {type(exc).__name__}")

    # 发送成功后才写推送记录（每台器材每节点一次）；全部失败不写，次日重试
    if pending is not None and sent > 0:
        now = datetime.now(UTC)
        try:
            for milestone, items in pending.items():
                for equipment in items:
                    db.add(
                        FireExpiryNotificationLog(
                            equipment_id=equipment.id,
                            milestone_days=milestone,
                            notified_at=now,
                        )
                    )
            await db.commit()
        except Exception:  # noqa: BLE001 —— 记录失败只记日志，接受次日重推
            await db.rollback()
            logger.exception("有效期提醒推送记录写入失败（消息已发送，次日可能重推）")
        try:
            await _purge_stale_logs(db)
        except Exception:  # noqa: BLE001
            logger.exception("有效期提醒推送记录清理失败")
    return sent, errors


async def send_test_notification(db: AsyncSession) -> dict[str, Any]:
    """设置页「测试发送」：向已配置目标发一条样例卡片。"""
    sent, errors = await send_fire_expiry_notifications(db, is_test=True)
    if sent == 0 and errors:
        raise AppException(message="；".join(errors[:3]))
    return {"sent": sent, "errors": errors}
