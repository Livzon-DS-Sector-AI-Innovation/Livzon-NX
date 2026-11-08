"""8 大作业票飞书卡片通知（提交→审批→验票→完工→驳回→复检催办）。

使用安全模块独立飞书应用（feishu/notification）发送互动卡片：
- 待办节点卡片带「同意 / 驳回」按钮，回调走 feishu.event_client 的
  card.action.trigger（见 work_permit_card_handler）；
- 收件人按 identity.users.feishu_open_id 解析，未绑定飞书的用户跳过；
- 飞书未配置/发送失败只记日志，不影响业务事务；
- ``permit_notify_enabled``（SafetyFeishuAppSettings）关闭时不发送。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.safety.models import (
    SafetyFeishuAppSettings,
    WorkPermit,
    WorkPermitNode,
)
from app.modules.safety.service.work_permit_templates import (
    PERMIT_LEVEL_LABELS,
    PERMIT_STATUS_ACTIVE,
    PERMIT_STATUS_APPROVED,
    PERMIT_STATUS_COMPLETED,
    PERMIT_STATUS_LABELS,
    PERMIT_STATUS_PENDING,
    PERMIT_STATUS_REJECTED,
    PERMIT_TEMPLATES,
)
from app.platform.identity.models import User

logger = logging.getLogger(__name__)


async def _permit_notify_enabled(db: AsyncSession) -> bool:
    result = await db.execute(select(SafetyFeishuAppSettings).limit(1))
    settings = result.scalar_one_or_none()
    if settings is None or not settings.is_enabled:
        return False
    return bool(getattr(settings, "permit_notify_enabled", False))


async def _open_id_map(
    db: AsyncSession, user_ids: list[UUID | None]
) -> dict[UUID, str]:
    ids = [uid for uid in set(user_ids) if uid is not None]
    if not ids:
        return {}
    result = await db.execute(
        select(User.id, User.feishu_open_id).where(User.id.in_(ids))
    )
    return {
        row[0]: row[1]
        for row in result.all()
        if row[1]
    }


def _permit_line(permit: WorkPermit) -> str:
    template = PERMIT_TEMPLATES[permit.permit_type]
    level = PERMIT_LEVEL_LABELS.get(permit.permit_level, permit.permit_level)
    return (
        f"**{template.name}**（{level}）\n"
        f"**编号：{permit.permit_no}**\n"
        f"申请单位：{permit.apply_department or '-'}\n"
        f"作业内容：{(permit.work_description or '-')[:80]}"
    )


def _time_text(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%m-%d %H:%M")


def _approval_buttons(
    permit_id: UUID, node_id: UUID, permit_no: str
) -> list[dict[str, Any]]:
    value = {
        "module": "work_permit",
        "permit_id": str(permit_id),
        "node_id": str(node_id),
        "permit_no": permit_no,
    }
    return [
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "同意"},
                    "type": "primary",
                    "value": {**value, "action": "approve"},
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "驳回"},
                    "type": "danger",
                    "value": {**value, "action": "reject"},
                },
            ],
        }
    ]


def _detail_link(permit_id: UUID) -> list[dict[str, Any]]:
    frontend = get_settings().FRONTEND_URL.rstrip("/")
    if not frontend:
        return []
    return [
        {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看作业票详情"},
                    "type": "default",
                    "url": f"{frontend}/safety/work-permits/{permit_id}",
                }
            ],
        }
    ]


async def notify_pending_node(
    db: AsyncSession,
    permit: WorkPermit,
    node: WorkPermitNode | None,
) -> None:
    """给当前待处理节点的指派审批人发待办卡片（含同意/驳回按钮）。"""
    if node is None or node.assigned_approver_id is None:
        return
    try:
        if not await _permit_notify_enabled(db):
            return
        from app.modules.safety.feishu.notification import send_user_card

        open_map = await _open_id_map(db, [node.assigned_approver_id])
        open_id = open_map.get(node.assigned_approver_id)
        if not open_id:
            logger.info(
                "审批人未绑定飞书，跳过卡片: node=%s", node.node_key
            )
            return
        if node.node_kind in ("approve", "confirm"):
            content = (
                f"{_permit_line(permit)}\n"
                f"待您处理节点：**{node.node_name}**\n"
                f"实施时间：{_time_text(permit.planned_start_time)} ~ "
                f"{_time_text(permit.planned_end_time)}"
            )
            elements = _approval_buttons(permit.id, node.id, permit.permit_no)
        else:
            content = (
                f"{_permit_line(permit)}\n"
                f"待您处理节点：**{node.node_name}**"
            )
            elements = []
        elements.extend(_detail_link(permit.id))
        await send_user_card(
            open_id,
            f"【作业票审批】{permit.permit_no}",
            content,
            elements=elements,
        )
    except Exception:
        logger.exception("作业票待办卡片发送失败: %s", permit.permit_no)


async def notify_status_change(
    db: AsyncSession,
    permit: WorkPermit,
    *,
    title: str,
    extra: str = "",
) -> None:
    """状态变化通知创建人（驳回/验票/完工/作废等）。"""
    try:
        if not await _permit_notify_enabled(db):
            return
        if permit.created_by is None:
            return
        from app.modules.safety.feishu.notification import send_user_card

        open_map = await _open_id_map(db, [permit.created_by])
        open_id = open_map.get(permit.created_by)
        if not open_id:
            return
        content = (
            f"{_permit_line(permit)}\n"
            f"当前状态：**{PERMIT_STATUS_LABELS.get(permit.status, permit.status)}**"
        )
        if extra:
            content += f"\n{extra}"
        elements = _detail_link(permit.id)
        await send_user_card(
            open_id,
            f"【作业票动态】{permit.permit_no} {title}",
            content,
            elements=elements,
        )
    except Exception:
        logger.exception("作业票状态卡片发送失败: %s", permit.permit_no)


async def notify_after_transition(
    db: AsyncSession,
    permit: WorkPermit,
    *,
    reject_opinion: str | None = None,
) -> None:
    """按流转后的状态分发通知：下一审批人 / 验票人 / 创建人。"""
    try:
        if permit.status == PERMIT_STATUS_PENDING:
            node = await _pending_node(db, permit)
            await notify_pending_node(db, permit, node)
            return
        if not await _permit_notify_enabled(db):
            return
        template = PERMIT_TEMPLATES[permit.permit_type]
        if permit.status == PERMIT_STATUS_APPROVED:
            verify_node = await _verify_node(db, permit)
            if verify_node is not None and verify_node.assigned_approver_id:
                await notify_pending_node(db, permit, verify_node)
            else:
                await notify_status_change(
                    db, permit, title="全部签批完成", extra="请安排验票开工"
                )
        elif permit.status == PERMIT_STATUS_REJECTED:
            await notify_status_change(
                db,
                permit,
                title="已被驳回",
                extra=f"驳回意见：{reject_opinion or '-'}；修改后可重新提交",
            )
        elif permit.status == PERMIT_STATUS_ACTIVE:
            await notify_status_change(db, permit, title="验票完成，开始作业")
            if template.gas_enabled and template.gas_cycle_minutes:
                await notify_status_change(
                    db,
                    permit,
                    title="请按周期录入气体复检",
                    extra=f"复检间隔：{template.gas_cycle_minutes} 分钟",
                )
        elif permit.status == PERMIT_STATUS_COMPLETED:
            await notify_status_change(db, permit, title="完工验收完成")
    except Exception:
        logger.exception("作业票流转通知失败: %s", permit.permit_no)


async def _pending_node(
    db: AsyncSession, permit: WorkPermit
) -> WorkPermitNode | None:
    result = await db.execute(
        select(WorkPermitNode).where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.seq == permit.current_node_seq,
            WorkPermitNode.status == "pending",
            WorkPermitNode.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def _verify_node(
    db: AsyncSession, permit: WorkPermit
) -> WorkPermitNode | None:
    result = await db.execute(
        select(WorkPermitNode).where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.node_kind == "verify",
            WorkPermitNode.status == "waiting",
            WorkPermitNode.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


async def notify_gas_due(
    db: AsyncSession,
    permit: WorkPermit,
    *,
    due_at: datetime,
    overdue: bool,
) -> None:
    """复检到期/超期催办：通知监护人与作业负责人（按 persons 中的账号）。"""
    try:
        if not await _permit_notify_enabled(db):
            return
        from app.modules.safety.feishu.notification import send_user_card

        user_ids = [
            p.get("user_id")
            for p in (permit.persons or [])
            if p.get("role") in ("guardian", "work_leader")
            and p.get("user_id")
        ]
        open_map = await _open_id_map(
            db, [UUID(str(uid)) for uid in user_ids]
        )
        if not open_map:
            return
        state = "已超期，请立即停止作业并复检" if overdue else "即将到期，请安排复检"
        content = (
            f"{_permit_line(permit)}\n"
            f"气体复检要求：{_time_text(due_at)} 前完成（{state}）"
        )
        elements = _detail_link(permit.id)
        for uid, open_id in open_map.items():
            await send_user_card(
                open_id,
                f"【复检提醒】{permit.permit_no}",
                content,
                elements=elements,
            )
    except Exception:
        logger.exception("复检提醒发送失败: %s", permit.permit_no)


__all__ = [
    "notify_gas_due",
    "notify_pending_node",
    "notify_status_change",
]
