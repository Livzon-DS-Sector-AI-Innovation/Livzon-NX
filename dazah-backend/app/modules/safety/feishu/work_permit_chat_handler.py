"""8 大作业票「飞书机器人」交互处理器：聊天发起 + 卡片全流程回调。

入口（均经安全模块独立飞书应用 WS 长连接，见 event_client）：
- ``im.message.receive_v1``（仅 p2p 文本）：票种关键词 → 分步表单卡；
  「菜单」/未知 → 菜单卡；「复检」→ 作业中气体票列表 + 复检录入卡；
  「取消」→ 清表单状态回菜单。
- ``card.action.trigger``（module=wp_chat）：分步表单 / 汇总签名（含默认
  签名复用）/ 提交 / 审批（同意·驳回意见表单）/ 验票 / 验收 / 复检录入
  的全量按钮分发。业务引擎复用 ``work_permit`` 服务与 ``ChatFlowService``。

快动作（2.9s 内完成业务）：start_form / step_save / form_prev / form_cancel /
menu / my_drafts / use_default_sign / reject_start / noop
重动作（ACK 后台执行）：submit / approve / reject_submit / verify / accept /
gas_save（Redis 30s 防重）。

**反馈通道**：本应用卡片回调经 card.action.trigger 事件（EVENT 帧）送达，
飞书忽略其 ACK 响应中的卡片更新与 toast（同设备模块结论），因此所有
视觉反馈均通过 PATCH 原消息（context.open_message_id）呈现；ACK 响应
仍按 raw 卡返回以兼容将来切换 CARD 帧模式。错误提示走私聊 DM 兜底。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import cache_get, cache_set
from app.modules.safety.feishu.event_client import on_event
from app.modules.safety.service.work_permit_card_forms import (
    build_menu_card,
    build_reject_card,
)
from app.modules.safety.service.work_permit_chat_flow import (
    ChatFlowService,
    parse_intent,
)
from app.modules.safety.service.work_permit_templates import PERMIT_TEMPLATES

logger = logging.getLogger(__name__)

_DEDUPE_TTL_SECONDS = 30

_FAST_ACTS = frozenset(
    {
        "menu",
        "my_drafts",
        "start_form",
        "step_save",
        "form_prev",
        "form_cancel",
        "use_default_sign",
        "reject_start",
        "toggle_risk",
        "toggle_measure",
        "set_level",
        "search_role",
        "choose_cert",
        "person_prev",
        "clear_search",
    }
)
_HEAVY_ACTS = frozenset(
    {"submit", "approve", "reject_submit", "verify", "accept", "gas_save"}
)


# ── 事件解析 ──


def _parse_value(event: dict[str, Any]) -> dict[str, Any] | None:
    action = event.get("action", {})
    value_raw = action.get("value", "{}")
    try:
        value = json.loads(value_raw) if isinstance(value_raw, str) else value_raw
    except (json.JSONDecodeError, TypeError):
        value = None
    if isinstance(value, dict) and value.get("module") == "wp_chat":
        return value
    # form_submit 按钮回调不回传 value，动作编码在按钮 name（wp|act|...）
    return _value_from_submit_name(str(action.get("name") or ""))


def _value_from_submit_name(name: str) -> dict[str, Any] | None:
    parts = name.split("|")
    if len(parts) < 2 or parts[0] != "wp":
        return None
    act = parts[1]
    value: dict[str, Any] = {"module": "wp_chat", "act": act}
    if act in ("step_save", "submit") and len(parts) >= 4:
        value["type"] = parts[2]
        value["step"] = parts[3]
        if act == "step_save" and len(parts) >= 5:
            value["person_role_idx"] = parts[4]
    elif act == "submit" and len(parts) >= 3:
        value["type"] = parts[2]
    elif act == "reject_submit" and len(parts) >= 4:
        value["permit_id"] = parts[2]
        value["node_id"] = parts[3]
    elif act == "gas_save" and len(parts) >= 3:
        value["permit_id"] = parts[2]
    return value


def _operator_open_id(event: dict[str, Any]) -> str:
    operator = event.get("operator") or {}
    open_id = str(operator.get("open_id") or "")
    if not open_id:
        open_id = str(
            (event.get("event", {}).get("operator") or {}).get("open_id") or ""
        )
    return open_id


def _operator_union_id(event: dict[str, Any]) -> str:
    """union_id 跨应用一致，作为平台账号匹配首选（open_id 是应用维度的）。"""
    operator = event.get("operator") or {}
    union_id = str(operator.get("union_id") or "")
    if not union_id:
        sender = (event.get("sender") or {}).get("sender_id") or {}
        union_id = str(sender.get("union_id") or "")
    return union_id


def _form_value(event: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = event.get("action", {}).get("form_value") or {}
    except (TypeError, ValueError):
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _message_id(event: dict[str, Any]) -> str:
    return str((event.get("context") or {}).get("open_message_id") or "")


def _uuid(value: Any, *, field: str) -> UUID:
    try:
        return UUID(str(value or ""))
    except ValueError:
        raise AppException(message=f"卡片参数错误（{field}）") from None


def _toast(toast_type: str, content: str) -> dict[str, Any]:
    return {
        "toast": {"type": toast_type, "content": content[:120]},
        "card": {"type": "raw"},
    }


def _card_response(card: dict[str, Any], content: str = "") -> dict[str, Any]:
    resp: dict[str, Any] = {"card": {"type": "raw", "data": card}}
    if content:
        resp["toast"] = {"type": "success", "content": content[:120]}
    return resp


def _text_card(title: str, content: str, template: str = "blue") -> dict[str, Any]:
    return {
        "schema": "2.0",
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": template,
        },
        "body": {"elements": [{"tag": "markdown", "content": content}]},
    }


# ── 聊天文本入口 ──


@on_event("im.message.receive_v1")
async def handle_work_permit_message(event: dict[str, Any]) -> None:
    """p2p 文本意图入口（群聊忽略）。

    event_client 的 ``_dispatch_event`` 传入的是已剥掉外层 ``event`` 键的
    内层载荷；兼容两种形态以防直接复用原始事件。
    """
    event_data = event.get("event") or event
    message = event_data.get("message") or {}
    if message.get("message_type") != "text":
        return
    if message.get("chat_type") not in ("p2p", None, ""):
        return
    sender = (event_data.get("sender") or {}).get("sender_id") or {}
    open_id = str(sender.get("open_id") or "")
    try:
        text = str(
            (json.loads(message.get("content") or "{}") or {}).get("text") or ""
        ).strip()
    except (json.JSONDecodeError, TypeError):
        return
    if not text or not open_id:
        return

    logger.info("wp_chat 聊天消息: open_id=%s text=%s", open_id, text[:40])
    from app.modules.safety.service.work_permit_notify import send_raw_card

    union_id = _operator_union_id(event_data)
    try:
        card = await _route_text(open_id, union_id, text)
        if card is not None:
            await send_raw_card(open_id, card)
    except AppException as exc:
        await _reply_error(open_id, str(exc.message or exc))
    except Exception:
        logger.exception("wp_chat 聊天消息处理失败: text=%s", text[:40])
        await _reply_error(open_id, "处理出错，请发送「菜单」重新开始。")


async def _route_text(open_id: str, union_id: str, text: str) -> dict[str, Any] | None:
    intent = parse_intent(text)
    act = intent.get("act", "")
    if act in ("start_form", "gas_list", "cancel"):
        async with async_session_factory() as db:
            flow = ChatFlowService(db, open_id=open_id, union_id=union_id)
            if act == "start_form":
                return await flow.start_form(str(intent.get("permit_type") or ""))
            if act == "gas_list":
                from app.modules.safety.service.work_permit_notify import (
                    active_gas_card,
                    send_raw_card,
                )

                permits = await flow.my_gas_permits()
                if not permits:
                    return _text_card(
                        "气体复检",
                        "当前没有作业中、需周期复检的作业票。发「菜单」查看其他操作。",
                    )
                for permit in permits:
                    await send_raw_card(open_id, await active_gas_card(db, permit))
                return None
            # cancel
            for permit_type in PERMIT_TEMPLATES:
                await flow.clear_state(permit_type)
            return _text_card("已取消", "已取消进行中的填写。", "grey")
    return build_menu_card(open_id)


async def _reply_error(open_id: str, text: str) -> None:
    from app.modules.safety.feishu.notification import send_user_card

    await send_user_card(open_id, "作业票助手", text[:200])


# ── 卡片按钮回调分发 ──


@on_event("card.action.trigger")
async def handle_wp_chat_card_action(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    """wp_chat 卡片动作入口；非本模块卡片返回 None 交给其他处理器。"""
    value = _parse_value(event)
    if value is None:
        return None
    act = str(value.get("act") or "")
    if not act or act == "noop":
        return None
    open_id = _operator_open_id(event)
    if not open_id:
        return _toast("error", "无法识别操作者，请重新点击")
    union_id = _operator_union_id(event)

    # 全部动作统一"立即 ACK + 后台处理"：飞书 EVENT 通道对卡片回调有
    # 2.9s 同步窗口，超时会取消整个处理任务（表现为点击无反应）；
    # 证书名单加载 + 20KB 大卡 PATCH 可能超过窗口，故一律后台执行，
    # 结果通过 PATCH 原消息 / 私信呈现。
    dedupe_key = _dedupe_key(act, open_id, value)
    if await cache_get(dedupe_key):
        return _toast("info", "正在处理，请勿重复点击")
    await cache_set(dedupe_key, "1", ex=_DEDUPE_TTL_SECONDS)
    if act in _FAST_ACTS:
        asyncio.create_task(_run_fast_action(act, open_id, union_id, value, event))
    elif act in _HEAVY_ACTS:
        asyncio.create_task(_run_heavy_action(act, open_id, union_id, value, event))
    else:
        return None
    return _toast("success", "正在处理…")


def _dedupe_key(act: str, open_id: str, value: dict[str, Any]) -> str:
    payload = (
        value.get("permit_id")
        or value.get("node_id")
        or value.get("type")
        or value.get("step")
        or ""
    )
    return f"safety:wp_chat:{act}:{open_id}:{payload}"


async def _run_fast_action(
    act: str,
    open_id: str,
    union_id: str,
    value: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    """快动作：2.9s 内完成业务，卡片经 PATCH 原消息呈现（EVENT 通道约束）。"""
    # 纯卡片动作不碰数据库
    if act == "menu":
        card = build_menu_card(open_id)
        asyncio.create_task(_patch_open_message(event, card))
        return _card_response(card)
    if act == "reject_start":
        card = build_reject_card(
            str(value.get("permit_id") or ""),
            str(value.get("node_id") or ""),
            str(value.get("permit_no") or ""),
        )
        asyncio.create_task(_patch_open_message(event, card))
        return _card_response(card)

    permit_type = str(value.get("type") or "")
    message_id = _message_id(event)
    try:
        async with async_session_factory() as db:
            flow = ChatFlowService(db, open_id=open_id, union_id=union_id)
            if act == "my_drafts":
                card = await flow.my_drafts(message_id=_message_id(event))
            elif act == "start_form":
                card = await flow.start_form(permit_type)
            elif act == "form_cancel":
                card = await flow.cancel(permit_type)
            elif act == "form_prev":
                card = await flow.form_prev(
                    permit_type, int(value.get("prev_step") or 1)
                )
            elif act in ("toggle_risk", "toggle_measure"):
                field = "risk" if act == "toggle_risk" else "measures"
                card = await flow.toggle_check(
                    permit_type, field, str(value.get("key") or "")
                )
            elif act == "set_level":
                card = await flow.set_level(permit_type, str(value.get("level") or ""))
            elif act == "search_role":
                search_role_key = str(value.get("search_role") or "")
                card = await flow.search_role_persons(
                    permit_type,
                    search_role_key,
                    str(_form_value(event).get(f"person_kw__{search_role_key}") or ""),
                )
            elif act == "choose_cert":
                card = await flow.choose_cert_person(
                    permit_type,
                    str(value.get("role") or ""),
                    str(value.get("cert_id") or ""),
                )
            elif act == "person_prev":
                card = await flow.person_prev(
                    permit_type, int(value.get("person_role_idx") or 0)
                )
            elif act == "clear_search":
                card = await flow.clear_person_search(permit_type)
            elif act == "use_default_sign":
                card = await flow.use_default_sign(
                    permit_type, str(value.get("sign_key") or "")
                )
            else:  # step_save
                idx_raw = value.get("person_role_idx")
                card = await flow.save_step(
                    permit_type,
                    int(value.get("step") or 1),
                    _form_value(event),
                    message_id=message_id,
                    person_role_idx=(
                        int(str(idx_raw)) if idx_raw not in (None, "") else None
                    ),
                )
        asyncio.create_task(_patch_open_message(event, card))
        toast = "已使用默认签名" if act == "use_default_sign" else ""
        return _card_response(card, toast)
    except AppException as exc:
        if getattr(exc, "status_code", None) == 410:
            # 表单过期：回菜单卡引导重新发起
            card = build_menu_card(open_id)
            asyncio.create_task(_patch_open_message(event, card))
            return _card_response(card, "表单已过期，请重新发起")
        await _reply_error(open_id, str(exc.message or "处理失败"))
        return _toast("error", str(exc.message or "处理失败"))
    except Exception:
        logger.exception("wp_chat 快动作失败: act=%s", act)
        await _reply_error(open_id, "处理失败，请稍后重试")
        return _toast("error", "处理失败，请稍后重试")


async def _run_heavy_action(
    act: str,
    open_id: str,
    union_id: str,
    value: dict[str, Any],
    event: dict[str, Any],
) -> None:
    """重动作：后台执行引擎流转，成功后 PATCH 原消息为回执卡。

    失败时不 PATCH 原消息（保留按钮/表单以便重试），另发 DM 错误提示。
    """
    try:
        receipt: dict[str, Any] | None = None
        async with async_session_factory() as db:
            flow = ChatFlowService(db, open_id=open_id, union_id=union_id)
            if act == "submit":
                receipt = await flow.submit(
                    str(value.get("type") or ""), _form_value(event)
                )
            elif act == "approve":
                receipt = await flow.approve(
                    _uuid(value.get("permit_id"), field="permit_id"),
                    _uuid(value.get("node_id"), field="node_id"),
                )
            elif act == "reject_submit":
                opinion = str(_form_value(event).get("opinion") or "").strip()
                if not opinion:
                    raise AppException(message="请填写驳回意见后再提交")
                receipt = await flow.reject(
                    _uuid(value.get("permit_id"), field="permit_id"),
                    _uuid(value.get("node_id"), field="node_id"),
                    opinion,
                )
            elif act == "verify":
                receipt = await flow.verify(
                    _uuid(value.get("permit_id"), field="permit_id")
                )
            elif act == "accept":
                receipt = await flow.accept(
                    _uuid(value.get("permit_id"), field="permit_id")
                )
            elif act == "gas_save":
                receipt = await flow.save_gas(
                    _uuid(value.get("permit_id"), field="permit_id"),
                    _form_value(event),
                )
                # 记录表卡片原地追加一行，成功则不再发独立回执
                from app.modules.safety.service.work_permit_notify import (
                    refresh_active_gas_card,
                )

                if await refresh_active_gas_card(
                    db,
                    _uuid(value.get("permit_id"), field="permit_id"),
                    open_id,
                ):
                    receipt = None
        if receipt is not None:
            await _patch_open_message(event, receipt)
    except AppException as exc:
        await _reply_error(open_id, str(exc.message or "处理失败"))
    except Exception:
        logger.exception("wp_chat 重动作失败: act=%s value=%s", act, value)
        await _reply_error(open_id, "处理失败，请稍后重试；持续失败请联系管理员")


async def _patch_open_message(event: dict[str, Any], card: dict[str, Any]) -> None:
    from app.modules.safety.feishu.notification import update_card

    message_id = _message_id(event)
    if not message_id:
        return
    try:
        await update_card(message_id, card)
    except Exception:
        logger.exception("wp_chat 回执卡 PATCH 失败: msg=%s", message_id)


__all__ = ["handle_wp_chat_card_action", "handle_work_permit_message"]
