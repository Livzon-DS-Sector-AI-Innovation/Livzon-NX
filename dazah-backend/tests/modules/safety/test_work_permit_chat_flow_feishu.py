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

    # ② 人员选人 + 外部人员手工录入
    person_names = _form_names("hot_work", 2)
    assert any(n.startswith("person__") for n in person_names), (
        "人员步应含通讯录选人组件"
    )
    assert any(n.startswith("person_ext_cert__") for n in person_names), (
        "人员步应支持外部人员证件号录入"
    )
    # ④ 风险辨识：下拉多选（与动火方式一致）
    step4_card = forms.build_step_card(
        "hot_work", 4, forms.base_form_values("hot_work", None), "ou-x"
    )
    step4_form = [
        el for el in step4_card["body"]["elements"] if el.get("tag") == "form"
    ][0]
    risk_selects = [
        el
        for el in step4_form["elements"]
        if el.get("name") == "risk" and el.get("tag") == "multi_select_static"
    ]
    assert risk_selects, "风险辨识应为下拉多选"
    assert len(risk_selects[0].get("options") or []) >= 20, "风险辨识下拉应含全部选项"
    # ⑤ 措施逐行是/否 + 下划线填空
    measure_names = _form_names("hot_work", 5)
    assert any(n.startswith("m__") for n in measure_names), "安全措施应逐行选择"
    assert any(n.startswith("f__hw_disconnect_pipes__") for n in measure_names), (
        "下划线条文应附数量填空"
    )
    # ⑥ 审批人选人
    assign_names = _form_names("hot_work", 6)
    assert any(n.startswith("assign_") for n in assign_names), (
        "审批人指派步应含选人组件"
    )


def test_all_selects_have_options() -> None:
    """所有下拉/多选必须带非空选项（模板 options 为 tuple，曾被误判为空）。"""
    from app.modules.safety.service.work_permit_templates import PERMIT_TEMPLATES

    for code in PERMIT_TEMPLATES:
        values = forms.base_form_values(code, None)
        for step in forms.steps_for(code)[:-1]:
            card = forms.build_step_card(code, step, values, "ou-x")
            for element in card["body"]["elements"]:
                if element.get("tag") != "form":
                    continue
                for field in element["elements"]:
                    if str(field.get("tag", "")).endswith("select_static"):
                        assert field.get("options"), (
                            f"{code} 第{step}步下拉 {field.get('name')} 无选项"
                        )


def test_summary_card_sign_gating_and_default_button() -> None:
    values = forms.base_form_values("blind_plate", None)
    urls = {
        key: f"https://x/sign/{key}"
        for key in ("initiator", "briefer", "briefer_receiver")
    }

    unsigned = forms.build_summary_card("blind_plate", "none", values, {}, urls)
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
    gas_values = _all_button_values(forms.build_gas_card("pid-2", "SX-20261109-001"))
    assert any(
        v.get("module") == "wp_chat" and v.get("act") == "gas_save" for v in gas_values
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

    async def use_default_sign(self, permit_type: str, sign_key: str) -> dict[str, Any]:
        self.calls.append(("use_default_sign", permit_type, sign_key))
        return _card("已签名")

    async def set_level(self, permit_type: str, level: str) -> dict[str, Any]:
        self.calls.append(("set_level", permit_type, level))
        return _card(f"级别-{level}")

    async def toggle_check(
        self, permit_type: str, field: str, key: str
    ) -> dict[str, Any]:
        self.calls.append(("toggle_check", permit_type, field, key))
        return _card(f"勾选-{key}")

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

    async def _fake_dm(
        open_id: str, title: str, content: str, elements=None, id_type: str = "open_id"
    ) -> bool:
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
    # 表单内还有级别切换按钮，取带 form_submit 标记的提交按钮
    submit = [
        el
        for el in form["elements"]
        if el.get("tag") == "button" and el.get("action_type") == "form_submit"
    ][0]
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

    async def _fake_dm(
        open_id: str, title: str, content: str, elements=None, id_type: str = "open_id"
    ) -> bool:
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
        _card_event({"module": "wp_chat", "act": "approve"}, message_id="om_keep"),
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
    recipient, elements, _title = await notify._next_stage_elements(db_session, permit)
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
    recipient, elements, _title = await notify._next_stage_elements(db_session, permit)
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
        await db.execute(delete(WorkPermit).where(WorkPermit.id.in_(permit_ids)))
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


class TestChatFlowHelpers:
    """ChatFlowService 辅助函数直测（模块级纯函数 + 简单 DB mock）。"""

    def _make_service(self, db: Any = None) -> Any:
        from app.modules.safety.service.work_permit_chat_flow import (
            ChatFlowService,
        )

        return ChatFlowService(db or object(), open_id="ou-h")

    async def test_user_by_feishu_id_direct(self) -> None:
        """open_id 精确命中。"""
        from types import SimpleNamespace

        user = SimpleNamespace(id="u1", name="张三", feishu_open_id="ou-h")
        result_mock = SimpleNamespace(scalar_one_or_none=lambda: user)

        class _DB:
            async def execute(self, *_a: Any, **_kw: Any) -> Any:
                return result_mock

        svc = self._make_service(_DB())
        found = await svc._user_by_feishu_id("ou-h")
        assert found is user

    async def test_user_by_feishu_id_none(self) -> None:
        from types import SimpleNamespace

        result_mock = SimpleNamespace(scalar_one_or_none=lambda: None)

        class _DB:
            async def execute(self, *_a: Any, **_kw: Any) -> Any:
                return result_mock

        svc = self._make_service(_DB())
        assert await svc._user_by_feishu_id("ou-x") is None

    async def test_certificate_by_name(self) -> None:
        from types import SimpleNamespace

        cert = SimpleNamespace(id="c1", certificate_no="DJ-1")
        result_mock = SimpleNamespace(scalar_one_or_none=lambda: cert)

        class _DB:
            async def execute(self, *_a: Any, **_kw: Any) -> Any:
                return result_mock

        svc = self._make_service(_DB())
        found = await svc._certificate_by_name("张三", "work_leader")
        assert found is cert

    async def test_certificate_for_user(self) -> None:
        from types import SimpleNamespace

        cert = SimpleNamespace(id="c2")
        result_mock = SimpleNamespace(scalar_one_or_none=lambda: cert)

        class _DB:
            async def execute(self, *_a: Any, **_kw: Any) -> Any:
                return result_mock

        svc = self._make_service(_DB())
        found = await svc._certificate_for_user("u1", "guardian")
        assert found is cert

    def test_parse_dt_strict(self) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            _parse_dt_strict,
        )

        assert _parse_dt_strict("2026-11-01 08:00") is not None
        assert _parse_dt_strict("2026-11-01T08:00") is not None
        assert _parse_dt_strict("") is None
        assert _parse_dt_strict(None) is None
        assert _parse_dt_strict("bad") is None

    def test_cert_snapshot(self) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service.work_permit_chat_flow import (
            _cert_snapshot,
        )

        cert = SimpleNamespace(
            id="c9",
            certificate_no="DJ-9",
            certificate_category="electrician",
            expiry_date=None,
            status="valid",
        )
        snap = _cert_snapshot(cert)
        assert snap["certificate_id"] == "c9"
        assert snap["certificate_no"] == "DJ-9"
        assert snap["certificate_category"] == "electrician"

    async def test_resolve_assignment_names_no_assignments(
        self,
    ) -> None:
        svc = self._make_service()
        values: dict[str, Any] = {"assignments": {}}
        await svc._resolve_assignment_names(values)
        assert values["assignments"] == {}


async def test_chat_flow_step1_warnings_paths(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """时间校验三分支：缺失/倒序/正常（mock runtime settings）。"""
    from app.modules.safety.service.work_permit_chat_flow import ChatFlowService

    async def _settings(db: Any) -> dict[str, Any]:
        return {}

    async def _hours(settings: dict, ptype: str, level: str) -> float | None:
        return None

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit.get_runtime_settings", _settings
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit._validity_hours", _hours
    )

    svc = ChatFlowService(db_session, open_id="ou-t")
    # 缺时间 → None（不校验）
    assert await svc._step1_warnings("hot_work", {}) is None
    # 倒序 → 错误消息
    msg = await svc._step1_warnings(
        "hot_work",
        {
            "planned_start": "2026-11-01 18:00",
            "planned_end": "2026-11-01 08:00",
        },
    )
    assert msg is not None and "晚于" in msg
    # 正常 → None
    assert (
        await svc._step1_warnings(
            "hot_work",
            {
                "planned_start": "2026-11-01 08:00",
                "planned_end": "2026-11-01 18:00",
            },
        )
        is None
    )


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


async def test_chat_flow_submit_seeded_state(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直接播种完整表单状态后提交：覆盖 submit 建票/指派/推送/清理全链。"""

    from app.core.redis import cache_delete, cache_set
    from app.modules.safety.models import WorkPermit
    from app.modules.safety.service import work_permit_notify as wp_notify
    from app.modules.safety.service.work_permit_card_forms import (
        base_form_values,
    )
    from app.modules.safety.service.work_permit_chat_flow import (
        ChatFlowService,
        initiator_sign_keys,
    )

    async def _stub_raw_card(*_a: Any, **_k: Any) -> str | None:
        return "om_seeded"

    monkeypatch.setattr(wp_notify, "send_raw_card", _stub_raw_card)
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_group_card",
        lambda *_a, **_k: "om_group",
    )

    user = User(
        id=uuid4(),
        name=f"{_MARK}播种用户{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-seed-{uuid4().hex[:8]}",
    )
    db_session.add(user)
    await db_session.flush()

    service = ChatFlowService(db_session, open_id=user.feishu_open_id)
    permit_type = "blind_plate"
    values = base_form_values(permit_type, None)
    values["work_description"] = "播种提交测试"
    values["type_data"] = {
        "blind_action": "堵盲板",
        "equipment_pipe_name": "R101 循环水管线",
    }
    values["planned_start"] = "2026-11-12 08:00"
    values["planned_end"] = "2026-11-12 18:00"
    values["persons"] = [{"role": "work_leader", "name": "播种人"}]
    # 审批节点指派：安全员意见节点指派给另一个测试用户
    assignee = User(
        id=uuid4(),
        name=f"{_MARK}审批人{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-assign-{uuid4().hex[:8]}",
    )
    db_session.add(assignee)
    await db_session.flush()
    values["assignments"] = {
        "safety_officer_opinion": str(assignee.feishu_open_id),
        "workshop_leader_opinion": str(assignee.feishu_open_id),
    }
    sign: dict[str, str] = {}
    for key in initiator_sign_keys(permit_type):
        sign[key] = f"signs/{key}.png"
    state = {
        "type": permit_type,
        "step": 6,
        "values": values,
        "sign": sign,
        "assignments": {},
    }
    await cache_set(
        f"wp_form:{user.feishu_open_id}:{permit_type}",
        json.dumps(state, ensure_ascii=False, default=str),
        ex=300,
    )
    try:
        receipt = await service.submit(permit_type)
        assert receipt
        permit = (
            await db_session.scalars(
                select(WorkPermit).where(WorkPermit.work_description == "播种提交测试")
            )
        ).first()
        assert permit is not None, "提交后应真实建票"
        assert permit.permit_no.startswith("MB-")
        await service.clear_state(permit_type)
    finally:
        await cache_delete(f"wp_form:{user.feishu_open_id}:{permit_type}")


# ── CI 缺口定向补测（chat_flow 辅助路径 / notify / card_forms / signatures）──


class _RecDB:
    """按次返回预设 result 的假会话；记录 commit/rollback。"""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *_a: Any, **_kw: Any) -> Any:
        from types import SimpleNamespace

        item = self._results.pop(0) if self._results else None
        if item is None:
            return SimpleNamespace(scalar_one_or_none=lambda: None)
        return item

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _result(value: Any) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(scalar_one_or_none=lambda: value)


class TestChatFlowGapCoverage:
    """chat_flow 未覆盖分支：人员合并/状态文案/推送/回执/merge 表单值。"""

    def _svc(self, db: Any = None) -> Any:
        from app.modules.safety.service.work_permit_chat_flow import (
            ChatFlowService,
        )

        return ChatFlowService(db or object(), open_id="ou-h")

    async def test_ensure_user_open_id_writeback(self) -> None:
        """open_id 变化时回写；commit 失败回滚不阻断。"""
        from types import SimpleNamespace

        user = SimpleNamespace(id="u1", name="张三", feishu_open_id="ou-old")
        db = _RecDB([_result(user)])
        svc = self._svc(db)
        got = await svc.ensure_user()
        assert got is user
        assert user.feishu_open_id == "ou-h"
        assert db.commits == 1

        # commit 抛错：回滚后仍返回用户
        user2 = SimpleNamespace(id="u2", name="李", feishu_open_id="ou-old")

        class _FailDB(_RecDB):
            async def commit(self) -> None:
                raise RuntimeError("commit down")

        fail_db = _FailDB([_result(user2)])
        svc2 = self._svc(fail_db)
        got2 = await svc2.ensure_user()
        assert got2 is user2
        assert fail_db.rollbacks == 1

    async def test_user_by_feishu_id_fallbacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """库内未命中 → 通讯录 tenant_user_id / 姓名兜底。"""
        from types import SimpleNamespace

        from app.modules.safety.service import work_permit_chat_flow as cf

        user_by_name = SimpleNamespace(id="u-name", name="王五")
        svc = self._svc(_RecDB([None, None, _result(user_by_name)]))

        async def _info(open_id: str) -> tuple[str, str]:
            return ("王五", "t-9")

        monkeypatch.setattr(cf, "feishu_user_info", _info)
        found = await svc._user_by_feishu_id("ou-x")
        assert found is user_by_name

        # tenant_user_id 命中工号
        user_by_uid = SimpleNamespace(id="u-uid", name="赵六")
        svc2 = self._svc(_RecDB([None, _result(user_by_uid)]))
        found2 = await svc2._user_by_feishu_id("ou-y")
        assert found2 is user_by_uid

        # 通讯录无任何信息 → None
        async def _empty(open_id: str) -> tuple[str, str]:
            return ("", "")

        monkeypatch.setattr(cf, "feishu_user_info", _empty)
        svc3 = self._svc(_RecDB([None]))
        assert await svc3._user_by_feishu_id("ou-z") is None

    async def test_certificate_for_user_none(self) -> None:
        svc = self._svc(_RecDB([None]))
        assert await svc._certificate_for_user("u1", "worker") is None

    async def test_merge_persons_all_branches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """第②步人员合并四分支：选人命中/未命中走通讯录/外部/保留。"""
        from types import SimpleNamespace

        from app.modules.safety.service import work_permit_chat_flow as cf

        svc = self._svc(_RecDB([]))
        found_user = SimpleNamespace(id="u-found", name="张三")
        cert_by_name = SimpleNamespace(
            id="c-name",
            certificate_no="DJ-N",
            certificate_category="electrician",
            expiry_date=None,
            status="valid",
        )
        userinfo: dict[str, tuple[str, str]] = {
            "ou-worker": ("李四", ""),
            "ou-receiver": ("", ""),
        }

        async def _info(open_id: str) -> tuple[str, str]:
            return userinfo.get(open_id, ("", ""))

        async def _by_feishu(feishu_id: str) -> Any:
            return found_user if feishu_id == "ou-leader" else None

        async def _cert_by_name(name: str, role: str) -> Any:
            return cert_by_name if name == "李四" else None

        async def _cert_for_user(user_id: Any, role: str) -> Any:
            return None

        monkeypatch.setattr(cf, "feishu_user_info", _info)
        svc._user_by_feishu_id = _by_feishu  # type: ignore[method-assign]
        svc._certificate_by_name = _cert_by_name  # type: ignore[method-assign]
        svc._certificate_for_user = _cert_for_user  # type: ignore[method-assign]

        values: dict[str, Any] = {
            "persons": [{"role": "process_guardian", "name": "老成员"}]
        }
        form_value = {
            "person__work_leader": "ou-leader",
            "person__worker": ["ou-worker"],
            "person__guardian": "",
            "person_ext_name__guardian": "王五",
            "person_ext_cert__guardian": "T-88",
            "person__briefer": "ou-leader",
            "person__briefer_receiver": "ou-receiver",
        }
        await svc._merge_persons("hot_work", values, form_value)
        by_role = {p["role"]: p for p in values["persons"]}
        assert by_role["work_leader"]["user_id"] == "u-found"
        assert by_role["worker"]["name"] == "李四"
        assert by_role["worker"]["certificate_no"] == "DJ-N"
        assert by_role["guardian"]["external"] == "true"
        assert by_role["guardian"]["certificate_no"] == "T-88"
        assert by_role["process_guardian"]["name"] == "老成员"
        assert by_role["briefer_receiver"]["name"] == "ou-receiver"
        assert values["person_sign_names"]["work_leader"] == "张三"

    async def test_set_level_expired_and_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.service import work_permit_chat_flow as cf

        async def _no_state(_key: str) -> str | None:
            return None

        monkeypatch.setattr(cf, "cache_get", _no_state)
        svc = self._svc()
        with pytest.raises(AppException) as exc:
            await svc.set_level("hot_work", "grade1")
        assert exc.value.status_code == 410

        saved: list[tuple[str, Any]] = []

        async def _state(_key: str) -> str:
            return json.dumps({"type": "hot_work", "step": 1, "values": {}})

        async def _save(key: str, payload: str, ex: int = 0) -> None:
            saved.append((key, payload))

        monkeypatch.setattr(cf, "cache_get", _state)
        monkeypatch.setattr(cf, "cache_set", _save)
        card = await svc.set_level("hot_work", "grade1")
        assert card
        assert saved and "grade1" in saved[0][1]

    async def test_step1_warnings_limit_exceeded(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            ChatFlowService,
        )

        async def _settings(db: Any) -> dict[str, Any]:
            return {}

        async def _hours(settings: dict, ptype: str, level: str) -> float | None:
            return 1.0

        monkeypatch.setattr(
            "app.modules.safety.service.work_permit.get_runtime_settings",
            _settings,
        )
        monkeypatch.setattr(
            "app.modules.safety.service.work_permit._validity_hours", _hours
        )
        svc = ChatFlowService(db_session, open_id="ou-h")
        values = {
            "planned_start": "2026-11-01 08:00",
            "planned_end": "2026-11-01 10:00",
            "level": "grade2",
        }
        warn = await svc._step1_warnings("hot_work", values)
        assert warn is not None and "超过" in warn

    def test_missing_approvers_paths(self) -> None:
        from app.modules.safety.service.work_permit_templates import (
            get_template,
        )

        svc = self._svc()
        template = get_template("hot_work")
        approve_keys = [
            str(n["key"]) for n in template.nodes if str(n.get("kind")) == "approve"
        ]
        assert approve_keys, "hot_work 应有审批节点"
        # 第一个节点已指派、第二个走默认、其余缺失
        values: dict[str, Any] = {
            "level": "grade2",
            "assignments": {approve_keys[0]: "ou-1"},
            "approver_defaults": (
                {approve_keys[1]: "默认审批人"} if len(approve_keys) > 1 else {}
            ),
        }
        missing = svc._missing_approvers("hot_work", values)
        assert isinstance(missing, list)
        # 全部指派 → 空
        values_full: dict[str, Any] = {
            "level": "grade2",
            "assignments": {k: f"ou-{i}" for i, k in enumerate(approve_keys)},
        }
        assert svc._missing_approvers("hot_work", values_full) == []

    async def test_progress_text_all_statuses(self) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_ACTIVE,
            PERMIT_STATUS_APPROVED,
            PERMIT_STATUS_COMPLETED,
            PERMIT_STATUS_PENDING,
        )

        svc = self._svc()
        node = SimpleNamespace(node_name="安全部审批")
        pending = SimpleNamespace(
            status=PERMIT_STATUS_PENDING, id=uuid4(), approval_round=1
        )
        svc_pending = self._svc(_RecDB([_result(node)]))
        assert "下一节点" in await svc_pending._progress_text(pending)

        svc_no_node = self._svc(_RecDB([None]))
        assert "审批已推进" in await svc_no_node._progress_text(pending)

        cases = {
            PERMIT_STATUS_APPROVED: "等待验票",
            PERMIT_STATUS_ACTIVE: "已开工",
            PERMIT_STATUS_COMPLETED: "已完工",
            "unknown": "",
        }
        for status, expect in cases.items():
            permit = SimpleNamespace(status=status)
            text = await svc._progress_text(permit)
            assert expect in text, f"{status} 应包含 {expect}"

    async def test_notify_creator_rejected_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import work_permit_notify as notify

        calls: list[tuple[Any, str]] = []

        async def _notify(db: Any, permit: Any, *, title: str, extra: str) -> None:
            calls.append((permit, title))

        permit = SimpleNamespace(permit_no="DH-1")
        monkeypatch.setattr(notify, "notify_status_change", _notify)
        svc = self._svc()
        await svc._notify_creator_rejected(permit, "材料不齐")
        assert calls and calls[0][1] == "已被驳回"

        async def _boom(db: Any, permit: Any, *, title: str, extra: str) -> None:
            raise RuntimeError("notify down")

        monkeypatch.setattr(notify, "notify_status_change", _boom)
        # 通知失败不抛错（仅记录日志）
        await svc._notify_creator_rejected(permit, "再次驳回")

    def test_merge_form_values_step1_and_type_fields(self) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            _merge_form_values,
        )

        values: dict[str, Any] = {}
        form_value = {
            "apply_department": "一车间",
            "work_description": "更换阀门",
            "planned_start_date": "2026-11-01",
            "planned_start_time": "08:30",
            "planned_end_date": 1793000000000,  # 毫秒时间戳
            "planned_end_time": "17:00",
            "hot_work_location": "罐区 T-101",
            "hot_work_methods": ["焊接", "气割"],
        }
        _merge_form_values("hot_work", 1, values, form_value)
        assert values["apply_department"] == "一车间"
        assert values["planned_start"] == "2026-11-01 08:30"
        assert values["planned_end"].endswith(" 17:00")
        assert values["type_data"]["hot_work_methods"] == ["焊接", "气割"]

        # 逐行 tf__ 形态 + 字符串单选覆盖列表
        values2: dict[str, Any] = {"level": "grade2"}
        form2 = {
            "tf__hot_work_methods__焊接": "yes",
            "tf__hot_work_methods__明火": "no",
            "hot_work_methods": "焊接",
        }
        _merge_form_values("hot_work", 1, values2, form2)
        assert values2["type_data"]["hot_work_methods"] == ["焊接"]

    def test_merge_form_values_step3_gas(self) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            _merge_form_values,
        )

        values: dict[str, Any] = {}
        form_value = {
            "gas_co": "12",
            "gas_time_date": "2026-11-02",
            "gas_time_time": "09:15",
        }
        _merge_form_values("hot_work", 3, values, form_value)
        assert values["gas"]["gas_co"] == "12"
        assert values["gas"]["gas_time"] == "2026-11-02 09:15"

    def test_merge_form_values_step4_risk_forms(self) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            _merge_form_values,
        )

        values: dict[str, Any] = {}
        _merge_form_values("hot_work", 4, values, {"risk": ["火灾", "触电"]})
        assert values["risk"] == ["火灾", "触电"]

        values2: dict[str, Any] = {}
        _merge_form_values("hot_work", 4, values2, {"risk": "火灾、高处坠落"})
        assert values2["risk"] == ["火灾", "高处坠落"]

        values3: dict[str, Any] = {}
        _merge_form_values(
            "hot_work",
            4,
            values3,
            {"risk__火灾": "yes", "risk__触电": "no"},
        )
        assert values3["risk"] == ["火灾"]

    def test_merge_form_values_step5_measures_and_step6_assign(self) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            _merge_form_values,
        )

        values: dict[str, Any] = {}
        _merge_form_values(
            "hot_work",
            5,
            values,
            {
                "m__fire_ext": "yes",
                "m__gas_check": "no",
                "f__fire_ext__count": " 2 ",
            },
        )
        assert values["measures"] == ["fire_ext"]
        assert values["measure_fills"] == {"fire_ext": {"count": "2"}}

        values6: dict[str, Any] = {}
        _merge_form_values(
            "hot_work",
            6,
            values6,
            {
                "assign_safety_officer": ["ou-approver"],
                "assign_workshop_leader": "  ",
                "assign_safety_dept": "ou-dept",
            },
        )
        assert values6["assignments"] == {
            "safety_officer": "ou-approver",
            "safety_dept": "ou-dept",
        }

    def test_build_create_payload_iso_and_persons(self) -> None:
        from app.modules.safety.service.work_permit_chat_flow import (
            build_create_payload,
        )

        values = {
            "apply_department": "一车间",
            "planned_start": "2026-11-01T08:00",  # ISO 兜底解析
            "planned_end": "2026-11-01T17:00",
            "persons": [
                {"role": "worker", "name": "王五", "certificate_no": "T-9"},
                {"role": "guardian", "name": ""},
            ],
        }
        payload = build_create_payload("hot_work", "grade2", values)
        assert payload.persons[0].certificate_no == "T-9"
        assert len(payload.persons) == 1, "无名人员应过滤"

    async def test_feishu_user_info_mocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.feishu import client as feishu_client
        from app.modules.safety.service import work_permit_chat_flow as cf

        class _Resp:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            def json(self) -> dict:
                return self._payload

        class _HTTP:
            def __init__(self, payload: dict) -> None:
                self._payload = payload

            async def __aenter__(self) -> _HTTP:
                return self

            async def __aexit__(self, *args: object) -> None:
                pass

            async def get(self, url: str, **kwargs: object) -> _Resp:
                return _Resp(self._payload)

        async def _client() -> Any:
            return object()

        async def _token(client: Any) -> str:
            return "t-token"

        monkeypatch.setattr(feishu_client, "get_safety_feishu_client", _client)
        monkeypatch.setattr(feishu_client, "get_safety_tenant_token", _token)

        ok_payload = {
            "code": 0,
            "data": {"user": {"name": "张三", "user_id": "t-1"}},
        }
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _HTTP(ok_payload))
        assert await cf.feishu_user_info("ou-ok") == ("张三", "t-1")

        err_payload = {"code": 999, "msg": "no permission"}
        monkeypatch.setattr("httpx.AsyncClient", lambda **kw: _HTTP(err_payload))
        assert await cf.feishu_user_info("ou-err") == ("", "")

        async def _broken_client() -> Any:
            raise RuntimeError("feishu down")

        monkeypatch.setattr(feishu_client, "get_safety_feishu_client", _broken_client)
        assert await cf.feishu_user_info("ou-ex") == ("", "")

    async def test_push_flow_after_action(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import work_permit_notify as notify

        pushed: list[tuple[Any, Any]] = []

        async def _push(db: Any, permit_id: Any) -> None:
            pushed.append((db, permit_id))

        monkeypatch.setattr(notify, "push_approval_card_for_next_node", _push)
        svc = self._svc()
        permit = SimpleNamespace(id=uuid4())
        await svc._push_flow_after_action(permit)
        assert pushed and pushed[0][1] == permit.id


async def test_handler_set_level_and_toggle(
    stub_flow: type, stub_session: None
) -> None:
    from app.modules.safety.feishu.work_permit_chat_handler import (
        handle_wp_chat_card_action,
    )

    resp = await handle_wp_chat_card_action(
        _card_event({"module": "wp_chat", "act": "set_level", "level": "grade1"})
    )
    assert resp is not None
    flow = stub_flow.instances[-1]
    set_calls = [c for c in flow.calls if c[0] == "set_level"]
    assert set_calls and set_calls[0][2] == "grade1"

    resp2 = await handle_wp_chat_card_action(
        _card_event({"module": "wp_chat", "act": "toggle_measure", "key": "m-1"})
    )
    assert resp2 is not None
    flow2 = stub_flow.instances[-1]
    toggle_calls = [c for c in flow2.calls if c[0] == "toggle_check"]
    assert toggle_calls and toggle_calls[0][3] == "m-1"


def _gap_permit(status: str) -> Any:
    """notify 用 SimpleNamespace 票据（_ticket_markdown 全字段）。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid4(),
        permit_no="DH-TEST-1",
        permit_type="hot_work",
        permit_level="grade2",
        status=status,
        apply_department="一车间",
        apply_time=None,
        work_description="补测作业",
        work_location="罐区",
        work_unit="检修班",
        planned_start_time=None,
        planned_end_time=None,
        type_data={},
        persons=[],
        risk_identifications=[],
        safety_measures=[],
        related_legacy_no_text="",
        created_by=uuid4(),
        approval_round=1,
    )


class TestNotifyGapCoverage:
    """work_permit_notify 未覆盖分支：下一环节构建/验收卡/审批卡刷新。"""

    async def test_next_stage_pending_no_node(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.service import work_permit_notify as notify
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_PENDING,
        )

        async def _no_records(db: Any, permit: Any) -> str:
            return ""

        async def _no_node(db: Any, permit: Any) -> Any:
            return None

        monkeypatch.setattr(notify, "_sign_records_markdown", _no_records)
        monkeypatch.setattr(notify, "_pending_node", _no_node)
        recipient, elements, title = await notify._next_stage_elements(
            object(), _gap_permit(PERMIT_STATUS_PENDING)
        )
        assert recipient is None and elements == [] and title == ""

    async def test_next_stage_pending_unassigned(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import work_permit_notify as notify
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_PENDING,
        )

        async def _no_records(db: Any, permit: Any) -> str:
            return ""

        node = SimpleNamespace(
            id=uuid4(),
            assigned_approver_id=None,
            node_kind="approve",
            node_name="安全部",
        )

        async def _node(db: Any, permit: Any) -> Any:
            return node

        async def _signed(db: Any, permit: Any, n: Any) -> bool:
            return False

        async def _hint(db: Any, user_id: Any) -> str:
            return "_已签过名，可默认沿用_"

        async def _sign_url(permit: Any, n: Any) -> str:
            return "https://s/sign"

        monkeypatch.setattr(notify, "_sign_records_markdown", _no_records)
        monkeypatch.setattr(notify, "_pending_node", _node)
        monkeypatch.setattr(notify, "_node_signed", _signed)
        monkeypatch.setattr(notify, "_default_sign_hint", _hint)
        monkeypatch.setattr(notify, "_node_sign_url", _sign_url)
        permit = _gap_permit(PERMIT_STATUS_PENDING)
        recipient, elements, title = await notify._next_stage_elements(object(), permit)
        # approve 节点未指派 → 跳过
        assert recipient is None and elements == []

        node.node_kind = "confirm"
        recipient2, elements2, _ = await notify._next_stage_elements(object(), permit)
        # confirm 未指派 → 创建人处理（卡片带签名链接与提示）
        assert recipient2 == permit.created_by and elements2
        joined = json.dumps(elements2, ensure_ascii=False)
        assert "手写签名" in joined and "已签过名" in joined

    async def test_next_stage_completed_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.service import work_permit_notify as notify
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_COMPLETED,
        )

        async def _no_records(db: Any, permit: Any) -> str:
            return ""

        async def _no_url(permit_id: Any) -> str:
            return ""

        async def _ok_url(permit_id: Any) -> str:
            return "http://dl/1"

        monkeypatch.setattr(notify, "_sign_records_markdown", _no_records)
        monkeypatch.setattr(notify, "_download_url", _no_url)

        permit = _gap_permit(PERMIT_STATUS_COMPLETED)
        permit.created_by = None
        recipient, elements, _ = await notify._next_stage_elements(object(), permit)
        assert recipient is None and elements == []

        # 创建人存在但下载链接为空 → 仍返回空
        permit.created_by = uuid4()
        recipient2, elements2, _ = await notify._next_stage_elements(object(), permit)
        assert recipient2 is None and elements2 == []

        # 下载链接可用 → 返回带下载按钮的卡片
        monkeypatch.setattr(notify, "_download_url", _ok_url)
        recipient3, elements3, _ = await notify._next_stage_elements(object(), permit)
        assert recipient3 == permit.created_by
        assert "下载 PDF" in json.dumps(elements3, ensure_ascii=False)

    async def test_accept_stage_elements_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.service import work_permit_notify as notify
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_ACTIVE,
        )

        async def _no_target(db: Any, permit: Any) -> Any:
            return None

        monkeypatch.setattr(notify, "_accept_target", _no_target)
        permit = _gap_permit(PERMIT_STATUS_ACTIVE)
        recipient, elements, sign_url = await notify._accept_stage_elements(
            object(), permit, [], with_gas=True
        )
        assert recipient is None and elements == [] and sign_url == ""

        target = uuid4()

        async def _target(db: Any, permit: Any) -> Any:
            return target

        monkeypatch.setattr(notify, "_accept_target", _target)
        recipient2, elements2, _ = await notify._accept_stage_elements(
            object(), permit, [], with_gas=True
        )
        assert recipient2 == target
        # hot_work 复检周期 60 分钟 → 卡片带复检提示 + 完工验收按钮
        joined = json.dumps(elements2, ensure_ascii=False)
        assert "复检周期 60 分钟" in joined
        assert "完工验收" in joined

    async def test_refresh_or_push_updates_cached_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.service import work_permit_notify as notify
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_PENDING,
        )

        permit = _gap_permit(PERMIT_STATUS_PENDING)
        node = type("N", (), {"assigned_approver_id": uuid4()})()

        async def _enabled(db: Any) -> bool:
            return True

        async def _resolve(db: Any, ref: Any) -> Any:
            return permit

        async def _node(db: Any, permit: Any) -> Any:
            return node

        async def _union(db: Any, user_id: Any) -> str:
            return "on-1"

        async def _cached(union_id: str, permit_id: Any) -> str:
            return "msg-1"

        async def _stage(db: Any, p: Any) -> tuple[Any, list, str]:
            return (uuid4(), [{"tag": "md"}], "标题")

        updated: list[tuple[str, dict]] = []

        async def _update(message_id: str, card: dict) -> None:
            updated.append((message_id, card))

        monkeypatch.setattr(notify, "_permit_notify_enabled", _enabled)
        monkeypatch.setattr(notify, "_resolve_permit", _resolve)
        monkeypatch.setattr(notify, "_pending_node", _node)
        monkeypatch.setattr(notify, "_recipient_union_id", _union)
        monkeypatch.setattr(notify, "_cached_approval_card_id", _cached)
        monkeypatch.setattr(notify, "_next_stage_elements", _stage)
        monkeypatch.setattr(
            "app.modules.safety.feishu.notification.update_card", _update
        )
        await notify.refresh_or_push_approval_card(object(), permit)
        assert updated and updated[0][0] == "msg-1"


class TestCardFormsGapCoverage:
    """card_forms 未覆盖：默认级别/步骤卡既有人员/票面备注与外部人员/汇总签名行。"""

    def test_default_level_empty(self) -> None:
        assert forms.default_level(()) == "none"

    def test_build_step_card_keeps_existing_person(self) -> None:
        card = forms.build_step_card(
            "hot_work",
            2,
            {
                "persons": [
                    {
                        "role": "work_leader",
                        "name": "张三",
                        "certificate_no": "DJ-1",
                    }
                ]
            },
            "ou-h",
        )
        text = json.dumps(card, ensure_ascii=False)
        assert "张三" in text
        assert "DJ-1" in text

    def test_ticket_document_note_and_persons(self) -> None:
        md = forms.ticket_document_markdown(
            "hot_work",
            {
                "measures_note": "备用灭火器 2 具",
                "persons": [
                    {
                        "role": "worker",
                        "name": "王五",
                        "certificate_no": "T-9",
                    },
                    {
                        "role": "guardian",
                        "name": "赵六",
                        "external": "true",
                    },
                ],
                "measures": [],
                "risk": [],
                "type_data": {},
            },
        )
        assert "备用灭火器 2 具" in md
        assert "王五" in md and "T-9" in md
        assert "赵六" in md and "外部人员" in md

    def test_build_summary_card_signer_names(self) -> None:
        card = forms.build_summary_card(
            "hot_work",
            "grade2",
            {
                "person_sign_names": {
                    "work_leader": "张三",
                    "briefer": "李四",
                },
                "persons": [],
                "measures": [],
                "risk": [],
                "type_data": {},
            },
            sign_status={"initiator": "done"},
            sign_urls={},
        )
        text = json.dumps(card, ensure_ascii=False)
        assert "张三" in text and "李四" in text
        assert "已签名" in text


class TestSignaturesGapCoverage:
    """work_permit_signatures 未覆盖分支：网关链接/非法 PNG 魔数。"""

    def test_build_sign_url_gateway(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import work_permit_signatures as sig

        settings = SimpleNamespace(
            SIGN_RELAY_GATEWAY_BASE="https://relay.example.com/",
            FRONTEND_URL="http://fe",
            BACKEND_PUBLIC_URL="http://be",
        )
        monkeypatch.setattr(sig, "get_settings", lambda: settings)
        url = sig.build_sign_url("tok-1")
        assert url == "https://relay.example.com/api/v1/safety/sign-relay/tok-1"

    def test_decode_signature_rejects_non_png(self) -> None:
        import base64

        from app.modules.safety.service import (
            work_permit_signatures as sig,
        )

        gif = base64.b64encode(b"GIF89a" + b"x" * 16).decode()
        assert sig.decode_signature_data_url(f"data:image/png;base64,{gif}") is None
