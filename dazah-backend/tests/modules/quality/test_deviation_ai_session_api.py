from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from docx import Document
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.ai_analysis_log import QualityAiAnalysisLog
from app.modules.quality.models.deviations import Deviation

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture(autouse=True)
async def _clean_ai_session_tables(db_session: AsyncSession) -> AsyncIterator[Any]:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.deviation_ai_sessions (
                deviation_id UUID NOT NULL,
                supplement_text TEXT NOT NULL DEFAULT '',
                attachment_summary TEXT NOT NULL DEFAULT '',
                deviation_analysis_payload JSON NULL,
                capa_suggestion_payload JSON NULL,
                model_name VARCHAR(255) NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'idle',
                error_message TEXT NULL,
                last_generated_at TIMESTAMPTZ NULL,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                CONSTRAINT uq_quality_deviation_ai_sessions_deviation_id UNIQUE
                (deviation_id)
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.deviation_ai_session_attachments (
                session_id UUID NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_type VARCHAR(100) NOT NULL,
                file_size INTEGER NOT NULL,
                storage_path TEXT NOT NULL,
                parsed_text TEXT NULL,
                parsed_summary TEXT NULL,
                parse_status VARCHAR(50) NOT NULL DEFAULT 'pending',
                parse_error TEXT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text("DELETE FROM quality.deviation_ai_session_attachments")
    )
    await db_session.execute(text("DELETE FROM quality.deviation_ai_sessions"))
    await db_session.execute(QualityAiAnalysisLog.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    await db_session.execute(
        text("DELETE FROM quality.deviation_ai_session_attachments")
    )
    await db_session.execute(text("DELETE FROM quality.deviation_ai_sessions"))
    await db_session.execute(QualityAiAnalysisLog.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


def _build_docx_bytes(text_value: str) -> bytes:
    document = Document()
    document.add_paragraph(text_value)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def _seed_deviation(db_session: AsyncSession, code: str) -> uuid.UUID:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code=code,
        title=f"{code}-title",
        description="原始偏差描述",
        status="pending_investigation",
    )
    db_session.add(deviation)
    await db_session.commit()
    return deviation.id


async def _async_config_stub() -> SimpleNamespace:
    return SimpleNamespace(model_name="test-model")


@pytest.mark.anyio
async def test_get_or_create_deviation_ai_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation_id = await _seed_deviation(db_session, "DEV-AI-SESSION-001")

    response = await client.get(f"/api/v1/quality/ai/deviations/{deviation_id}/session")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["deviation_id"] == str(deviation_id)
    assert payload["supplement_text"] == ""
    assert payload["attachments"] == []
    assert payload["deviation_analysis_payload"] is None
    assert payload["capa_suggestion_payload"] is None


@pytest.mark.anyio
async def test_update_deviation_ai_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation_id = await _seed_deviation(db_session, "DEV-AI-SESSION-002")

    response = await client.put(
        f"/api/v1/quality/ai/deviations/{deviation_id}/session",
        json={"supplement_text": "补充：现场温湿度波动，批记录有手工修订"},
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["supplement_text"]
        == "补充：现场温湿度波动，批记录有手工修订"
    )


@pytest.mark.anyio
async def test_upload_deviation_ai_session_attachment(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation_id = await _seed_deviation(db_session, "DEV-AI-SESSION-003")
    content = _build_docx_bytes("调查补充：批记录发现夜班清场后有异常擦拭痕迹。")

    response = await client.post(
        f"/api/v1/quality/ai/deviations/{deviation_id}/session/attachments",
        files={
            "file": (
                "note.docx",
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    attachment = response.json()["data"]
    assert attachment["file_name"] == "note.docx"
    assert attachment["parse_status"] == "completed"
    assert attachment["parsed_summary"]


@pytest.mark.anyio
async def test_regenerate_and_apply_deviation_ai_session(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation_id = await _seed_deviation(db_session, "DEV-AI-SESSION-004")
    captured_prompt: dict[str, str] = {}

    async def _fake_llm_chat_json(
        self: Any,  # noqa: ANN001
        messages: list[dict[Any, Any]],
        expected_keys: Any = None,  # noqa: ANN001
        temperature: Any = None,  # noqa: ANN001
        config_type: Any = "text",  # noqa: ANN001
    ) -> dict[str, Any]:
        captured_prompt["prompt"] = messages[0]["content"] if messages else ""
        return {
            "deviation_analysis": {
                "summary": "已结合补充信息完成偏差分析",
                "risk_level": "中",
                "risks": ["清场确认不充分"],
                "suggestions": ["补充清场复核记录"],
                "missing_info": ["需补充班组复盘结论"],
                "structured_fields": {
                    "preliminary_cause_analysis": "夜班清场执行不到位",
                    "capa_suggestions": "完善清场复核并增加双人确认",
                },
            },
            "capa_suggestion": {
                "summary": "建议以清场复核 CAPA 为主线",
                "risk_level": "中",
                "risks": ["若不整改，重复发生风险较高"],
                "suggestions": ["建立夜班清场点检表"],
                "missing_info": [],
                "structured_fields": {
                    "capa_suggestions": "建立夜班清场点检表并纳入班组长复核",
                },
            },
        }

    monkeypatch.setattr(
        "app.core.llm.client.LLMClient.chat_json",
        _fake_llm_chat_json,
    )
    monkeypatch.setattr(
        "app.modules.quality.service.quality_ai.get_config",
        lambda *_args, **_kwargs: _async_config_stub(),
    )

    await client.put(
        f"/api/v1/quality/ai/deviations/{deviation_id}/session",
        json={"supplement_text": "补充：已确认异常发生于夜班清场后"},
    )
    await client.post(
        f"/api/v1/quality/ai/deviations/{deviation_id}/session/attachments",
        files={
            "file": (
                "investigation.docx",
                _build_docx_bytes("附件说明：偏差发生前设备已完成常规点检。"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    regenerate_response = await client.post(
        f"/api/v1/quality/ai/deviations/{deviation_id}/session/regenerate"
    )

    assert regenerate_response.status_code == 200
    data = regenerate_response.json()["data"]
    assert data["deviation_analysis_payload"]["summary"] == "已结合补充信息完成偏差分析"
    assert data["capa_suggestion_payload"]["summary"] == "建议以清场复核 CAPA 为主线"
    assert "夜班清场后" in captured_prompt["prompt"]
    assert "附件说明" in captured_prompt["prompt"]

    apply_response = await client.post(
        f"/api/v1/quality/ai/deviations/{deviation_id}/session/apply",
        json={
            "section": "deviation_analysis",
            "field_keys": ["root_cause_analysis", "corrective_actions"],
        },
    )

    assert apply_response.status_code == 200

    refreshed = await db_session.get(Deviation, deviation_id)
    assert refreshed is not None
    assert refreshed.root_cause_analysis == "夜班清场执行不到位"
    assert refreshed.corrective_actions == "完善清场复核并增加双人确认"
