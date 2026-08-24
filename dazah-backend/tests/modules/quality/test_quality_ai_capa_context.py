from __future__ import annotations

import uuid
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.ai_analysis_log import QualityAiAnalysisLog
from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.deviations import Deviation

SimpleNamespace: Any = _SimpleNamespace


@pytest.fixture(autouse=True)
async def _clean_tables(db_session: AsyncSession) -> Any:
    await db_session.execute(QualityAiAnalysisLog.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(CAPA.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    await db_session.execute(QualityAiAnalysisLog.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(CAPA.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.mark.anyio
async def test_capa_ai_includes_deviation_context_when_linked(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CAPA AI 分析时，如果找到关联偏差，输入快照应包含偏差完整详情。"""
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="PC2505001",
        title="甩干异常",
        description="甩干过程中出现异常振动",
        root_cause_analysis="设备老化导致轴承磨损",
        corrective_actions="更换轴承并加强日常检查",
    )
    db_session.add(deviation)
    await db_session.flush()
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-PC2505001",
        title="轴承更换计划",
        deviation_id=deviation.id,
    )
    db_session.add(capa)
    await db_session.commit()

    captured_input: dict[Any, Any] = {}

    async def _fake_llm_chat_json(
        self: Any,  # noqa: ANN001
        messages: list[dict[Any, Any]],
        expected_keys: Any = None,  # noqa: ANN001
        temperature: Any = None,  # noqa: ANN001
        config_type: Any = "text",  # noqa: ANN001
    ) -> dict[str, Any]:
        captured_input["prompt"] = messages[0]["content"] if messages else ""
        return {
            "summary": "CAPA 已对准偏差根因",
            "risk_level": "低",
            "risks": [],
            "suggestions": [],
            "missing_info": [],
            "structured_fields": {},
        }

    monkeypatch.setattr(
        "app.core.llm.client.LLMClient.chat_json",
        _fake_llm_chat_json,
    )
    monkeypatch.setattr(
        "app.modules.quality.service.quality_ai.get_config",
        lambda *_args, **_kwargs: _async_config_stub(),
    )

    response = await client.post(f"/api/v1/quality/ai/capas/{capa.id}/analyze")

    assert response.status_code == 200
    prompt = captured_input.get("prompt", "")
    assert "PC2505001" in prompt
    assert "甩干异常" in prompt
    assert "甩干过程中出现异常振动" in prompt
    assert "设备老化导致轴承磨损" in prompt
    assert "更换轴承并加强日常检查" in prompt


@pytest.mark.anyio
async def test_capa_ai_continues_without_deviation_context_when_not_linked(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CAPA AI 分析时，如果未找到关联偏差，仍能正常分析，但输入快照不包含偏差详情。"""
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-UNLINKED-001",
        title="无关联偏差的CAPA",
    )
    db_session.add(capa)
    await db_session.commit()

    captured_input: dict[Any, Any] = {}

    async def _fake_llm_chat_json(
        self: Any,  # noqa: ANN001
        messages: list[dict[Any, Any]],
        expected_keys: Any = None,  # noqa: ANN001
        temperature: Any = None,  # noqa: ANN001
        config_type: Any = "text",  # noqa: ANN001
    ) -> dict[str, Any]:
        captured_input["prompt"] = messages[0]["content"] if messages else ""
        return {
            "summary": "仅基于CAPA自身分析",
            "risk_level": "中",
            "risks": ["缺少偏差背景"],
            "suggestions": ["建议补充偏差来源"],
            "missing_info": [],
            "structured_fields": {},
        }

    monkeypatch.setattr(
        "app.core.llm.client.LLMClient.chat_json",
        _fake_llm_chat_json,
    )
    monkeypatch.setattr(
        "app.modules.quality.service.quality_ai.get_config",
        lambda *_args, **_kwargs: _async_config_stub(),
    )

    response = await client.post(f"/api/v1/quality/ai/capas/{capa.id}/analyze")

    assert response.status_code == 200
    prompt = captured_input.get("prompt", "")
    assert "CAPA-UNLINKED-001" in prompt
    assert "无关联偏差的CAPA" in prompt
    # 不应包含偏差编号或偏差描述
    assert "PC2505" not in prompt
    assert "偏差编号" not in prompt
    assert "偏差描述" not in prompt


async def _async_config_stub() -> Any:
    return SimpleNamespace(model_name="test-model")
