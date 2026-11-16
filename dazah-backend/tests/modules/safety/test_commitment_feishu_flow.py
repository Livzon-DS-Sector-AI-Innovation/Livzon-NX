"""安全承诺飞书链路测试（车间分填报 + 签署）。

覆盖：卡片构建器（分步/车间卡/提醒/回执/签署卡）、表单值合并与
enterprise_status 转换、车间配置种子、填报落库与汇总、催办、签署
token 与「用上次签名」。不连真实飞书（send_raw_card/send_group_card
打桩）。
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.feishu.commitment_chat_handler import (
    _to_enterprise_status,
)
from app.modules.safety.models import (
    SafetyCommitmentReport,
    SafetyCommitmentSignature,
    SafetyCommitmentWorkshopConfig,
    SafetyCommitmentWorkshopFill,
    SafetyFeishuAppSettings,
)
from app.modules.safety.service import commitment_card_forms as forms
from app.modules.safety.service import commitment_notify
from app.modules.safety.service import commitment_workshops as ws_service
from app.modules.safety.service.commitment_signatures import (
    create_sign_token,
    reuse_or_none,
    save_signature,
    verify_token,
)

_MARK = "SC填报测试"


async def _cleanup_tables(db: AsyncSession) -> None:
    await db.execute(
        delete(SafetyFeishuAppSettings).where(
            SafetyFeishuAppSettings.app_id.like(f"{_MARK}%")
        )
    )
    await db.execute(delete(SafetyCommitmentWorkshopConfig))
    await db.execute(delete(SafetyCommitmentWorkshopFill))
    await db.execute(delete(SafetyCommitmentReport))
    await db.execute(delete(SafetyCommitmentSignature))
    await db.commit()


@pytest.fixture(autouse=True)
async def _clean(db_session: AsyncSession):  # noqa: ANN201 — 生成器 fixture
    await _cleanup_tables(db_session)
    yield
    await _cleanup_tables(db_session)


# ── 卡片构建器 ──


def test_build_step_card_steps_shape() -> None:
    values = forms.initial_values(None)
    for step in range(1, forms.TOTAL_STEPS + 1):
        card = forms.build_step_card("2026-11-09", step, values)
        assert card["schema"] == "2.0"
        assert "安全承诺填报 2026-11-09" in card["header"]["title"]["content"]
        tags = [el.get("tag") for el in card["body"]["elements"]]
        assert "form" in tags


def test_build_ws_step_card_carries_workshop() -> None:
    values = forms.initial_values(None)
    card = forms.build_step_card(
        "2026-11-09", 1, values,
        module=forms.MODULE_WORKSHOP, ws_name="201-2车间（MC）",
        ws_reporter="张起智",
    )
    assert "201-2车间（MC）" in card["header"]["title"]["content"]
    form = next(el for el in card["body"]["elements"] if el.get("tag") == "form")
    submit = next(
        el for el in form["elements"]
        if el.get("tag") == "button" and str(el.get("name", "")).startswith("cmws")
    )
    assert submit["name"].startswith("cmws|step_save|2026-11-09|1|")
    # 车间名允许含括号，不含 | 时完整还原
    parsed = forms.parse_submit_name(submit["name"])
    assert parsed is not None
    assert parsed["ws"] == "201-2车间（MC）"
    assert parsed["module"] == forms.MODULE_WORKSHOP


def test_build_step_card_no_action_container() -> None:
    values = forms.initial_values(None)
    for module in (forms.MODULE_REPORT, forms.MODULE_WORKSHOP):
        for step in range(1, forms.TOTAL_STEPS + 1):
            card = forms.build_step_card(
                "2026-11-09", step, values,
                module=module, ws_name="锅炉",
            )

            def _walk(elements: list[dict]) -> None:
                for el in elements:
                    assert el.get("tag") != "action"
                    for child in el.get("elements") or []:
                        if isinstance(child, dict):
                            _walk([child])

            _walk(card["body"]["elements"])


def test_parse_submit_name_compat() -> None:
    # 旧 4 段格式兼容
    parsed = forms.parse_submit_name("cm|step_save|2026-11-09|2")
    assert parsed is not None and parsed["module"] == "commitment"
    # 新 5 段（无 ws）
    parsed2 = forms.parse_submit_name("cm|commitment|submit|2026-11-09|4")
    assert parsed2 is not None and parsed2["ws"] == ""
    # 非本模块
    assert forms.parse_submit_name("other|a|b|c") is None


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
        values, 1, {"workshop_total": "6", "workshop_running": "5"},
    )
    assert merged["workshop_total"] == 6

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


def test_build_reminder_and_receipt_cards() -> None:
    reminder = forms.build_reminder_card(
        "2026-11-09", "今日待填报", "http://x/safety/safety-commitment"
    )
    buttons = [
        el for el in reminder["body"]["elements"] if el.get("tag") == "button"
    ]
    acts = [btn["value"]["act"] for btn in buttons if "value" in btn]
    assert "start_form" in acts

    ws_reminder = forms.build_reminder_card(
        "2026-11-09", "催办", "http://x",
        module=forms.MODULE_WORKSHOP, ws_name="锅炉", kind="remind",
    )
    assert "锅炉" in ws_reminder["header"]["title"]["content"]
    ws_start = [
        el for el in ws_reminder["body"]["elements"]
        if el.get("tag") == "button" and "value" in el
    ][0]
    assert ws_start["value"]["module"] == "commitment_ws"
    assert ws_start["value"]["ws"] == "锅炉"

    receipt = forms.build_receipt_card(
        "2026-11-09", "已提交", "责任人提示", ws_name="锅炉"
    )
    assert "锅炉" in receipt["header"]["title"]["content"]


def test_build_signature_card_reuse_button() -> None:
    card = forms.build_signature_card(
        "2026-11-09", "王总", "**承诺日期**：2026-11-09",
        "http://x/commitment-sign/tok", reuse_available=True,
    )
    texts = [
        el.get("text", {}).get("content", "")
        for el in card["body"]["elements"]
        if el.get("tag") == "button"
    ]
    assert any("用上次签名" in t for t in texts)
    card2 = forms.build_signature_card(
        "2026-11-09", "王总", "摘要", "http://x", reuse_available=False,
    )
    texts2 = [
        el.get("text", {}).get("content", "")
        for el in card2["body"]["elements"]
        if el.get("tag") == "button"
    ]
    assert not any("用上次签名" in t for t in texts2)


# ── 车间配置与汇总 ──


async def test_workshop_seed_and_progress(db_session: AsyncSession) -> None:
    configs = await ws_service.list_configs(db_session)
    assert len(configs) == 12
    assert any(c.workshop_name == "201-2车间（MC）" for c in configs)
    assert any(c.workshop_name == "动力部" for c in configs)
    progress = await ws_service.fills_progress(db_session, date.today())
    assert progress["total"] == 12
    assert progress["filled"] == 0


async def test_save_workshop_fill_overwrites(db_session: AsyncSession) -> None:
    await ws_service.list_configs(db_session)
    first = await ws_service.save_workshop_fill(
        db_session, date.today(), "锅炉",
        {"workshop_total": 12, "hazard_count": 1},
        filled_by_name="张起智", filled_by_open_id="ou-a", source="feishu",
    )
    again = await ws_service.save_workshop_fill(
        db_session, date.today(), "锅炉",
        {"workshop_total": 12, "hazard_count": 0},
        filled_by_name="张起智", filled_by_open_id="ou-a", source="feishu",
    )
    assert again.id == first.id
    assert again.fields["hazard_count"] == 0


async def test_summarize_incomplete_and_complete(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await ws_service.list_configs(db_session)
    configs = await ws_service.list_configs(db_session, enabled_only=True)

    # 未齐全：不汇总
    summarized, report = await ws_service.summarize_if_complete(
        db_session, date.today()
    )
    assert summarized is False and report is None

    # 全部车间填齐 → 汇总进日报（AI mock 失败不阻断）
    from types import SimpleNamespace

    from app.core.llm.exceptions import LLMConfigError
    from app.modules.safety.service import safety_commitment_risk

    monkeypatch.setattr(
        safety_commitment_risk,
        "llm_client",
        SimpleNamespace(
            chat_json=AsyncMock(side_effect=LLMConfigError("未配置"))
        ),
    )
    fields = {"workshop_total": 12, "person_main": "王总"}
    for idx, cfg in enumerate(configs):
        await ws_service.save_workshop_fill(
            db_session, date.today(), cfg.workshop_name,
            {**fields, "hazard_count": idx},
            filled_by_name="负责人", filled_by_open_id=f"ou-{idx}",
        )
    summarized, report = await ws_service.summarize_if_complete(
        db_session, date.today()
    )
    assert summarized is True and report is not None
    assert report.enterprise_status["workshop_total"] == 12
    assert len(report.workshop_summary) == len(configs)
    assert report.fill_source == "feishu_summary"

    # 幂等：再跑不再重复汇总
    again, _ = await ws_service.summarize_if_complete(db_session, date.today())
    assert again is False


async def test_missing_workshops(db_session: AsyncSession) -> None:
    configs = await ws_service.list_configs(db_session)
    await ws_service.save_workshop_fill(
        db_session, date.today(), configs[0].workshop_name, {},
        filled_by_name="x", filled_by_open_id="ou-x",
    )
    missing = await ws_service.missing_workshops(db_session, date.today())
    assert len(missing) == len(configs) - 1
    assert configs[0].workshop_name not in {c.workshop_name for c in missing}


# ── 推送 ──


@pytest.fixture
def _mock_send(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent_open_ids: list[str] = []

    async def _fake_send_raw_card(open_id: str, card: dict) -> str | None:
        sent_open_ids.append(open_id)
        return "om_test_message"

    monkeypatch.setattr(commitment_notify, "send_raw_card", _fake_send_raw_card)
    return sent_open_ids


async def test_push_workshop_cards(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _mock_send: list[str],
) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FRONTEND_URL="https://demo.example.com", BACKEND_PUBLIC_URL=""
        ),
    )
    configs = await ws_service.list_configs(db_session)
    assert len(configs) == 12

    # 无负责人：全部进 missing
    sent, failed, missing = await commitment_notify.push_workshop_cards(
        db_session, date.today().isoformat()
    )
    assert (sent, failed, len(missing)) == (0, 0, 12)

    # 配置前两个负责人：只推这两个
    for cfg in configs[:2]:
        cfg.reporter_open_id = f"ou-{cfg.workshop_name[:2]}"
        cfg.reporter_name = "负责人"
    await db_session.commit()
    sent, failed, missing = await commitment_notify.push_workshop_cards(
        db_session, date.today().isoformat()
    )
    assert (sent, failed) == (2, 0)
    assert len(missing) == 10
    assert _mock_send == [f"ou-{c.workshop_name[:2]}" for c in configs[:2]]


async def test_push_remind_cards_skips_filled(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    _mock_send: list[str],
) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FRONTEND_URL="https://demo.example.com", BACKEND_PUBLIC_URL=""
        ),
    )
    configs = await ws_service.list_configs(db_session)
    for cfg in configs:
        cfg.reporter_open_id = f"ou-{cfg.workshop_name[:3]}"
    await db_session.commit()
    await ws_service.save_workshop_fill(
        db_session, date.today(), configs[0].workshop_name, {},
        filled_by_name="x", filled_by_open_id="ou-x",
    )
    sent, failed = await commitment_notify.push_remind_cards(
        db_session, date.today().isoformat()
    )
    assert (sent, failed) == (len(configs) - 1, 0)
    assert len(_mock_send) == len(configs) - 1


async def test_push_summary_to_group(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent_chats: list[str] = []

    async def _fake_group_card(
        chat_id: str, title: str, content: str, header_template: str = "orange"
    ) -> str | None:
        sent_chats.append(chat_id)
        return "om_group_msg"

    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_group_card", _fake_group_card
    )
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
        "workshop_summary": [{"workshop_name": "锅炉"}],
        "publisher_name": "秦刚",
    }
    sent, failed = await commitment_notify.push_summary_to_group(db_session, item)
    assert (sent, failed) == (2, 0)
    assert sent_chats == ["oc-x", "oc-y"]


async def test_push_signature_card(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent_open_ids: list[str] = []

    async def _fake_send_raw_card(open_id: str, card: dict) -> str | None:
        sent_open_ids.append(open_id)
        return "om_sign"

    monkeypatch.setattr(commitment_notify, "send_raw_card", _fake_send_raw_card)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(
            FRONTEND_URL="https://demo.example.com",
            BACKEND_PUBLIC_URL="",
            SECRET_KEY="test-secret",
            SIGN_RELAY_GATEWAY_BASE="",
        ),
    )
    db_session.add(
        SafetyFeishuAppSettings(
            app_id=f"{_MARK}app",
            app_secret="x",
            commitment_signer_open_id="ou-signer",
        )
    )
    await db_session.flush()

    item = {
        "id": "00000000-0000-0000-0000-000000000000",
        "report_date": "2026-11-09",
        "enterprise_status": {},
        "publisher_name": "秦刚",
    }
    sent, failed = await commitment_notify.push_signature_card(db_session, item)
    assert (sent, failed) == (1, 0)
    assert sent_open_ids == ["ou-signer"]

    # 无签署人配置：跳过
    await _cleanup_tables(db_session)
    sent, failed = await commitment_notify.push_signature_card(db_session, item)
    assert (sent, failed) == (0, 0)


# ── 签署 token 与复用 ──


async def test_sign_token_roundtrip() -> None:
    token = create_sign_token(
        report_id="r-1", report_date="2026-11-09",
        open_id="ou-signer", signer_name="王总",
    )
    payload = verify_token(token)
    assert payload is not None
    assert payload["act"] == "commitment_sign"
    assert payload["rid"] == "r-1"
    assert payload["nm"] == "王总"
    assert verify_token(token + "tampered") is None


async def test_signature_reuse(db_session: AsyncSession) -> None:
    assert await reuse_or_none(db_session, signer_open_id="ou-signer") is None
    await save_signature(
        db_session,
        report_date=date.today() - timedelta(days=1),
        signer_open_id="ou-signer",
        signer_name="王总",
        image_key="commitment-signatures/old.png",
        reused=False,
    )
    image_key = await reuse_or_none(db_session, signer_open_id="ou-signer")
    assert image_key == "commitment-signatures/old.png"

    # 重签覆盖当日
    row = await save_signature(
        db_session,
        report_date=date.today(),
        signer_open_id="ou-signer",
        signer_name="王总",
        image_key="commitment-signatures/new.png",
        reused=True,
    )
    assert row.reused is True
    again = await save_signature(
        db_session,
        report_date=date.today(),
        signer_open_id="ou-signer",
        signer_name="王总",
        image_key="commitment-signatures/newest.png",
        reused=False,
    )
    assert again.id == row.id
    assert again.image_key == "commitment-signatures/newest.png"
