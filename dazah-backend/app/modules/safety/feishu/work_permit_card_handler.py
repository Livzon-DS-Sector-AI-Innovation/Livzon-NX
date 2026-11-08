"""8 大作业票飞书卡片回调：处理「同意 / 驳回」按钮点击。

卡片按钮 value 携带 {module: "work_permit", action, permit_id, node_id}；
处理流程：
1. Redis 去重（同一节点+动作+操作人 30 秒内只处理一次）；
2. 按 operator open_id 解析平台账号并校验该节点指派给其处理
   （引擎内 _resolve_actor_guard 复核，管理员放行）；
3. 复用 work_permit 服务引擎执行签批/驳回（含审计与流转通知）；
4. ACK 返回 toast + raw 卡片防回流，后台 PATCH 原消息更新按钮态。

驳回意见无法在快捷卡片上输入，统一落「飞书卡片驳回」并由通知携带
提示到平台补充意见（与 HR 卡片审批的处理口径一致）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.redis import cache_get, cache_set
from app.modules.safety.feishu.event_client import on_event
from app.modules.safety.service import work_permit as permit_service
from app.modules.safety.service.work_permit_notify import (
    notify_after_transition,
)
from app.platform.identity.models import User

logger = logging.getLogger(__name__)

_CARD_REJECT_OPINION = "（飞书快捷卡片驳回）请登录平台查看意见并修改后重新提交"


def _parse_value(event: dict[str, Any]) -> dict[str, Any] | None:
    action_value = event.get("action", {})
    value_raw = action_value.get("value", "{}")
    try:
        value = (
            json.loads(value_raw) if isinstance(value_raw, str) else value_raw
        )
    except (json.JSONDecodeError, TypeError):
        logger.warning("作业票卡片 value 解析失败: %s", value_raw)
        return None
    if not isinstance(value, dict) or value.get("module") != "work_permit":
        return None
    return value


async def _resolve_operator(
    db: AsyncSession, open_id: str
) -> User | None:
    result = await db.execute(
        select(User).where(User.feishu_open_id == open_id)
    )
    user: User | None = result.scalar_one_or_none()
    return user


def _processed_card(permit_no: str, node_name: str, action: str) -> dict[str, Any]:
    action_label = "已同意" if action == "approve" else "已驳回"
    template = "green" if action == "approve" else "red"
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"作业票 {permit_no}"},
            "template": template,
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    f"节点「{node_name}」{action_label}。\n"
                    "请到平台查看作业票最新进展。"
                ),
            }
        ],
    }


async def _patch_card_async(
    open_message_id: str, card: dict[str, Any], permit_no: str
) -> None:
    """后台 PATCH 原卡片（兜底，ACK 中的 raw 卡片为主）。"""
    try:
        from app.modules.safety.feishu.notification import update_card

        await update_card(open_message_id, card)
    except Exception:
        logger.exception(
            "作业票卡片 PATCH 失败: msg=%s permit=%s",
            open_message_id,
            permit_no,
        )


@on_event("card.action.trigger")
async def handle_work_permit_card_action(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    """作业票卡片按钮点击入口；非本模块卡片返回 None 交给其他处理器。"""
    value = _parse_value(event)
    if value is None:
        return None

    action = value.get("action", "")
    if action not in ("approve", "reject"):
        return None
    permit_id = value.get("permit_id", "")
    node_id = value.get("node_id", "")
    permit_no = value.get("permit_no", "")
    operator_open_id = (
        event.get("operator", {}).get("open_id")
        or event.get("event", {}).get("operator", {}).get("open_id")
        or ""
    )
    if not permit_id or not node_id or not operator_open_id:
        logger.warning(
            "作业票卡片缺少参数: permit=%s node=%s operator=%s",
            bool(permit_id),
            bool(node_id),
            bool(operator_open_id),
        )
        return {"toast": {"type": "error", "content": "卡片参数缺失"}}

    dedupe_key = f"safety:wp_card:{node_id}:{action}:{operator_open_id}"
    if await cache_get(dedupe_key):
        return {"toast": {"type": "info", "content": "正在处理，请勿重复点击"}}
    await cache_set(dedupe_key, "1", ex=30)

    node_name = ""
    try:
        async with async_session_factory() as db:
            operator = await _resolve_operator(db, operator_open_id)
            if operator is None:
                return {
                    "toast": {
                        "type": "error",
                        "content": "当前飞书账号未绑定平台用户，请在平台操作",
                    }
                }
            if action == "approve":
                permit = await permit_service.approve_node(
                    db, permit_id, node_id, "（飞书卡片同意）", operator
                )
            else:
                permit = await permit_service.reject_node(
                    db, permit_id, node_id, _CARD_REJECT_OPINION, operator
                )
            node_name = await _load_node_name(db, node_id)
            await db.commit()
            await notify_after_transition(db, permit)
    except Exception as exc:
        logger.exception(
            "作业票卡片操作失败: permit=%s node=%s action=%s",
            permit_id,
            node_id,
            action,
        )
        message = str(exc) or "处理失败"
        return {
            "toast": {"type": "error", "content": message[:120]},
            "card": {"type": "raw"},
        }

    card = _processed_card(permit_no, node_name or "审批节点", action)
    open_message_id = event.get("context", {}).get("open_message_id", "")
    if open_message_id:
        asyncio.create_task(_patch_card_async(open_message_id, card, permit_no))
    label = "同意" if action == "approve" else "驳回"
    return {
        "toast": {"type": "success", "content": f"已{label} {permit_no}"},
        "card": {"type": "raw", "data": card},
    }


async def _load_node_name(db: AsyncSession, node_id: str) -> str:
    from uuid import UUID

    from app.modules.safety.models import WorkPermitNode

    try:
        result = await db.execute(
            select(WorkPermitNode.node_name).where(
                WorkPermitNode.id == UUID(node_id)
            )
        )
        return result.scalar_one_or_none() or ""
    except ValueError:
        return ""


__all__ = ["handle_work_permit_card_action"]
