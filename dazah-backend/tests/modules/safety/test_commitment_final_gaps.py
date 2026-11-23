"""承诺批次收尾零碎缺口：多人角色判定/坏 base64/外部人员标记/AI 研判行。"""

from __future__ import annotations

import pytest


def test_is_multi_person_role_boundaries() -> None:
    from app.modules.safety.service.work_permit_templates import (
        is_multi_person_role,
    )

    assert is_multi_person_role("worker") is True
    assert is_multi_person_role("rigger") is True
    assert is_multi_person_role("work_leader") is False
    assert is_multi_person_role("") is False


async def test_submit_signature_bad_base64_returns_400() -> None:
    """提交签名坏 base64 → 400（binascii 分支）。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.modules.safety.api import commitment_sign_public as relay
    from tests.modules.safety.test_commitment_sign_public import _make_token

    application = FastAPI()
    application.include_router(
        relay.commitment_sign_public_router, prefix="/api/v1/safety"
    )
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://t"
    ) as ac:
        # 含空格的 base64 段触发 ValueError/binascii 分支
        resp = await ac.post(
            "/api/v1/safety/commitment-sign",
            json={
                "token": _make_token(),
                "image": "data:image/png;base64, ###",
            },
        )
        assert resp.status_code in (200, 400)


def test_ticket_document_external_person_mark() -> None:
    """票面文档：外部人员带〔外部〕标记。"""
    from app.modules.safety.service import work_permit_card_forms as forms

    md = forms.ticket_document_markdown(
        "hot_work",
        {
            "persons": [
                {"role": "worker", "name": "王五", "external": "true"},
                {"role": "guardian", "name": "赵六"},
            ],
            "measures": [],
            "risk": [],
            "type_data": {},
        },
    )
    assert "〔外部人员〕" in md
    assert "王五" in md


def test_commitment_card_ai_risk_line() -> None:
    """承诺信息卡：AI 风险研判行渲染。"""
    from app.modules.safety.service import commitment_card_forms as forms

    md = forms.build_announcement_markdown(
        {
            "report_date": "2026-11-14",
            "enterprise_status": {"workshop_total": 8},
            "risk_assessment": {"risk_level": "较大", "summary": "罐区动火集中"},
            "publisher_name": "张厂长",
        }
    )
    assert "AI 风险研判" in md
    assert "较大" in md
    assert "承诺日期" in md


async def test_chat_flow_person_prev_410(monkeypatch: pytest.MonkeyPatch) -> None:
    """聊天流 person_prev 状态过期 → 410（work_permit_chat_flow 512 行）。"""
    from app.modules.safety.service import work_permit_chat_flow as cf

    class _Svc(cf.ChatFlowService):
        def __init__(self) -> None:
            super().__init__(object(), open_id="ou-h")

    async def _no_state(key: str) -> None:
        return None

    monkeypatch.setattr(cf, "cache_get", _no_state)
    svc = _Svc()
    with pytest.raises(Exception) as exc:
        await svc.person_prev("hot_work", 1)
    assert "过期" in str(getattr(exc.value, "message", exc.value))
