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
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import cache_set
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
    """用户ID → feishu_union_id（跨应用一致，安全机器人可用）。"""
    ids = [uid for uid in set(user_ids) if uid is not None]
    if not ids:
        return {}
    result = await db.execute(
        select(User.id, User.feishu_union_id).where(User.id.in_(ids))
    )
    return {row[0]: row[1] for row in result.all() if row[1]}


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
            logger.info("审批人未绑定飞书，跳过卡片: node=%s", node.node_key)
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
            content = f"{_permit_line(permit)}\n待您处理节点：**{node.node_name}**"
            elements = []
        elements.extend(_detail_link(permit.id))
        await send_user_card(
            open_id,
            f"【作业票审批】{permit.permit_no}",
            content,
            elements=elements,
            id_type="union_id",
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
            id_type="union_id",
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


async def _pending_node(db: AsyncSession, permit: WorkPermit) -> WorkPermitNode | None:
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


async def _verify_node(db: AsyncSession, permit: WorkPermit) -> WorkPermitNode | None:
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
            if p.get("role") in ("guardian", "work_leader") and p.get("user_id")
        ]
        open_map = await _open_id_map(db, [UUID(str(uid)) for uid in user_ids])
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
                id_type="union_id",
            )
    except Exception:
        logger.exception("复检提醒发送失败: %s", permit.permit_no)


__all__ = [
    "notify_gas_due",
    "notify_pending_node",
    "notify_status_change",
    "push_approval_card_for_next_node",
    "refresh_or_push_approval_card",
]


async def send_raw_card(open_id: str, card: dict[str, Any]) -> str | None:
    """发送自定义卡片 JSON（卡片 2.0 表单等），返回 message_id。

    open_id 须为安全模块机器人应用下的 open_id（跨应用 open_id 不通用）；
    若已知的是 union_id，请用 send_raw_card_by_union_id。
    """
    return await _send_card(open_id, card, "open_id")


async def send_raw_card_by_union_id(union_id: str, card: dict[str, Any]) -> str | None:
    """按 union_id 发送卡片（跨应用一致，推荐用于 DB 查出的用户）。"""
    return await _send_card(union_id, card, "union_id")


async def _send_card(receive_id: str, card: dict[str, Any], id_type: str) -> str | None:
    try:
        if not receive_id:
            return None
        from lark_oapi.api.im.v1 import (  # type: ignore[import-untyped]
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        from app.modules.safety.feishu.client import (
            get_safety_feishu_client,
            get_safety_tenant_token,
        )

        client = await get_safety_feishu_client()
        token = await get_safety_tenant_token(client)
        card_json = _json_dumps(card)
        req = (
            CreateMessageRequest.builder()
            .receive_id_type(id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("interactive")
                .content(card_json)
                .build()
            )
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.im.v1.message.acreate(req)
        if not resp.success():
            logger.error(
                "send_raw_card 失败: %s=%s code=%s msg=%s",
                id_type,
                receive_id,
                resp.code,
                resp.msg,
            )
            return None
        return resp.data.message_id if resp.data else None
    except Exception:
        logger.exception("send_raw_card 异常: %s=%s", id_type, receive_id)
        return None


async def push_approval_card_for_next_node(
    db: AsyncSession, permit_or_id: UUID | WorkPermit
) -> None:
    """提交/签批/验票/验收后：按当前状态向下一环节处理人推完整票面卡。

    - pending_approval → 当前节点审批人（手写签名 + 默认签名提示 + 同意/驳回）
    - approved → 验票人（确认开工）；无验票环节票种 → 验收人（完工验收）
    - active → 验收人（完工验收 + 复检周期提示）
    - completed → 创建人（PDF 下载）
    """
    try:
        if not await _permit_notify_enabled(db):
            return
        permit = await _resolve_permit(db, permit_or_id)
        if permit is None:
            return
        recipient, elements, card_title = await _next_stage_elements(db, permit)
        if recipient is None or not elements:
            return
        union_id = await _recipient_union_id(db, recipient)
        if not union_id:
            logger.info(
                "下一环节处理人未绑定飞书，跳过审批卡: permit=%s status=%s",
                permit.permit_no,
                permit.status,
            )
            return
        message_id = await send_raw_card_by_union_id(
            union_id, _card_for(elements, title=card_title or "作业票审批")
        )
        if message_id:
            await cache_set(
                f"wp_approval_card:{union_id}:{permit.id}",
                message_id,
                ex=7 * 86400,
            )
    except Exception:
        logger.exception(
            "审批卡推送失败: permit=%s",
            getattr(permit_or_id, "permit_no", permit_or_id),
        )


async def refresh_or_push_approval_card(
    db: AsyncSession, permit_or_id: UUID | WorkPermit
) -> None:
    """节点签名完成后刷新已推的审批卡（PATCH），无缓存卡时退回推送新卡。"""
    from app.modules.safety.feishu.notification import update_card

    try:
        if not await _permit_notify_enabled(db):
            return
        permit = await _resolve_permit(db, permit_or_id)
        if permit is None:
            return
        if permit.status != PERMIT_STATUS_PENDING:
            await push_approval_card_for_next_node(db, permit)
            return
        node = await _pending_node(db, permit)
        if node is None or node.assigned_approver_id is None:
            return
        union_id = await _recipient_union_id(db, node.assigned_approver_id)
        cached_message_id = (
            await _cached_approval_card_id(union_id, permit.id) if union_id else None
        )
        if not cached_message_id:
            await push_approval_card_for_next_node(db, permit)
            return
        _recipient, elements, card_title = await _next_stage_elements(db, permit)
        if elements:
            await update_card(
                cached_message_id,
                _card_for(elements, title=card_title or "作业票审批"),
            )
    except Exception:
        logger.exception(
            "审批卡刷新失败: permit=%s",
            getattr(permit_or_id, "permit_no", permit_or_id),
        )


async def _resolve_permit(
    db: AsyncSession, permit_or_id: UUID | WorkPermit
) -> WorkPermit | None:
    if isinstance(permit_or_id, WorkPermit):
        return permit_or_id
    result = await db.execute(select(WorkPermit).where(WorkPermit.id == permit_or_id))
    return result.scalar_one_or_none()


async def _next_stage_elements(
    db: AsyncSession, permit: WorkPermit
) -> tuple[UUID | None, list[dict[str, Any]], str]:
    """按票据状态构建下一环节卡片元素，返回 (目标用户, elements, 标题)。

    卡片标题与首行都带"待您处理：节点名"，让审批人一眼看出这是新节点
    （票面内容相同，仅靠内容无法区分已推进）。
    """
    from app.modules.safety.service.work_permit_card_forms import _hr, _md

    base: list[dict[str, Any]] = [_md(_ticket_markdown(permit)), _hr()]
    records = await _sign_records_markdown(db, permit)
    if records:
        base.extend([_md(records), _hr()])

    if permit.status == PERMIT_STATUS_PENDING:
        node = await _pending_node(db, permit)
        if node is None:
            return None, [], ""
        # 未指派的确认/验票/验收节点由创建人处理（引擎同口径）；
        # approve 节点提交时已强制指派，未指派视为异常跳过
        recipient = node.assigned_approver_id
        if recipient is None:
            if node.node_kind == "approve" or permit.created_by is None:
                return None, [], ""
            recipient = permit.created_by
        elements = list(base)
        if await _node_signed(db, permit, node):
            elements.append(_md("✔ 本节点已完成手写签名，点「同意」生效"))
        else:
            hint = await _default_sign_hint(db, recipient)
            if hint:
                elements.append(_md(hint))
            else:
                elements.append(_md("_首次审批请点「🖊 手写签名」，之后可默认沿用_"))
        actions: list[dict[str, Any]] = []
        sign_url = await _node_sign_url(permit, node)
        if sign_url:
            actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🖊 手写签名"},
                    "type": "default",
                    "url": sign_url,
                }
            )
        actions.extend(
            [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "同意"},
                    "type": "primary",
                    "value": {
                        "module": "wp_chat",
                        "act": "approve",
                        "permit_id": str(permit.id),
                        "node_id": str(node.id),
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "驳回"},
                    "type": "danger",
                    "value": {
                        "module": "wp_chat",
                        "act": "reject_start",
                        "permit_id": str(permit.id),
                        "node_id": str(node.id),
                        "permit_no": permit.permit_no,
                    },
                },
            ]
        )
        # 卡片 2.0 不支持 action 容器（200861），按钮平铺
        elements.insert(0, _md(f"🔔 **待您处理：{node.node_name}**"))
        elements.extend(actions)
        return (
            recipient,
            elements,
            f"作业票审批 · {node.node_name}（{permit.permit_no}）",
        )

    if permit.status == PERMIT_STATUS_APPROVED:
        verify_node = await _verify_node(db, permit)
        if verify_node is None:
            return await _accept_stage_elements(db, permit, base)
        # 未指派验票节点由创建人处理（引擎同口径）
        verify_recipient = verify_node.assigned_approver_id or permit.created_by
        if verify_recipient is None:
            return await _accept_stage_elements(db, permit, base)
        elements = list(base)
        sign_url = await _node_sign_url(permit, verify_node)
        if sign_url:
            elements.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "🖊 手写签名"},
                    "type": "default",
                    "url": sign_url,
                }
            )
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "确认开工"},
                "type": "primary",
                "value": {
                    "module": "wp_chat",
                    "act": "verify",
                    "permit_id": str(permit.id),
                    "permit_no": permit.permit_no,
                },
            }
        )
        return (
            verify_recipient,
            elements,
            f"作业票验票 · 确认开工（{permit.permit_no}）",
        )

    if permit.status == PERMIT_STATUS_ACTIVE:
        # 作业中：卡片即"活的气体检测记录表"——历史记录 + 录入表单 +
        # 完工验收，每次复检提交后原地 PATCH 追加一行
        elements = list(base)
        elements.append(_md(await _gas_records_markdown(db, permit)))
        elements.append(_hr())
        elements.extend(_gas_form_elements(permit))
        elements.append(_hr())
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "完工验收"},
                "type": "primary",
                "value": {
                    "module": "wp_chat",
                    "act": "accept",
                    "permit_id": str(permit.id),
                    "permit_no": permit.permit_no,
                },
            }
        )
        recipient = await _accept_target(db, permit)
        return (
            recipient,
            elements,
            f"作业票 · 作业中气体检测（{permit.permit_no}）",
        )

    if permit.status == PERMIT_STATUS_COMPLETED:
        if permit.created_by is None:
            return None, [], ""
        # 手机可达优先：完工即生成 PDF 并中转上传到公网网关（180），
        # 手机直接下载；网关未配置/生成上传失败时回退本环境链接（电脑端）
        download_url = await _relay_or_local_pdf_url(db, permit)
        if not download_url:
            return None, [], ""
        elements = list(base)
        elements.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "下载 PDF"},
                "type": "primary",
                "url": download_url,
            }
        )
        return (
            permit.created_by,
            elements,
            f"作业票已完成 · {permit.permit_no}",
        )

    return None, [], ""


async def _relay_or_local_pdf_url(db: AsyncSession, permit: WorkPermit) -> str | None:
    """完工 PDF 下载地址：配置公网网关时生成并中转上传，返回公网链接；
    未配置或生成/上传失败时回退本环境链接（电脑端下载）。"""
    settings = get_settings()
    gateway = (settings.SIGN_RELAY_GATEWAY_BASE or "").rstrip("/")
    relay_key = settings.SIGN_RELAY_KEY or ""
    local_url = await _download_url(permit.id)
    if not gateway or not relay_key:
        return local_url
    try:
        from app.modules.safety.service.work_permit_pdf import render_permit_pdf

        pdf_bytes = await render_permit_pdf(db, permit.id)
        if not pdf_bytes:
            return local_url
        import secrets

        import httpx

        pdf_key = f"{permit.permit_no}-{secrets.token_urlsafe(16)}"
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{gateway}/api/v1/safety/sign-relay/pdf/{pdf_key}",
                headers={
                    "X-Relay-Key": relay_key,
                    "Content-Type": "application/pdf",
                },
                content=pdf_bytes,
            )
        if resp.status_code != 200:
            logger.warning(
                "完工 PDF 中转上传失败: %s %s",
                resp.status_code,
                resp.text[:120],
            )
            return local_url
        return (
            f"{gateway}/api/v1/safety/sign-relay/pdf/{pdf_key}?name={permit.permit_no}"
        )
    except Exception:
        logger.exception("完工 PDF 中转异常，回退本环境链接")
        return local_url


async def _accept_stage_elements(
    db: AsyncSession,
    permit: WorkPermit,
    base: list[dict[str, Any]],
    *,
    with_gas: bool = False,
) -> tuple[UUID | None, list[dict[str, Any]], str]:
    """完工验收卡（无验票票种签批完毕 / 验票开工后）。返回 (审批人, 卡片, 签名链接)。"""
    from app.modules.safety.service.work_permit_card_forms import _md

    recipient = await _accept_target(db, permit)
    if recipient is None:
        return None, [], ""
    elements = list(base)
    if with_gas:
        cycle = _gas_cycle_for(permit)
        if cycle:
            elements.append(
                _md(f"_复检周期 {cycle} 分钟：作业中给机器人发「复检」提交数据。_")
            )
    elements.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "完工验收"},
            "type": "primary",
            "value": {
                "module": "wp_chat",
                "act": "accept",
                "permit_id": str(permit.id),
                "permit_no": permit.permit_no,
            },
        }
    )
    elements.insert(0, _md("🔔 **待您处理：完工验收**"))
    return (
        recipient,
        elements,
        f"作业票验收 · 完工验收（{permit.permit_no}）",
    )


async def _accept_target(db: AsyncSession, permit: WorkPermit) -> UUID | None:
    """完工验收卡目标：验收节点指派人，未指派回退创建人。"""
    node = await _accept_node(db, permit)
    if node is not None and node.assigned_approver_id:
        return node.assigned_approver_id
    return permit.created_by


async def _accept_node(db: AsyncSession, permit: WorkPermit) -> WorkPermitNode | None:
    result = await db.execute(
        select(WorkPermitNode)
        .where(
            WorkPermitNode.permit_id == permit.id,
            WorkPermitNode.round == permit.approval_round,
            WorkPermitNode.node_kind == "accept",
            WorkPermitNode.is_deleted.is_(False),
        )
        .order_by(WorkPermitNode.seq.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _sign_records_markdown(db: AsyncSession, permit: WorkPermit) -> str:
    """签字记录（逐节点：状态、签字人、时间、是否留手写签名）。

    最终卡/审批卡都展示，验收时可核对每一级是谁签的。
    """
    from app.modules.safety.models import WorkPermitSignature

    rows = (
        await db.execute(
            select(WorkPermitNode, User.name)
            .outerjoin(User, User.id == WorkPermitNode.acted_by)
            .where(
                WorkPermitNode.permit_id == permit.id,
                WorkPermitNode.round == permit.approval_round,
                WorkPermitNode.is_deleted.is_(False),
            )
            .order_by(WorkPermitNode.seq)
        )
    ).all()
    if not rows:
        return ""
    sig_node_ids = set(
        (
            await db.execute(
                select(WorkPermitSignature.node_id).where(
                    WorkPermitSignature.permit_id == permit.id,
                    WorkPermitSignature.round == permit.approval_round,
                    WorkPermitSignature.node_id.isnot(None),
                    WorkPermitSignature.is_deleted.is_(False),
                )
            )
        ).scalars()
    )
    marks = {
        "approved": "✅",
        "rejected": "❌",
        "pending": "⏳",
        "waiting": "⏸",
        "skipped": "—",
    }
    lines = ["**签字记录**"]
    for node, acted_name in rows:
        mark = marks.get(node.status, "")
        who = acted_name or ""
        when = node.acted_at.strftime("%m-%d %H:%M") if node.acted_at else ""
        sig = " 🖊" if node.id in sig_node_ids else ""
        suffix = f"（{who} {when}{sig}）" if who or when else ""
        lines.append(f"{node.seq}. {mark} {node.node_name}{suffix}")
    return "\n".join(lines)


async def _gas_records_markdown(db: AsyncSession, permit: WorkPermit) -> str:
    """作业期间气体检测记录表 + 下次复检时间（超期红字警示）。"""

    from zoneinfo import ZoneInfo

    from app.modules.safety.models import WorkPermitGasAnalysis

    bj = ZoneInfo("Asia/Shanghai")

    def _bj(dt_value: datetime) -> datetime:
        """统一转北京时间（库内 UTC 转 +08:00；naive 视为已是北京并附加时区，
        保证后续比较恒为 aware）。"""
        if dt_value.tzinfo is not None:
            return dt_value.astimezone(bj)
        return dt_value.replace(tzinfo=bj)

    rows = (
        (
            await db.execute(
                select(WorkPermitGasAnalysis)
                .where(
                    WorkPermitGasAnalysis.permit_id == permit.id,
                    WorkPermitGasAnalysis.is_deleted.is_(False),
                )
                .order_by(WorkPermitGasAnalysis.sampled_at)
            )
        )
        .scalars()
        .all()
    )
    cycle = _gas_cycle_for(permit)
    header = (
        f"**气体检测记录**（复检周期 {cycle} 分钟）" if cycle else "**气体检测记录**"
    )
    lines = [header]
    for i, r in enumerate(rows, start=1):
        tag = "（作业前）" if str(r.phase) == "pre_work" else ""
        items_txt = "；".join(
            f"{it.get('name')}={it.get('value') or '-'}" for it in (r.items or [])
        )
        shown = _bj(r.sampled_at).strftime("%m-%d %H:%M")
        lines.append(
            f"{i}. {shown}{tag} "
            f"{r.analysis_point or '—'}｜{items_txt}｜"
            f"分析人 {r.analyst_name or '—'}"
        )
    if not rows:
        lines.append("_暂无记录，请在下方表单填写检测结果_")

    # 下次复检时间 = 最近一次采样（无记录则取开工时间）+ 周期
    if cycle:
        base_time = rows[-1].sampled_at if rows else permit.actual_start_time
        if base_time is not None:
            due = _bj(base_time) + timedelta(minutes=cycle)
            now_local = datetime.now(bj)
            if now_local > due:
                lines.append(
                    f"⚠️ **复检已超期**（应不晚于 {due:%m-%d %H:%M}），"
                    "请立即停止作业并复检"
                )
            else:
                lines.append(f"⏰ 下次复检不晚于 {due:%m-%d %H:%M}")
    return "\n".join(lines)


def _gas_form_elements(permit: WorkPermit) -> list[dict[str, Any]]:
    """作业中卡片内嵌的复检录入表单（日期时间选择 + 提交按钮）。"""
    from app.modules.safety.service.work_permit_card_forms import (
        _btn,
        _dt_picker,
        form_submit_name,
    )

    elements: list[dict[str, Any]] = [_md("**填写本次复检结果**（时间点选择器选择）")]
    elements.extend(_dt_picker("gas_time", "取样分析时间"))
    for name, label, placeholder in (
        ("gas_point", "分析部位", "如：釜内"),
        ("gas_name", "代表性气体", "如：可燃气体"),
        ("gas_value", "分析结果", "如：0"),
        ("gas_analyst", "分析人", "姓名"),
    ):
        elements.append(
            {
                "tag": "input",
                "name": name,
                "placeholder": {"tag": "plain_text", "content": placeholder},
                "width": "default",
                "label": {"tag": "plain_text", "content": label},
            }
        )
    submit = _btn(
        "提交本次复检",
        {
            "module": "wp_chat",
            "act": "gas_save",
            "permit_id": str(permit.id),
            "permit_no": permit.permit_no,
        },
        type_="primary",
        form_submit=True,
    )
    submit["name"] = form_submit_name("gas_save", str(permit.id))
    elements.append({"tag": "form", "name": "wp_gas_form", "elements": [submit]})
    return elements


async def refresh_active_gas_card(
    db: AsyncSession, permit_id: UUID, operator_open_id: str | None = None
) -> bool:
    """复检提交后：PATCH 作业中卡片原地追加记录行。

    优先 PATCH 该作业票已推送卡片（验收人缓存）；操作人不同或无缓存时，
    给操作人补发一张最新卡片。返回是否已让用户看到更新后的记录表。
    """
    from app.modules.safety.feishu.notification import update_card
    from app.platform.identity.models import User

    permit = await _resolve_permit(db, permit_id)
    if permit is None or permit.status != PERMIT_STATUS_ACTIVE:
        return False
    _, elements, title = await _next_stage_elements(db, permit)
    if not elements:
        return False

    operator_union: str | None = None
    if operator_open_id:
        row = (
            await db.execute(
                select(User.feishu_union_id).where(
                    User.feishu_open_id == operator_open_id
                )
            )
        ).scalar_one_or_none()
        operator_union = row or None

    recipient_union = (
        await _recipient_union_id(db, recipient)
        if (recipient := await _accept_target(db, permit)) is not None
        else None
    )
    # 操作人恰是当前卡片持有人：原地 PATCH
    if operator_union and operator_union == recipient_union:
        cached = await _cached_approval_card_id(operator_union, permit.id)
        if cached:
            await update_card(
                cached, _card_for(elements, title=title or "作业票 · 作业中")
            )
            return True
    # 其他情况：给操作人补发最新卡片
    if operator_union:
        await send_raw_card_by_union_id(
            operator_union, _card_for(elements, title=title or "作业票 · 作业中")
        )
        return True
    return False


async def active_gas_card(db: AsyncSession, permit: WorkPermit) -> dict[str, Any]:
    """作业中"活的气体检测记录卡"（发「复检」列表与推送共用）。"""
    base: list[dict[str, Any]] = [_md(_ticket_markdown(permit)), _hr()]
    base.append(_md(await _gas_records_markdown(db, permit)))
    base.append(_hr())
    base.extend(_gas_form_elements(permit))
    base.append(_hr())
    base.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": "完工验收"},
            "type": "primary",
            "value": {
                "module": "wp_chat",
                "act": "accept",
                "permit_id": str(permit.id),
                "permit_no": permit.permit_no,
            },
        }
    )
    return _card_for(base, title=f"作业票 · 作业中气体检测（{permit.permit_no}）")


async def _node_signed(
    db: AsyncSession, permit: WorkPermit, node: WorkPermitNode
) -> bool:
    from app.modules.safety.models import WorkPermitSignature

    result = await db.execute(
        select(WorkPermitSignature.id).where(
            WorkPermitSignature.permit_id == permit.id,
            WorkPermitSignature.round == permit.approval_round,
            WorkPermitSignature.node_id == node.id,
            WorkPermitSignature.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none() is not None


async def _default_sign_hint(db: AsyncSession, user_id: UUID) -> str | None:
    """审批人有历史手写签名时，生成默认签名提示文案。"""
    from app.modules.safety.service.work_permit_signatures import (
        latest_person_signature,
    )

    row = await latest_person_signature(db, signer_user_id=user_id)
    if row is None or row.signed_at is None:
        return None
    return f"✔ 点「同意」将默认使用你 {row.signed_at:%m-%d} 的手写签名"


async def _recipient_union_id(db: AsyncSession, user_id: UUID) -> str | None:
    open_map = await _open_id_map(db, [user_id])
    return open_map.get(user_id)


async def _cached_approval_card_id(union_id: str, permit_id: UUID) -> str | None:
    from app.core.redis import cache_get

    return await cache_get(f"wp_approval_card:{union_id}:{permit_id}")


def _gas_cycle_for(permit: WorkPermit) -> int | None:
    from app.modules.safety.service.work_permit_templates import (
        gas_cycle_minutes_for,
    )

    return gas_cycle_minutes_for(permit.permit_type)


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, default=lambda o: str(o))


def _md(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _hr() -> dict[str, Any]:
    return {"tag": "hr"}


def _card_for(
    elements: list[dict[str, Any]],
    *,
    template: str = "blue",
    title: str = "作业票审批",
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        },
        "body": {"elements": elements},
    }


def public_base_url() -> str:
    """免登链接的对外基础地址（前端代理优先，回退后端公网地址）。"""
    settings = get_settings()
    return (settings.FRONTEND_URL or settings.BACKEND_PUBLIC_URL).rstrip("/")


def _ticket_markdown(permit: WorkPermit) -> str:
    """完整票面 markdown（文档版式，与聊天汇总卡同一渲染）。"""
    from app.modules.safety.service.work_permit_card_forms import (
        ticket_document_markdown,
    )

    def _fmt(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value else ""

    measures_yes = [
        str(item.get("key"))
        for item in (permit.safety_measures or [])
        if item.get("status") == "yes"
    ]
    measure_fills = {
        str(item.get("key")): dict(item.get("fills") or {})
        for item in (permit.safety_measures or [])
        if item.get("fills")
    }
    values: dict[str, Any] = {
        "apply_department": permit.apply_department or "",
        "apply_time": _fmt(getattr(permit, "apply_time", None)),
        "work_description": permit.work_description or "",
        "work_location": permit.work_location or "",
        "work_unit": permit.work_unit or "",
        "level": permit.permit_level,
        "planned_start": _fmt(permit.planned_start_time),
        "planned_end": _fmt(permit.planned_end_time),
        "type_data": permit.type_data or {},
        "persons": permit.persons or [],
        "risk": permit.risk_identifications or [],
        "measures": measures_yes,
        "measure_fills": measure_fills,
        "measures_note": "",
        "related_permits": permit.related_legacy_no_text or "",
        "gas": {},
    }
    content = ticket_document_markdown(
        permit.permit_type, values, permit_no=permit.permit_no
    )
    status = PERMIT_STATUS_LABELS.get(permit.status, permit.status)
    # 空行分隔（单换行在飞书 markdown 中被并入上一行）
    return f"{content}\n\n**当前状态** {status}"


async def _node_sign_url(permit: WorkPermit, node: WorkPermitNode) -> str:
    from app.modules.safety.service.work_permit_signatures import (
        build_sign_url,
        create_sign_token,
    )

    token = create_sign_token(
        permit_id=permit.id,
        round_no=permit.approval_round,
        sign_key=node.node_key,
        node_id=node.id,
        open_id="",
        signer_name=node.node_name,
    )
    return build_sign_url(token)


async def _download_url(permit_id: UUID) -> str:
    from app.modules.safety.service.work_permit_signatures import (
        create_download_token,
    )

    return (
        f"{public_base_url()}/api/v1/safety/work-permit-file/"
        f"{create_download_token(permit_id)}"
    )
