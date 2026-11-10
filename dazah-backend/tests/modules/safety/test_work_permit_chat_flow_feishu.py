"""8 大作业票飞书聊天链路测试。

覆盖：卡片构建器（分步/汇总签名门控/驳回/复检/菜单）、文本意图路由、
卡片回调分发器（快/重动作、防重、module 过滤、回执 PATCH）、手写签名
按人默认复用、聊天全流程端到端（提交→逐级签批→完工验收→PDF 推卡）、
事件分发首非 None 语义。不连真实飞书（发送/更新均 mock）。
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.models import (
    SafetyFeishuAppSettings,
    WorkPermit,
    WorkPermitApproverConfig,
    WorkPermitNode,
    WorkPermitSignature,
)
from app.modules.safety.service import work_permit as permit_service
from app.modules.safety.service import work_permit_card_forms as forms
from app.modules.safety.service.work_permit_chat_flow import (
    ChatFlowService,
    parse_intent,
)
from app.modules.safety.service.work_permit_signatures import (
    latest_person_signature,
    reuse_or_none,
)
from app.platform.identity.models import User

_MARK = "WP聊天测试"


def _card(title: str) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "body": {"elements": []},
    }


def _card_event(
    value: dict[str, Any],
    *,
    operator: str = "ou-op",
    form_value: dict[str, Any] | None = None,
    message_id: str = "om_1",
) -> dict[str, Any]:
    action: dict[str, Any] = {"value": json.dumps(value, ensure_ascii=False)}
    if form_value is not None:
        action["form_value"] = form_value
    return {
        "action": action,
        "operator": {"open_id": operator},
        "context": {"open_message_id": message_id},
    }


def _all_button_values(card: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    elements = (card.get("body") or {}).get("elements") or card.get("elements") or []

    def _walk(items: list[Any]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if isinstance(value, dict):
                values.append(value)
            for key in ("actions", "elements"):
                if isinstance(item.get(key), list):
                    _walk(item[key])

    _walk(elements)
    return values


# ── 卡片构建器 ──


def test_step_cards_carry_module_and_act() -> None:
    values = forms.base_form_values("blind_plate", None)
    # 第①②④⑤⑥步为表单卡（④风险逐行、⑤措施逐行+填空、⑥选人）
    for step in (1, 2, 4, 5, 6):
        card = forms.build_step_card("blind_plate", step, values, "ou-x")
        assert card["schema"] == "2.0"
        tags = [el.get("tag") for el in card["body"]["elements"]]
        assert "form" in tags
    button_values = _all_button_values(
        forms.build_step_card("blind_plate", 1, values, "ou-x")
    )
    assert any(
        v.get("module") == "wp_chat"
        and v.get("act") == "step_save"
        and v.get("type") == "blind_plate"
        and v.get("step") == 1
        for v in button_values
    )
    cancel = [v for v in button_values if v.get("act") == "form_cancel"]
    assert cancel, "分步卡应带取消按钮"

    def _form_names(permit_type: str, step: int) -> list[str]:
        card = forms.build_step_card(
            permit_type, step, forms.base_form_values(permit_type, None), "ou-x"
        )
        form_el = [el for el in card["body"]["elements"] if el.get("tag") == "form"][0]
        return [
            str(el.get("name"))
            for el in form_el["elements"]
            if el.get("tag") in ("select_static", "input", "select_person")
        ]

    # ④ 风险逐行涉及/不涉及
    risk_names = _form_names("hot_work", 4)
    assert any(n.startswith("risk__") for n in risk_names), "风险辨识应逐行选择"
    assert not any(n.startswith("m__") for n in risk_names)
    # ⑤ 措施逐行是/否 + 下划线填空
    measure_names = _form_names("hot_work", 5)
    assert any(n.startswith("m__") for n in measure_names), "安全措施应逐行选择"
    assert any(
        n.startswith("f__hw_disconnect_pipes__") for n in measure_names
    ), "下划线条文应附数量填空"
    # ⑥ 审批人选人
    assign_names = _form_names("hot_work", 6)
    assert any(
        n.startswith("assign_") for n in assign_names
    ), "审批人指派步应含选人组件"


def test_summary_card_sign_gating_and_default_button() -> None:
    values = forms.base_form_values("blind_plate", None)
    urls = {
        key: f"https://x/sign/{key}"
        for key in ("initiator", "briefer", "briefer_receiver")
    }

    unsigned = forms.build_summary_card(
        "blind_plate", "none", values, {}, urls
    )
    button_values = _all_button_values(unsigned)
    assert any(v.get("act") == "use_default_sign" for v in button_values), (
        "未签名行应提供「用我的默认签名」按钮"
    )
    assert not any(v.get("act") == "submit" for v in button_values), (
        "签名未齐时不得出现提交按钮"
    )

    signed = forms.build_summary_card(
        "blind_plate",
        "none",
        values,
        {key: "img" for key in urls},
        urls,
    )
    signed_values = _all_button_values(signed)
    assert any(v.get("act") == "submit" for v in signed_values)
    assert not any(v.get("act") == "use_default_sign" for v in signed_values)


def test_reject_and_gas_cards_carry_act() -> None:
    reject_values = _all_button_values(
        forms.build_reject_card("pid-1", "nid-1", "DH-20261109-001")
    )
    assert any(
        v.get("module") == "wp_chat"
        and v.get("act") == "reject_submit"
        and v.get("permit_id") == "pid-1"
        and v.get("node_id") == "nid-1"
        for v in reject_values
    )
    gas_values = _all_button_values(
        forms.build_gas_card("pid-2", "SX-20261109-001")
    )
    assert any(
        v.get("module") == "wp_chat" and v.get("act") == "gas_save"
        for v in gas_values
    )


def test_menu_card_has_drafts_entry() -> None:
    values = _all_button_values(forms.build_menu_card("ou-x"))
    assert any(v.get("act") == "my_drafts" for v in values)
    assert sum(1 for v in values if v.get("act") == "start_form") == 8


# ── 文本意图 ──


def test_parse_intent_routing() -> None:
    assert parse_intent("发起动火作业") == {
        "act": "start_form",
        "permit_type": "hot_work",
    }
    assert parse_intent("菜单")["act"] == "menu"
    assert parse_intent("复检")["act"] == "gas_list"
    assert parse_intent("取消")["act"] == "cancel"
    assert parse_intent("你好")["act"] == "unknown"


# ── 事件分发首非 None ──


async def test_dispatch_keeps_first_non_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety.feishu import event_client as ec

    async def _first(_event: dict[str, Any]) -> dict[str, Any]:
        return {"claimed": 1}

    async def _later(_event: dict[str, Any]) -> None:
        return None

    monkeypatch.setitem(ec._handlers, "t.wp_test", [_first, _later])
    assert await ec._dispatch("t.wp_test", {}) == {"claimed": 1}

    async def _boom(_event: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    async def _rescuer(_event: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setitem(ec._handlers, "t.wp_test2", [_boom, _rescuer])
    assert await ec._dispatch("t.wp_test2", {}) == {"ok": True}


# ── 分发器（stub 业务层）──


class _StubFlow:
    """ChatFlowService 替身：记录调用并返回固定卡片。"""

    instances: list[_StubFlow] = []

    def __init__(self, db: Any, *, open_id: str = "", union_id: str = "") -> None:
        self.open_id = open_id
        self.calls: list[tuple] = []
        _StubFlow.instances.append(self)

    async def start_form(self, permit_type: str) -> dict[str, Any]:
        self.calls.append(("start_form", permit_type))
        return _card(f"开始-{permit_type}")

    async def save_step(
        self,
        permit_type: str,
        step: int,
        form_value: dict[str, Any],
        *,
        message_id: str = "",
    ) -> dict[str, Any]:
        self.calls.append(("save_step", permit_type, step, form_value, message_id))
        return _card("下一步")

    async def my_drafts(self, *, message_id: str = "") -> dict[str, Any]:
        self.calls.append(("my_drafts", message_id))
        return _card("草稿")

    async def cancel(self, permit_type: str) -> dict[str, Any]:
        return _card("已取消")

    async def use_default_sign(
        self, permit_type: str, sign_key: str
    ) -> dict[str, Any]:
        self.calls.append(("use_default_sign", permit_type, sign_key))
        return _card("已签名")

    async def my_gas_permits(self) -> list[Any]:
        return []

    async def submit(
        self, permit_type: str, form_value: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.calls.append(("submit", permit_type, form_value))
        return _card("提交回执")


@pytest.fixture
def stub_flow(monkeypatch: pytest.MonkeyPatch) -> type[_StubFlow]:
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    _StubFlow.instances = []
    monkeypatch.setattr(handler, "ChatFlowService", _StubFlow)
    return _StubFlow


@pytest.fixture
def stub_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """用空会话工厂替换 async_session_factory（stub 用例不连库）。"""
    import contextlib

    from app.modules.safety.feishu import work_permit_chat_handler as handler

    @contextlib.asynccontextmanager
    async def _fake_factory():  # type: ignore[untyped-def]
        yield object()

    monkeypatch.setattr(handler, "async_session_factory", _fake_factory)


async def test_handler_ignores_foreign_module_and_noop() -> None:
    from app.modules.safety.feishu.work_permit_chat_handler import (
        handle_wp_chat_card_action,
    )

    foreign = await handle_wp_chat_card_action(
        _card_event({"module": "work_permit", "action": "approve"})
    )
    assert foreign is None
    noop = await handle_wp_chat_card_action(
        _card_event({"module": "wp_chat", "act": "noop"})
    )
    assert noop is None


async def test_handler_menu_returns_card() -> None:
    from app.modules.safety.feishu.work_permit_chat_handler import (
        handle_wp_chat_card_action,
    )

    resp = await handle_wp_chat_card_action(
        _card_event({"module": "wp_chat", "act": "menu"})
    )
    assert resp is not None
    assert resp["card"]["type"] == "raw"
    assert "作业票办理" in json.dumps(resp["card"]["data"], ensure_ascii=False)


async def test_handler_fast_step_save_passes_form_and_message(
    stub_flow: type[_StubFlow],
    stub_session: None,
) -> None:
    from app.modules.safety.feishu.work_permit_chat_handler import (
        handle_wp_chat_card_action,
    )

    resp = await handle_wp_chat_card_action(
        _card_event(
            {
                "module": "wp_chat",
                "act": "step_save",
                "type": "blind_plate",
                "step": 1,
            },
            form_value={"apply_department": "一车间"},
            message_id="om_step9",
        )
    )
    assert resp is not None
    assert "下一步" in json.dumps(resp["card"]["data"], ensure_ascii=False)
    flow = stub_flow.instances[-1]
    assert flow.calls == [
        ("save_step", "blind_plate", 1, {"apply_department": "一车间"}, "om_step9")
    ]


async def test_handler_use_default_sign_returns_signed_card(
    stub_flow: type[_StubFlow],
    stub_session: None,
) -> None:
    from app.modules.safety.feishu.work_permit_chat_handler import (
        handle_wp_chat_card_action,
    )

    resp = await handle_wp_chat_card_action(
        _card_event(
            {
                "module": "wp_chat",
                "act": "use_default_sign",
                "type": "blind_plate",
                "sign_key": "initiator",
            }
        )
    )
    assert resp is not None
    assert "已签名" in json.dumps(resp["card"]["data"], ensure_ascii=False)
    assert stub_flow.instances[-1].calls == [
        ("use_default_sign", "blind_plate", "initiator")
    ]


async def test_handler_heavy_ack_toast_and_background_receipt(
    stub_flow: type[_StubFlow],
    stub_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety.feishu import work_permit_chat_handler as handler
    from app.modules.safety.feishu.notification import update_card

    patched: list[tuple[str, dict[str, Any]]] = []

    async def _fake_update(message_id: str, card: dict[str, Any]) -> None:
        patched.append((message_id, card))

    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.update_card", _fake_update
    )
    del update_card

    resp = await handler.handle_wp_chat_card_action(
        _card_event(
            {"module": "wp_chat", "act": "submit", "type": "blind_plate"},
            message_id="om_submit",
        )
    )
    assert resp is not None
    assert resp["toast"]["type"] == "success"

    # 直接执行后台任务验证回执 PATCH
    await handler._run_heavy_action(
        "submit",
        "ou-op",
        "un-op",
        {"type": "blind_plate"},
        _card_event(
            {"module": "wp_chat", "act": "submit", "type": "blind_plate"},
            message_id="om_submit",
        ),
    )
    assert patched and patched[0][0] == "om_submit"
    assert "提交回执" in json.dumps(patched[0][1], ensure_ascii=False)
    assert stub_flow.instances[-1].calls == [("submit", "blind_plate", {})]


async def test_handler_reject_submit_requires_opinion(
    stub_flow: type[_StubFlow],
    stub_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """驳回意见为空：DM 提示补填，不 PATCH 原表单卡。"""
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    patched: list[str] = []
    dm_errors: list[str] = []

    async def _fake_update(message_id: str, card: dict[str, Any]) -> None:
        patched.append(message_id)

    async def _fake_dm(open_id: str, title: str, content: str,
                       elements=None, id_type: str = "open_id") -> bool:
        dm_errors.append(content)
        return True

    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.update_card", _fake_update
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_user_card", _fake_dm
    )
    await handler._run_heavy_action(
        "reject_submit",
        "ou-op",
        "un-op",
        {"permit_id": "p1", "node_id": "n1"},
        _card_event(
            {"module": "wp_chat", "act": "reject_submit"},
            form_value={"opinion": "  "},
            message_id="om_reject",
        ),
    )
    assert patched == [], "意见缺失时不得 PATCH 原表单卡"
    assert dm_errors and "驳回意见" in dm_errors[0]


async def test_handler_dedupe_blocks_repeat(
    stub_flow: type[_StubFlow],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    async def _hit(_key: str) -> str:
        return "1"

    monkeypatch.setattr(
        "app.modules.safety.feishu.work_permit_chat_handler.cache_get", _hit
    )
    resp = await handler.handle_wp_chat_card_action(
        _card_event(
            {"module": "wp_chat", "act": "approve", "permit_id": "p1", "node_id": "n1"}
        )
    )
    assert resp is not None
    assert resp["toast"]["type"] == "info"
    assert stub_flow.instances == [], "防重命中时不得进入业务层"


# ── 聊天文本入口 ──


def _message_event(text: str, open_id: str = "ou-op") -> dict[str, Any]:
    return {
        "event": {
            "message": {
                "message_type": "text",
                "chat_type": "p2p",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            "sender": {"sender_id": {"open_id": open_id}},
        }
    }


async def test_text_entry_menu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    sent: list[dict[str, Any]] = []

    async def _fake_send(open_id: str, card: dict[str, Any]) -> str | None:
        sent.append({"open_id": open_id, "card": card})
        return "om_new"

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.send_raw_card", _fake_send
    )
    await handler.handle_work_permit_message(_message_event("菜单"))
    assert sent and "作业票办理" in json.dumps(sent[0]["card"], ensure_ascii=False)
    assert sent[0]["open_id"] == "ou-op"


async def test_text_entry_accepts_unwrapped_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """event_client 分发传入的是剥掉外层 event 键的内层载荷（真机形态）。"""
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    sent: list[dict[str, Any]] = []

    async def _fake_send(open_id: str, card: dict[str, Any]) -> str | None:
        sent.append({"card": card})
        return "om_new"

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.send_raw_card", _fake_send
    )
    unwrapped = _message_event("菜单")["event"]
    await handler.handle_work_permit_message(dict(unwrapped))
    assert sent, "剥壳事件形态必须被识别处理"
    assert "作业票办理" in json.dumps(sent[0]["card"], ensure_ascii=False)


async def test_text_entry_keyword_starts_form(
    stub_flow: type[_StubFlow],
    stub_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    sent: list[dict[str, Any]] = []

    async def _fake_send(open_id: str, card: dict[str, Any]) -> str | None:
        sent.append({"card": card})
        return "om_new"

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.send_raw_card", _fake_send
    )
    await handler.handle_work_permit_message(_message_event("发起动火"))
    assert sent and "开始-hot_work" in json.dumps(sent[0]["card"], ensure_ascii=False)
    assert stub_flow.instances[-1].calls == [("start_form", "hot_work")]


async def test_text_entry_gas_list_empty(
    stub_flow: type[_StubFlow],
    stub_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    sent: list[dict[str, Any]] = []

    async def _fake_send(open_id: str, card: dict[str, Any]) -> str | None:
        sent.append({"card": card})
        return "om_new"

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.send_raw_card", _fake_send
    )
    await handler.handle_work_permit_message(_message_event("复检"))
    assert sent and "没有作业中" in json.dumps(sent[0]["card"], ensure_ascii=False)


async def test_handler_parses_form_submit_name(
    stub_flow: type[_StubFlow],
    stub_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """form_submit 按钮回调不回传 value，动作编码在 name（真机形态）。"""
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    patched: list[str] = []

    async def _fake_update(message_id: str, card: dict[str, Any]) -> None:
        patched.append(message_id)

    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.update_card", _fake_update
    )
    # 真机 form_submit 回调：action 无 value，只有 name + form_value
    event = _card_event({}, form_value={"apply_department": "一车间"})
    event["action"] = {
        "tag": "button",
        "name": "wp|step_save|hot_work|1",
        "form_value": {"apply_department": "一车间"},
    }
    resp = await handler.handle_wp_chat_card_action(event)
    assert resp is not None
    assert stub_flow.instances[-1].calls == [
        ("save_step", "hot_work", 1, {"apply_department": "一车间"}, "om_1")
    ]
    await asyncio.sleep(0.1)  # 让后台 PATCH 任务执行
    assert patched == ["om_1"], "成功后应 PATCH 原卡"


def test_form_submit_buttons_carry_encoded_name() -> None:
    from app.modules.safety.service.work_permit_card_forms import (
        build_gas_card,
        build_reject_card,
        build_step_card,
    )

    step_card = build_step_card("hot_work", 1, {}, "ou_x")
    form = [el for el in step_card["body"]["elements"] if el.get("tag") == "form"][0]
    submit = [el for el in form["elements"] if el.get("tag") == "button"][0]
    assert submit["name"] == "wp|step_save|hot_work|1"
    assert submit["action_type"] == "form_submit"

    reject = build_reject_card("p1", "n1", "DH-1")
    r_form = [el for el in reject["body"]["elements"] if el.get("tag") == "form"][0]
    r_submit = [el for el in r_form["elements"] if el.get("tag") == "button"][0]
    assert r_submit["name"] == "wp|reject_submit|p1|n1"

    gas = build_gas_card("p2", "SX-1")
    g_form = [el for el in gas["body"]["elements"] if el.get("tag") == "form"][0]
    g_submit = [el for el in g_form["elements"] if el.get("tag") == "button"][0]
    assert g_submit["name"] == "wp|gas_save|p2"


# ── 自审修复回归：错误不毁操作卡 + 未指派节点回退创建人 ──


async def test_heavy_error_sends_dm_and_keeps_original_card(
    stub_flow: type[_StubFlow],
    stub_session: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重动作失败时另发 DM 错误提示，不 PATCH 原卡（保留按钮供重试）。"""
    from app.modules.safety.feishu import work_permit_chat_handler as handler

    patched: list[str] = []
    dm_errors: list[str] = []

    async def _fake_update(message_id: str, card: dict[str, Any]) -> None:
        patched.append(message_id)

    async def _fake_dm(open_id: str, title: str, content: str,
                       elements=None, id_type: str = "open_id") -> bool:
        dm_errors.append(content)
        return True

    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.update_card", _fake_update
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_user_card", _fake_dm
    )

    class _NoSignFlow(_StubFlow):
        async def approve(self, permit_id: Any, node_id: Any) -> dict[str, Any]:
            raise AppException(
                status_code=422, message="请先点卡片上的「🖊 手写签名」完成签名"
            )

    monkeypatch.setattr(handler, "ChatFlowService", _NoSignFlow)
    await handler._run_heavy_action(
        "approve",
        "ou-op",
        "un-op",
        {"permit_id": str(uuid4()), "node_id": str(uuid4())},
        _card_event(
            {"module": "wp_chat", "act": "approve"}, message_id="om_keep"
        ),
    )
    assert patched == [], "失败时不得 PATCH 原消息"
    assert dm_errors and "手写签名" in dm_errors[0]


async def test_next_stage_unassigned_nodes_fall_back_creator(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未指派确认节点（如动火工艺确认）与未指派验票节点推给创建人。"""
    from types import SimpleNamespace

    from app.modules.safety.service import work_permit_notify as notify

    creator_id = uuid4()
    permit = SimpleNamespace(
        id=uuid4(),
        permit_type="hot_work",
        permit_level="grade2",
        permit_no="DH-20261109-001",
        apply_department=None,
        apply_time=None,
        work_unit=None,
        work_description=None,
        work_location=None,
        planned_start_time=None,
        planned_end_time=None,
        persons=[],
        risk_identifications=[],
        safety_measures=[],
        type_data={},
        related_legacy_no_text=None,
        status="pending_approval",
        approval_round=1,
        created_by=creator_id,
    )
    confirm_node = SimpleNamespace(
        id=uuid4(),
        node_key="process_tech_confirm",
        node_name="工艺技术确认",
        node_kind="confirm",
        assigned_approver_id=None,
    )

    async def _fake_pending_node(db: Any, p: Any) -> Any:
        return confirm_node

    monkeypatch.setattr(notify, "_pending_node", _fake_pending_node)
    recipient, elements = await notify._next_stage_elements(db_session, permit)
    assert recipient == creator_id
    assert "同意" in json.dumps(elements, ensure_ascii=False)

    permit.status = "approved"
    verify_node = SimpleNamespace(
        id=uuid4(),
        node_key="pre_work_verify",
        node_name="作业前验票",
        node_kind="verify",
        assigned_approver_id=None,
    )

    async def _fake_verify_node(db: Any, p: Any) -> Any:
        return verify_node

    monkeypatch.setattr(notify, "_verify_node", _fake_verify_node)
    recipient, elements = await notify._next_stage_elements(db_session, permit)
    assert recipient == creator_id
    assert "确认开工" in json.dumps(elements, ensure_ascii=False)


# ── 签名默认复用（按人最近）──


async def _cleanup_chat_flow(db: AsyncSession) -> None:
    permit_ids = list(
        await db.scalars(
            select(WorkPermit.id).where(WorkPermit.remark.like(f"{_MARK}%"))
        )
    )
    if permit_ids:
        await db.execute(
            delete(WorkPermitSignature).where(
                WorkPermitSignature.permit_id.in_(permit_ids)
            )
        )
        await db.execute(
            delete(WorkPermitNode).where(WorkPermitNode.permit_id.in_(permit_ids))
        )
        await db.execute(
            delete(WorkPermit).where(WorkPermit.id.in_(permit_ids))
        )
    await db.execute(
        delete(WorkPermitApproverConfig).where(
            WorkPermitApproverConfig.permit_type == "blind_plate",
            WorkPermitApproverConfig.remark == _MARK,
        )
    )
    await db.execute(
        delete(SafetyFeishuAppSettings).where(
            SafetyFeishuAppSettings.app_id.like(f"{_MARK}%")
        )
    )
    await db.commit()


async def _redis_available() -> bool:
    from app.core.redis import cache_get, cache_set

    try:
        await cache_set("probe:wp_chat_test", "1", ex=10)
        return await cache_get("probe:wp_chat_test") == "1"
    except Exception:
        return False


async def test_reuse_or_none_uses_person_latest(
    db_session: AsyncSession,
) -> None:
    await _cleanup_chat_flow(db_session)
    user = User(
        id=uuid4(),
        name=f"{_MARK}签署人{uuid4().hex[:6]}",
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    permit = WorkPermit(
        permit_no=f"MB-CT{uuid4().hex[:8].upper()}",
        permit_type="blind_plate",
        permit_level="none",
        status="draft",
        remark=f"{_MARK}{uuid4().hex[:8]}",
        created_by=user.id,
    )
    db_session.add(permit)
    await db_session.flush()
    db_session.add_all(
        [
            WorkPermitSignature(
                permit_id=permit.id,
                round=1,
                sign_key="initiator",
                signer_user_id=user.id,
                signer_name=user.name,
                image_key="img-old",
                signed_at=datetime(2026, 11, 1, tzinfo=UTC),
            ),
            WorkPermitSignature(
                permit_id=permit.id,
                round=1,
                sign_key="safety_officer",
                signer_user_id=user.id,
                signer_name=user.name,
                image_key="img-new",
                signed_at=datetime(2026, 11, 8, tzinfo=UTC),
            ),
        ]
    )
    await db_session.flush()

    # sign_key 传任意值都应取本人最近一次（img-new）
    assert (
        await reuse_or_none(db_session, signer_user_id=user.id, sign_key="whatever")
        == "img-new"
    )
    row = await latest_person_signature(db_session, signer_user_id=user.id)
    assert row is not None and row.image_key == "img-new"

    await _cleanup_chat_flow(db_session)


# ── 端到端：聊天提交 → 逐级签批 → 完工验收 → PDF 推卡 ──


async def test_chat_flow_end_to_end(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not await _redis_available():
        pytest.skip("Redis 不可用，跳过聊天状态机用例")

    await _cleanup_chat_flow(db_session)

    creator = User(
        id=uuid4(),
        name=f"{_MARK}发起人{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-ct-{uuid4().hex[:10]}",
        feishu_union_id=f"un-ct-{uuid4().hex[:10]}",
    )
    approver1 = User(
        id=uuid4(),
        name=f"{_MARK}审批A{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-a1-{uuid4().hex[:10]}",
        feishu_union_id=f"un-a1-{uuid4().hex[:10]}",
    )
    approver2 = User(
        id=uuid4(),
        name=f"{_MARK}审批B{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-a2-{uuid4().hex[:10]}",
        feishu_union_id=f"un-a2-{uuid4().hex[:10]}",
    )
    db_session.add_all([creator, approver1, approver2])
    await db_session.flush()
    db_session.add_all(
        [
            SafetyFeishuAppSettings(
                app_id=f"{_MARK}-{uuid4().hex[:8]}",
                app_secret="test-secret",
                is_enabled=True,
                permit_notify_enabled=True,
            ),
            WorkPermitApproverConfig(
                permit_type="blind_plate",
                node_key="safety_officer_opinion",
                node_name="安全员意见",
                approver_user_id=approver1.id,
                remark=_MARK,
                created_by=creator.id,
            ),
            WorkPermitApproverConfig(
                permit_type="blind_plate",
                node_key="workshop_leader_opinion",
                node_name="车间负责人意见",
                approver_user_id=approver2.id,
                remark=_MARK,
                created_by=creator.id,
            ),
        ]
    )
    await db_session.commit()

    pushed: list[dict[str, Any]] = []

    async def _fake_push_card(union_id: str, card: dict[str, Any]) -> str | None:
        pushed.append({"union_id": union_id, "card": card})
        return f"om_{len(pushed)}"

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.send_raw_card_by_union_id",
        _fake_push_card,
    )

    now = datetime.now(UTC)
    flow = ChatFlowService(db_session, open_id=creator.feishu_open_id or "")
    await flow.start_form("blind_plate")
    state = await flow._load_state("blind_plate")
    assert state is not None
    state["values"].update(
        {
            "apply_department": "一车间",
            "work_description": f"{_MARK}更换盲板",
            "work_location": "车间东侧",
            "work_unit": "检修单位",
            "planned_start": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
            "planned_end": (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"),
            "type_data": {
                "blind_action": "堵盲板",
                "equipment_pipe_name": "R101 出料管",
            },
            "persons": [{"role": "work_leader", "name": "张三"}],
            "risk": [],
            "measures": [],
            "remark": f"{_MARK}{uuid4().hex[:8]}",
        }
    )
    state["sign"] = {
        "initiator": "img-i",
        "briefer": "img-b",
        "briefer_receiver": "img-br",
    }
    await flow._save_state(state)

    receipt = await flow.submit("blind_plate")
    assert "MB-" in json.dumps(receipt, ensure_ascii=False)

    permit_id = (
        await db_session.scalars(
            select(WorkPermit.id)
            .where(WorkPermit.remark.like(f"{_MARK}%"))
            .order_by(WorkPermit.created_at.desc())
        )
    ).first()
    assert permit_id is not None
    permit = await permit_service.get_permit(db_session, permit_id)
    assert permit.status == "pending_approval"
    # 第一级审批卡已推给 approver1（union_id）
    assert pushed and pushed[0]["union_id"] == approver1.feishu_union_id

    # 无历史签名时同意被拦截
    flow1 = ChatFlowService(db_session, open_id=approver1.feishu_open_id or "")
    nodes = [
        n
        for n in await db_session.scalars(
            select(WorkPermitNode).where(WorkPermitNode.permit_id == permit_id)
        )
        if n.node_kind == "approve"
    ]
    first_node = min(nodes, key=lambda n: n.seq)
    with pytest.raises(AppException):
        await flow1.approve(permit_id, first_node.id)

    # 写入本人历史签名后一键同意（默认复用）
    db_session.add(
        WorkPermitSignature(
            permit_id=permit_id,
            round=1,
            sign_key=first_node.node_key,
            signer_user_id=approver1.id,
            signer_name=approver1.name,
            image_key="img-a1",
            signed_at=datetime(2026, 11, 8, tzinfo=UTC),
        )
    )
    await db_session.commit()
    await flow1.approve(permit_id, first_node.id)
    permit = await permit_service.get_permit(db_session, permit_id)
    assert permit.status == "pending_approval"
    assert pushed[-1]["union_id"] == approver2.feishu_union_id

    # 第二级签批 → 盲板无验票环节 → 完工验收卡（回退创建人）
    second_node = max(nodes, key=lambda n: n.seq)
    db_session.add(
        WorkPermitSignature(
            permit_id=permit_id,
            round=1,
            sign_key=second_node.node_key,
            signer_user_id=approver2.id,
            signer_name=approver2.name,
            image_key="img-a2",
            signed_at=datetime(2026, 11, 8, tzinfo=UTC),
        )
    )
    await db_session.commit()
    flow2 = ChatFlowService(db_session, open_id=approver2.feishu_open_id or "")
    await flow2.approve(permit_id, second_node.id)
    permit = await permit_service.get_permit(db_session, permit_id)
    assert permit.status == "approved"
    accept_push = json.dumps(pushed[-1], ensure_ascii=False)
    assert pushed[-1]["union_id"] == creator.feishu_union_id
    assert "完工验收" in accept_push

    # 创建人完工验收 → completed → PDF 推卡
    await flow.accept(permit_id)
    permit = await permit_service.get_permit(db_session, permit_id)
    assert permit.status == "completed"
    assert "下载 PDF" in json.dumps(pushed[-1], ensure_ascii=False)

    await _cleanup_chat_flow(db_session)
    # 测试用户与表单记忆/审计日志行按仓库既有模式保留（存在 FK 引用）


# ── 安全承诺测试端点修复 ──


async def test_commitment_notify_test_endpoint(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.safety.api import feishu_settings as api
    from app.modules.safety.service import commitment_notify as service

    await _cleanup_chat_flow(db_session)

    # 未配置 → 明确报错而不是 NameError
    with pytest.raises(AppException):
        await api.test_commitment_notify(db_session, None)

    db_session.add(
        SafetyFeishuAppSettings(
            app_id=f"{_MARK}-sc-{uuid4().hex[:8]}",
            app_secret="test-secret",
            is_enabled=True,
            commitment_notify_enabled=True,
            commitment_user_ids=["ou-sc-target"],
        )
    )
    await db_session.commit()

    sent: list[str] = []

    async def _fake_send(db: Any, open_id: str) -> bool:
        sent.append(open_id)
        return True

    monkeypatch.setattr(service, "send_test_fill_card", _fake_send)
    result = await api.test_commitment_notify(db_session, None)
    assert result.data["success"] is True
    assert sent == ["ou-sc-target"]

    await _cleanup_chat_flow(db_session)



async def test_chat_flow_service_real_steps(
    db_session: AsyncSession, stub_flow: type[_StubFlow]
) -> None:
    """真实 ChatFlowService 分步驱动（不经 handler stub）：发起→保存→汇总。"""
    from app.core.redis import cache_get
    from app.modules.safety.service.work_permit_chat_flow import ChatFlowService

    user = User(
        id=uuid4(),
        name=f"{_MARK}聊天用户{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-flow-{uuid4().hex[:8]}",
    )
    db_session.add(user)
    await db_session.flush()

    service = ChatFlowService(db_session, open_id=user.feishu_open_id or "")
    permit_type = "hot_work"

    card = await service.start_form(permit_type)
    assert card
    state = await cache_get(f"wp_form:{service.open_id}:{permit_type}")
    assert state

    from app.modules.safety.service.work_permit_card_forms import steps_for

    steps = steps_for(permit_type)
    form_value: dict[str, Any] = {"work_description": "聊天流测试动火"}
    for step in steps[:-1]:
        await service.save_step(permit_type, step, dict(form_value))
    summary = await service.build_summary(permit_type)
    assert summary

    await service.my_drafts()
    await service.cancel(permit_type)
    leftover = await cache_get(f"wp_form:{service.open_id}:{permit_type}")
    assert not leftover

    await db_session.delete(user)
    await db_session.flush()
