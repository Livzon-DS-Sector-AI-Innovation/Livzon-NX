"""隐患到期提醒：按「目标完成日期」的提醒节点推送飞书卡片。

节点制：设置里配置提醒节点天数列表（如 [30,15,7]，对应到期前一个月/
半个月/一周）。每天 08:00 检查一次，隐患进入某个节点（剩余天数首次
≤ 节点值）或逾期时推送——每个节点只推一次（推送记录表查重），没有
新触发的节点当天静默跳过，不重复轰炸。

数据来自隐患台账镜像（页面绑定 sub_tables 全部子表）。仪表盘的
due_summary 统计口径与这里完全一致（见 summarize_due）。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.feishu.field_codec import KIND_DATE
from app.modules.safety.feishu.notification import send_group_card, send_user_card
from app.modules.safety.models import (
    HazardDueNotificationLog,
    SafetyFeishuAppSettings,
)
from app.modules.safety.service import page_table

logger = logging.getLogger(__name__)

LEDGER_PAGE_KEY = "safety:risk-hazard:hazard-inspection:hazard-quick-report"
DUE_FIELD = "目标完成日期"
CLOSE_FIELD = "关闭状态"
CLOSED_VALUE = "已关闭"
# 到期提醒的默认节点：一个月 / 半个月 / 一周（逾期再推一次）
DEFAULT_MILESTONES: tuple[int, ...] = (30, 15, 7)
# 逾期节点用 0 表示（剩余天数 < 0 时触发）
OVERDUE_MILESTONE = 0
# 仪表盘到期卡片的候选时间窗（天）；与推送节点相互独立
DUE_WINDOWS: tuple[int, ...] = (7, 15, 30)
# 单条消息每个节点分组最多列出的条数
MESSAGE_LINE_LIMIT = 10
# 推送记录保留时长（历史记录定期清理，防表膨胀）
NOTIFY_LOG_RETENTION = timedelta(days=365)


def _today() -> date:
    return datetime.now().date()


def _days_until(value: Any) -> int | None:
    """解码字段值（YYYY-MM-DD）距今天的天数；解析失败返回 None。"""
    if not value:
        return None
    try:
        target = date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return (target - _today()).days


def _close_options(value: Any) -> list[str]:
    """关闭状态字段的选项集合：兼容单选（字符串）与多选（数组）子表。"""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _is_closed(record: dict[str, Any], close_field: str) -> bool:
    return CLOSED_VALUE in _close_options(record.get(close_field))


def milestone_for(days_left: int, milestones: list[int]) -> int | None:
    """剩余天数所处的提醒节点：取「已进入的节点里最内层者」。

    例：节点 [30,15,7]，剩 25 天 → 处于 30 节点；剩 10 天 → 已越过 30、
    处于 15 节点；剩 3 天 → 处于 7 节点；逾期（负数）→ 0（逾期节点）；
    剩 40 天 → 未进入任何节点，None。配合推送记录查重，每条隐患每个
    节点只推一次；中途才纳入视线的隐患只推当前所处节点，不回补历史节点。
    """
    if days_left < 0:
        return OVERDUE_MILESTONE
    applicable = [m for m in milestones if days_left <= m]
    return min(applicable) if applicable else None


def summarize_due(
    records: list[dict[str, Any]],
    due_field: str = DUE_FIELD,
    close_field: str = CLOSE_FIELD,
) -> dict[str, int]:
    """未关闭（关闭状态 ≠ 已关闭）记录的到期分布。

    overdue = 已逾期；within_N = 距今 N 天内到期（含今天）。日期为空或
    无法解析的记录不计入（仪表盘与推送同口径）。
    """
    summary: dict[str, int] = {"overdue": 0}
    for window in DUE_WINDOWS:
        summary[f"within_{window}"] = 0
    for record in records:
        if _is_closed(record, close_field):
            continue
        days = _days_until(record.get(due_field))
        if days is None:
            continue
        if days < 0:
            summary["overdue"] += 1
        else:
            for window in DUE_WINDOWS:
                if days <= window:
                    summary[f"within_{window}"] += 1
    return summary


def _milestone_label(milestone: int) -> str:
    if milestone == OVERDUE_MILESTONE:
        return "已逾期"
    if milestone >= 30 and milestone % 30 == 0:
        return f"到期前{milestone // 30}个月"
    if milestone == 15:
        return "到期前半个月"
    if milestone == 7:
        return "到期前一周"
    return f"到期前{milestone}天"


def _message_line(record: dict[str, Any]) -> str:
    dept = str(record.get("部门/车间") or "").strip() or "未知部门"
    content = str(record.get("隐患内容") or "").strip()
    if len(content) > 30:
        content = content[:30] + "…"
    owner_value = record.get("负责人")
    if isinstance(owner_value, list):
        names = [
            str(item.get("name") or "").strip()
            for item in owner_value
            if isinstance(item, dict) and item.get("name")
        ]
        owner = "、".join(names) or "未指派"
    else:
        owner = str(owner_value or "").strip() or "未指派"
    due = str(record.get(DUE_FIELD) or "").strip() or "无日期"
    days = _days_until(record.get(DUE_FIELD))
    badge = (
        f"已逾期{-days}天"
        if days is not None and days < 0
        else f"{days}天后到期" if days is not None else "待定"
    )
    return f"- {dept}｜{content}｜负责人：{owner}｜目标：{due}（{badge}）"


async def collect_due_records(
    db: AsyncSession,
    *,
    page_key: str = LEDGER_PAGE_KEY,
) -> list[tuple[str, list[dict[str, Any]]]]:
    """扫描台账全部绑定子表，返回 [(table_id, 未关闭且有目标日期的记录)]。

    只统计「目标完成日期」为日期类型字段的子表；镜像未同步时回退实时
    拉取（与页面统计同一条取数路径）。
    """
    definition, model, app_token, _primary = await page_table._load_config_or_raise(
        db, page_key
    )
    bound_tables = page_table._bound_tables(definition, model)
    collected: list[tuple[str, list[dict[str, Any]]]] = []
    for bound in bound_tables:
        records, columns = await page_table._collect_table_records(
            db, model, app_token, bound
        )
        due_target = next(
            (f for f in columns if f.name == DUE_FIELD and f.kind == KIND_DATE), None
        )
        if due_target is None:
            continue  # 该子表没有日期型目标完成日期（如不符合项/观察项）
        open_records = [
            record
            for record in records
            if not _is_closed(record, CLOSE_FIELD)
            and _days_until(record.get(DUE_FIELD)) is not None
        ]
        if open_records:
            collected.append((bound.table_id, open_records))
    return collected


async def _load_settings(db: AsyncSession) -> SafetyFeishuAppSettings | None:
    return (
        await db.execute(select(SafetyFeishuAppSettings).limit(1))
    ).scalar_one_or_none()


async def _purge_stale_logs(db: AsyncSession) -> None:
    """清理超期推送记录（防表膨胀）。"""
    from sqlalchemy import delete

    cutoff = datetime.now(UTC) - NOTIFY_LOG_RETENTION
    await db.execute(
        delete(HazardDueNotificationLog).where(
            HazardDueNotificationLog.notified_at < cutoff
        )
    )


def _build_pending(
    collected: list[tuple[str, list[dict[str, Any]]]],
    milestones: list[int],
    logged: set[tuple[str, str, int]],
) -> dict[int, list[tuple[str, dict[str, Any]]]]:
    """按节点分组「新触发且未推送过」的隐患：(table_id, record) 对。"""
    pending: dict[int, list[tuple[str, dict[str, Any]]]] = {}
    for table_id, records in collected:
        for record in records:
            days_left = _days_until(record.get(DUE_FIELD))
            if days_left is None:
                continue
            milestone = milestone_for(days_left, milestones)
            if milestone is None:
                continue  # 还没进入任何节点
            record_id = str(record.get("_record_id") or "")
            if not record_id or (table_id, record_id, milestone) in logged:
                continue
            pending.setdefault(milestone, []).append((table_id, record))
    for items in pending.values():
        items.sort(
            key=lambda pair: _days_until(pair[1].get(DUE_FIELD)) or 0
        )
    return pending


async def send_hazard_due_notifications(
    db: AsyncSession,
    *,
    is_test: bool = False,
) -> tuple[int, list[str] | None]:
    """按节点推送到期提醒卡片，返回 (成功条数, 错误列表)。

    未启用/未配置目标时静默跳过（返回 (0, None)）；无新触发节点也静默
    跳过；测试模式强制发送一条样例卡片并给出明确错误。
    """
    settings = await _load_settings(db)
    if settings is None:
        return 0, None
    if not settings.hazard_due_notify_enabled and not is_test:
        logger.info("隐患到期提醒未启用，跳过推送")
        return 0, None
    chat_ids = [
        str(c).strip()
        for c in (settings.hazard_due_notify_chat_ids or [])
        if str(c).strip()
    ]
    user_ids = [
        str(u).strip()
        for u in (settings.hazard_due_notify_user_ids or [])
        if str(u).strip()
    ]
    if not chat_ids and not user_ids:
        if is_test:
            return 0, ["未配置提醒目标（群 chat_id / 个人 open_id）"]
        logger.info("隐患到期提醒未配置目标，跳过推送")
        return 0, None

    pending: dict[int, list[tuple[str, dict[str, Any]]]] | None = None
    if is_test:
        title = "隐患到期提醒 · 通知测试"
        content = (
            "这是一条**测试通知**。\n\n"
            "配置验证成功后，每天 08:00 检查隐患台账：隐患进入提醒节点"
            "（如到期前一个月/半个月/一周）或逾期时推送一次，同一节点不重复。"
        )
    else:
        raw_milestones = settings.hazard_due_notify_milestones
        milestone_source = (
            raw_milestones if raw_milestones is not None else list(DEFAULT_MILESTONES)
        )
        milestones = sorted(
            {int(m) for m in milestone_source if int(m) > 0},
            reverse=True,
        )
        if not milestones:
            logger.info("隐患到期提醒未配置节点，跳过推送")
            return 0, None
        collected = await collect_due_records(db)
        # 查推送记录：同一条隐患同一节点只推一次（全量小表，直接载入）
        rows = (await db.execute(select(HazardDueNotificationLog))).scalars().all()
        logged = {
            (row.table_id, row.record_id, row.milestone_days)
            for row in rows
            if not row.is_deleted
        }
        pending = _build_pending(collected, milestones, logged)
        if not pending:
            logger.info("无新触发的提醒节点，跳过推送")
            return 0, None

        lines: list[str] = []
        total = 0
        for milestone in sorted(pending, reverse=True):
            items = pending[milestone]
            total += len(items)
            lines.append(f"**{_milestone_label(milestone)}（{len(items)} 项）**")
            lines.extend(
                _message_line(record) for _tid, record in items[:MESSAGE_LINE_LIMIT]
            )
            if len(items) > MESSAGE_LINE_LIMIT:
                lines.append(f"…… 该节点共 {len(items)} 项")
        lines.append("详见 安全管理 → 隐患台账")
        title = f"隐患到期提醒 · {total} 项进入提醒节点"
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

    # 发送成功后才写推送记录（每节点一次）。全部目标失败时不写记录，
    # 明晚自动重试——宁可偶尔重推，不可因发送故障漏推。
    if pending is not None and sent > 0:
        now = datetime.now(UTC)
        try:
            for milestone, items in pending.items():
                for table_id, record in items:
                    record_id = str(record.get("_record_id") or "")
                    if not record_id:
                        continue
                    db.add(
                        HazardDueNotificationLog(
                            table_id=table_id,
                            record_id=record_id,
                            milestone_days=milestone,
                            notified_at=now,
                        )
                    )
            await db.commit()
        except Exception:  # noqa: BLE001 —— 记录失败只记日志，接受明晚重推
            await db.rollback()
            logger.exception("到期提醒推送记录写入失败（消息已发送，明晚可能重推）")
        try:
            await _purge_stale_logs(db)
        except Exception:  # noqa: BLE001 —— 清理失败不影响推送
            logger.exception("到期提醒推送记录清理失败")
    return sent, errors


async def send_test_notification(db: AsyncSession) -> dict[str, Any]:
    """设置页「测试发送」：向已配置目标发一条样例卡片。"""
    sent, errors = await send_hazard_due_notifications(db, is_test=True)
    if sent == 0 and errors:
        raise AppException(message="；".join(errors[:3]))
    return {"sent": sent, "errors": errors}
