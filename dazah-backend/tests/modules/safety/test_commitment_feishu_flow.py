"""安全承诺飞书填报链路测试。

覆盖：卡片构建器（分步/提醒/回执/公告 markdown）、表单值合并与
enterprise_status 转换、填报推送（mock send_raw_card + 设置开关）。
不连真实飞书。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.feishu.commitment_chat_handler import (
    _to_enterprise_status,
)
from app.modules.safety.models import (
    SafetyCommitmentReport,
    SafetyFeishuAppSettings,
)
from app.modules.safety.service import commitment_card_forms as forms
from app.modules.safety.service import commitment_notify

_MARK = "SC填报测试"


async def _cleanup_settings(db: AsyncSession) -> None:
    await db.execute(
        delete(SafetyFeishuAppSettings).where(
            SafetyFeishuAppSettings.app_id.like(f"{_MARK}%")
        )
    )
    await db.commit()


@pytest.fixture(autouse=True)
async def _clean(db_session: AsyncSession):  # noqa: ANN201 — 生成器 fixture
    await _cleanup_settings(db_session)
    yield
    await _cleanup_settings(db_session)


# ── 卡片构建器 ──


def test_build_step_card_steps_shape() -> None:
    values = forms.initial_values(None)
    for step in range(1, forms.TOTAL_STEPS + 1):
        card = forms.build_step_card("2026-11-09", step, values)
        assert card["schema"] == "2.0"
        assert "安全承诺填报 2026-11-09" in card["header"]["title"]["content"]
        tags = [el.get("tag") for el in card["body"]["elements"]]
        assert "form" in tags


def test_initial_values_prefill_from_status() -> None:
    values = forms.initial_values(
        {
            "workshop_total": 6,
            "special_work": {"hot_work_level1": 2},
            "person_main": "秦刚",
        }
    )
    assert values["workshop_total"] == 6
    assert values["special_work"]["hot_work_level1"] == 2
    assert values["person_main"] == "秦刚"


def test_merge_step_form_value_numbers_and_nested() -> None:
    values = forms.default_form_values()
    merged = forms.merge_step_form_value(
        values,
        1,
        {"workshop_total": "6", "workshop_running": "5"},
    )
    assert merged["workshop_total"] == 6
    assert merged["workshop_running"] == 5

    # step2 嵌套字段以点号 name 提交，_set_path 正确落位
    merged2 = forms.merge_step_form_value(
        dict(merged),
        2,
        {
            "special_work_total": "4",
            "special_work.hot_work_level1": "2",
            "special_work.height_work": "1",
        },
    )
    assert merged2["special_work_total"] == 4
    assert merged2["special_work"]["hot_work_level1"] == 2
    assert merged2["special_work"]["height_work"] == 1

    # 非数字容错归 0；负数钳到 0
    merged3 = forms.merge_step_form_value(
        dict(merged2), 1, {"workshop_total": "abc", "workshop_running": "-3"}
    )
    assert merged3["workshop_total"] == 0
    assert merged3["workshop_running"] == 0


def test_merge_step4_commitment_confirm() -> None:
    values = forms.default_form_values()
    merged = forms.merge_step_form_value(
        values,
        4,
        {
            "major_hazard_safe": "yes",
            "responsibility_implemented": "yes",
            "person_main": "秦刚",
            "person_tech": "史润",
            "person_ops": "贾晓",
            "commitment_confirm": "yes",
        },
    )
    assert merged["commitment_confirm"] == "yes"
    assert merged["person_main"] == "秦刚"


def test_to_enterprise_status_tri_state() -> None:
    values = {
        "workshop_total": 6,
        "hazard_rectified": "yes",
        "contractor_work": "no",
        "major_hazard_safe": "unknown",
        "person_main": "秦刚",
        "special_work": {"hot_work_level1": 1},
    }
    status = _to_enterprise_status(values)
    assert status["workshop_total"] == 6
    assert status["hazard_rectified"] is True
    assert status["contractor_work"] is False
    assert status["major_hazard_safe"] is None
    assert status["person_main"] == "秦刚"
    assert status["special_work"]["hot_work_level1"] == 1


def test_build_reminder_and_receipt_cards() -> None:
    reminder = forms.build_reminder_card(
        "2026-11-09", "今日待填报", "http://x/safety/safety-commitment"
    )
    buttons = reminder["body"]["elements"][-1]["actions"]
    acts = [btn["value"]["act"] for btn in buttons if "value" in btn]
    assert "start_form" in acts

    receipt = forms.build_receipt_card("2026-11-09", "已提交", "责任人提示")
    assert "已提交" in receipt["body"]["elements"][1]["content"]


def test_build_announcement_markdown() -> None:
    item = {
        "report_date": "2026-11-09",
        "enterprise_status": {
            "workshop_total": 6,
            "workshop_running": 6,
            "workshop_stopped": 0,
            "workshop_maintenance": 0,
            "special_work_total": 1,
            "special_work": {
                "hot_work_level1": 1,
                "hot_work_level2": 0,
                "height_work": 0,
                "confined_space": 0,
                "other": 0,
            },
            "hazard_count": 2,
            "hazard_rectified": True,
            "major_hazard_safe": True,
            "responsibility_implemented": True,
        },
        "risk_assessment": {"risk_level": "中", "summary": "有动火作业"},
        "publisher_name": "秦刚",
    }
    md = forms.build_announcement_markdown(item)
    assert "承诺日期**：2026-11-09" in md
    assert "秦刚" in md
    assert "应急〔2018〕74号" in md
    assert "一级动火 1" in md


# ── 填报推送 ──


@pytest.fixture
def _mock_send(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent_open_ids: list[str] = []

    async def _fake_send_raw_card(open_id: str, card: dict) -> str | None:
        sent_open_ids.append(open_id)
        return "om_test_message"

    monkeypatch.setattr(commitment_notify, "send_raw_card", _fake_send_raw_card)
    return sent_open_ids


async def test_push_fill_cards_disabled(
    db_session: AsyncSession, _mock_send: list[str]
) -> None:
    """开关关闭时不推送。"""
    db_session.add(
        SafetyFeishuAppSettings(
            app_id=f"{_MARK}app",
            app_secret="x",
            commitment_notify_enabled=False,
            commitment_user_ids=["ou-a"],
        )
    )
    await db_session.flush()

    report = SafetyCommitmentReport(id=uuid4(), report_date=date.today())
    sent, failed = await commitment_notify.push_fill_cards(
        db_session, "2026-11-09", report
    )
    assert (sent, failed) == (0, 0)
    assert _mock_send == []


async def test_push_fill_cards_enabled(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _mock_send: list[str],
) -> None:
    db_session.add(
        SafetyFeishuAppSettings(
            app_id=f"{_MARK}app",
            app_secret="x",
            commitment_notify_enabled=True,
            commitment_user_ids=["ou-a", "ou-b", ""],
        )
    )
    await db_session.flush()

    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FRONTEND_URL="https://demo.example.com", BACKEND_PUBLIC_URL=""
        ),
    )
    report = SafetyCommitmentReport(id=uuid4(), report_date=date.today())
    sent, failed = await commitment_notify.push_fill_cards(
        db_session, "2026-11-09", report
    )
    assert (sent, failed) == (2, 0)
    assert _mock_send == ["ou-a", "ou-b"]


async def test_push_announcement_cards(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent_chats: list[str] = []

    async def _fake_group_card(
        chat_id: str, title: str, content: str, header_template: str = "orange"
    ) -> str | None:
        sent_chats.append(chat_id)
        return "om_group_msg"

    monkeypatch.setattr(commitment_notify, "send_group_card", _fake_group_card)
    db_session.add(
        SafetyFeishuAppSettings(
            app_id=f"{_MARK}app",
            app_secret="x",
            commitment_chat_ids=["oc-x", "oc-y"],
        )
    )
    await db_session.flush()

    item = {
        "report_date": "2026-11-09",
        "enterprise_status": {},
        "publisher_name": "秦刚",
    }
    sent, failed = await commitment_notify.push_announcement_cards(db_session, item)
    assert (sent, failed) == (2, 0)
    assert sent_chats == ["oc-x", "oc-y"]


async def test_commitment_card_action_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """承诺卡片动作分发器：start/step_save/cancel/submit 全链路（stub 缓存与飞书）。"""
    from app.modules.safety.feishu import commitment_chat_handler as handler

    store: dict[str, str] = {}

    async def cache_get(key: str) -> str | None:
        return store.get(key)

    async def cache_set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    async def cache_delete(key: str) -> None:
        store.pop(key, None)

    async def _ensure_bound_user(db: Any, open_id: str) -> None:
        return None

    class _Report:
        enterprise_status = {"workshop_total": 3}
        status = "draft"
        commitment_text = ""

    async def _save_status(db: Any, date: str, status: dict[str, Any]) -> _Report:
        report = _Report()
        report.enterprise_status = status
        return report

    sent: list[tuple[str, str]] = []
    patched: list[str] = []

    async def send_user_card(open_id: str, title: str, content: str, **_k) -> bool:
        sent.append((open_id, content))
        return True

    async def update_card(message_id: str, card: dict[str, Any]) -> None:
        patched.append(message_id)

    monkeypatch.setattr(handler, "cache_get", cache_get)
    monkeypatch.setattr(handler, "cache_set", cache_set)
    monkeypatch.setattr(handler, "cache_delete", cache_delete)
    monkeypatch.setattr(handler, "_ensure_bound_user", _ensure_bound_user)
    monkeypatch.setattr(
        handler, "save_enterprise_status_from_feishu", _save_status
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_user_card", send_user_card
    )
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.update_card", update_card
    )

    open_id = "ou-commitment"
    date = "2026-11-10"

    def _event(act: str, **extra: Any) -> dict[str, Any]:
        value: dict[str, Any] = {
            "act": act,
            "date": date,
            "module": "commitment",
            **extra,
        }
        return {
            "operator": {
                "operator_id": {"open_id": open_id},
                "open_id": open_id,
            },
            "context": {"open_message_id": "om_c1"},
            "action": {"value": value},
        }

    # 非本模块事件：None
    assert (
        await handler.handle_commitment_card_action({"action": {"value": {}}})
        is None
    )
    # 缺日期：错误 toast
    missing = await handler.handle_commitment_card_action(
        {
            "operator": {"open_id": open_id},
            "action": {
                "value": {"act": "x", "module": "commitment"},
            },
        }
    )
    assert missing is not None and "参数缺失" in missing["toast"]["content"]

    # start_form：写入状态并返回 step1 卡
    started = await handler.handle_commitment_card_action(_event("start_form"))
    assert started is not None
    assert store.get(handler._state_key(open_id, date))
    # step_save：步进
    saved = await handler.handle_commitment_card_action(_event("step_save"))
    assert saved is not None
    state = store[handler._state_key(open_id, date)]
    assert '"step": 2' in state or '"step":2' in state
    # form_prev：回退
    prev = await handler.handle_commitment_card_action(_event("form_prev"))
    assert prev is not None
    # form_cancel：清状态
    await handler.handle_commitment_card_action(_event("form_cancel"))
    assert handler._state_key(open_id, date) not in store
    # submit：无状态 → 错误 toast 且私信告警
    await handler.handle_commitment_card_action(_event("submit"))
    await flush_events()
    assert sent, "无状态提交应私信提示重新发起"


async def flush_events() -> None:
    import asyncio

    for _ in range(10):
        await asyncio.sleep(0.05)
