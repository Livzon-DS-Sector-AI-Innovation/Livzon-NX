"""安全承诺「飞书卡片填报」处理器。

``card.action.trigger``（module=commitment）：分步表单（车间装置 → 特殊
危险作业 → 隐患与承包商 → 重大危险源与承诺确认）。快动作同步回卡
（3 秒 ACK 约束），提交为重动作 ACK toast + 后台落库 + PATCH 回执。

状态机：``commitment_form:{open_id}:{date}``（Redis JSON，30 分钟过期）：
``{date, step, values}``。业务落库在 ``safety_commitment`` 服务层，
本模块只做事件解析、身份校验与卡片组装。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.core.database import async_session_factory
from app.core.exceptions import AppException
from app.core.redis import cache_delete, cache_get, cache_set
from app.modules.safety.feishu.event_client import on_event
from app.modules.safety.service.commitment_card_forms import (
    TOTAL_STEPS,
    build_receipt_card,
    build_reminder_card,
    build_step_card,
    initial_values,
    merge_step_form_value,
)
from app.modules.safety.service.safety_commitment import (
    get_or_create_report,
    save_enterprise_status_from_feishu,
)

logger = logging.getLogger(__name__)

_FORM_TTL_SECONDS = 1800


def _state_key(open_id: str, report_date: str) -> str:
    return f"commitment_form:{open_id}:{report_date}"


def _parse_event_action(event: dict[str, Any]) -> dict[str, Any] | None:
    action_value = event.get("action", {})
    value_raw = action_value.get("value", "{}")
    try:
        value = (
            json.loads(value_raw) if isinstance(value_raw, str) else value_raw
        )
    except (json.JSONDecodeError, TypeError):
        value = None
    if isinstance(value, dict) and value.get("module") == "commitment":
        return value
    # form_submit 按钮回调不回传 value，动作编码在按钮 name（cm|act|date|step）
    name = str(action_value.get("name") or "")
    parts = name.split("|")
    if len(parts) >= 4 and parts[0] == "cm":
        return {
            "module": "commitment",
            "act": parts[1],
            "date": parts[2],
            "step": parts[3],
        }
    return None


def _operator_open_id(event: dict[str, Any]) -> str:
    operator = event.get("operator") or {}
    open_id = str(operator.get("open_id") or "")
    if not open_id:
        open_id = str(
            (event.get("event", {}).get("operator") or {}).get("open_id") or ""
        )
    return open_id


def _raw_card_response(card: dict[str, Any]) -> dict[str, Any]:
    """ACK 中返回 raw 卡片，防止客户端回流旧样式。"""
    return {"card": {"type": "raw", "data": card}}


async def _ensure_bound_user(db: Any, open_id: str) -> None:
    """填报人必须是已绑定平台用户的飞书账号（权限入口）。"""
    from sqlalchemy import select

    from app.platform.identity.models import User

    result = await db.execute(
        select(User).where(User.feishu_open_id == open_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise AppException(
            status_code=403,
            message="当前飞书账号未绑定平台用户，请联系管理员绑定后填报",
        )


async def _start_form(db: Any, open_id: str, report_date: str) -> dict[str, Any]:
    await _ensure_bound_user(db, open_id)
    report, _created = await get_or_create_report(db, report_date)
    state = {
        "date": report_date,
        "step": 1,
        "values": initial_values(report.enterprise_status or {}),
    }
    await cache_set(
        _state_key(open_id, report_date),
        json.dumps(state, ensure_ascii=False),
        ex=_FORM_TTL_SECONDS,
    )
    values = state.get("values")
    values = values if isinstance(values, dict) else {}
    return build_step_card(report_date, 1, values)


async def _load_state(open_id: str, report_date: str) -> dict[str, Any] | None:
    raw = await cache_get(_state_key(open_id, report_date))
    if not raw:
        return None
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return state if isinstance(state, dict) else None


def _to_enterprise_status(values: dict[str, Any]) -> dict[str, Any]:
    """表单值 → enterprise_status JSONB（yes/no → True/False，unknown → None）。"""
    tri = {"yes": True, "no": False}
    special = values.get("special_work") or {}

    def _tri(key: str) -> bool | None:
        choice = values.get(key)
        return tri.get(choice) if isinstance(choice, str) else None

    return {
        "workshop_total": values.get("workshop_total", 0),
        "workshop_running": values.get("workshop_running", 0),
        "workshop_stopped": values.get("workshop_stopped", 0),
        "workshop_maintenance": values.get("workshop_maintenance", 0),
        "trial_production_count": values.get("trial_production_count", 0),
        "startup_count": values.get("startup_count", 0),
        "shutdown_count": values.get("shutdown_count", 0),
        "special_work_total": values.get("special_work_total", 0),
        "special_work": {
            "hot_work_level1": special.get("hot_work_level1", 0),
            "hot_work_level2": special.get("hot_work_level2", 0),
            "height_work": special.get("height_work", 0),
            "confined_space": special.get("confined_space", 0),
            "other": special.get("other", 0),
        },
        "hazard_count": values.get("hazard_count", 0),
        "hazard_rectified": _tri("hazard_rectified"),
        "hazard_temp_measures": _tri("hazard_temp_measures"),
        "contractor_work": bool(_tri("contractor_work") or False),
        "contractor_trained": _tri("contractor_trained"),
        "major_hazard_safe": _tri("major_hazard_safe"),
        "responsibility_implemented": _tri("responsibility_implemented"),
        "person_main": values.get("person_main", ""),
        "person_tech": values.get("person_tech", ""),
        "person_ops": values.get("person_ops", ""),
    }


async def _submit_form(
    open_id: str, event: dict[str, Any], value: dict[str, Any]
) -> None:
    """重动作：最终步提交 → 承诺确认校验 → 落库 → PATCH 回执卡。"""
    report_date = str(value.get("date") or "")
    form_value: dict[str, Any] = {}
    try:
        form_value = dict(event.get("action", {}).get("form_value") or {})
    except (TypeError, ValueError):
        form_value = {}
    try:
        state = await _load_state(open_id, report_date)
        if state is None:
            raise AppException(message="填报会话已过期，请从提醒卡重新发起")
        values = merge_step_form_value(
            dict(state.get("values") or {}), TOTAL_STEPS, form_value
        )
        if values.get("commitment_confirm") != "yes":
            raise AppException(message="承诺确认必须选择「是」才能提交")
        enterprise_status = _to_enterprise_status(values)
        async with async_session_factory() as db:
            await _ensure_bound_user(db, open_id)
            report = await save_enterprise_status_from_feishu(
                db, report_date, enterprise_status
            )
            status = (
                "已提交，今日承诺公告已发布"
                if report.status == "published"
                else "已提交，待负责人在网页端发布承诺公告"
            )
            hint = (
                f"包保责任人：主要负责人 {values.get('person_main') or '—'} / "
                f"技术负责人 {values.get('person_tech') or '—'} / "
                f"操作负责人 {values.get('person_ops') or '—'}"
            )
            receipt = build_receipt_card(report_date, status, hint)
        await cache_delete(_state_key(open_id, report_date))
        await _patch_open_message(event, receipt)
    except AppException as exc:
        await _reply_error(open_id, str(exc.message or exc))
    except Exception:
        logger.exception("安全承诺填报提交失败: date=%s", report_date)
        await _reply_error(open_id, "提交失败，请稍后重试或联系管理员")


async def _reply_error(open_id: str, text: str) -> None:
    from app.modules.safety.feishu.notification import send_user_card

    await send_user_card(open_id, "安全承诺填报", text[:200])


async def _patch_open_message(
    event: dict[str, Any], card: dict[str, Any]
) -> None:
    from app.modules.safety.feishu.notification import update_card

    message_id = str(event.get("context", {}).get("open_message_id") or "")
    if message_id:
        await update_card(message_id, card)


@on_event("card.action.trigger")
async def handle_commitment_card_action(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    """commitment 卡片动作入口；非本模块卡片返回 None。"""
    value = _parse_event_action(event)
    if value is None:
        return None
    act = str(value.get("act") or "")
    open_id = _operator_open_id(event)
    report_date = str(value.get("date") or "")
    if not report_date:
        return {"toast": {"type": "error", "content": "参数缺失"}}

    if act == "submit":
        asyncio.create_task(_submit_form(open_id, event, value))
        return {
            "toast": {"type": "success", "content": "提交中…"},
            "card": {"type": "raw"},
        }

    if act in ("start_form", "step_save", "form_prev", "form_cancel"):
        try:
            if act == "form_cancel":
                await cache_delete(_state_key(open_id, report_date))
                from app.modules.safety.service.commitment_notify import (
                    COMMITMENT_PAGE_PATH,
                    public_base_url,
                )

                card = build_reminder_card(
                    report_date,
                    "已取消本次填报，可点击「开始填报」重新发起。",
                    f"{public_base_url()}{COMMITMENT_PAGE_PATH}",
                )
                return {**_raw_card_response(card), "toast": {"type": "success"}}

            async with async_session_factory() as db:
                state = await _load_state(open_id, report_date)
                step = int(value.get("step") or (state or {}).get("step") or 1)
                if act == "start_form" or state is None:
                    card = await _start_form(db, open_id, report_date)
                    return {**_raw_card_response(card), "toast": {"type": "success"}}

                await _ensure_bound_user(db, open_id)
                values = dict(state.get("values") or {})
                if act == "step_save":
                    form_value = event.get("action", {}).get("form_value") or {}
                    values = merge_step_form_value(
                        values, step, dict(form_value)
                    )
                    next_step_no = min(step + 1, TOTAL_STEPS)
                else:  # form_prev
                    next_step_no = max(step - 1, 1)
                new_state = {
                    "date": report_date,
                    "step": next_step_no,
                    "values": values,
                }
                await cache_set(
                    _state_key(open_id, report_date),
                    json.dumps(new_state, ensure_ascii=False),
                    ex=_FORM_TTL_SECONDS,
                )
                card = build_step_card(report_date, next_step_no, values)
            return {**_raw_card_response(card), "toast": {"type": "success"}}
        except AppException as exc:
            return {
                "toast": {
                    "type": "error",
                    "content": str(exc.message or "处理失败")[:120],
                },
                "card": {"type": "raw"},
            }
        except Exception:
            logger.exception("安全承诺卡片动作处理失败: act=%s", act)
            return {
                "toast": {"type": "error", "content": "处理失败，请稍后重试"},
                "card": {"type": "raw"},
            }
    return None


__all__ = ["handle_commitment_card_action"]
