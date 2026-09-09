"""检验进度 API 端点契约测试（overview / ai-analysis / 详情附加字段）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.modules.warehouse import inspection_progress_ai as ai_module


@pytest.fixture(autouse=True)
async def _ensure_transition_table() -> None:
    """API 测试走 client 会话，需在测试库引擎级建表（幂等提交）。

    CI 数据库由迁移建表；本地 dazah_test 状态不全，这里补齐。
    """
    from app.modules.warehouse.models import MaterialStatusTransition
    from tests.conftest import _test_engine

    async with _test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_db: MaterialStatusTransition.__table__.create(
                sync_db, checkfirst=True
            )
        )


async def test_overview_endpoint_contract(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/warehouse/inspection-progress/overview",
        params={"scope": "raw", "days": 7},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["scope"] == "raw"
    assert data["scope_label"] == "原辅料及包材"
    assert data["start_date"] == "2026-09-09"
    assert "pending_count" in data["current"]
    assert "completed_count" in data["window"]
    assert isinstance(data["daily"], list)
    assert len(data["daily"]) == 7


async def test_overview_endpoint_rejects_invalid_scope(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/warehouse/inspection-progress/overview",
        params={"scope": "hardware"},
    )
    assert response.status_code == 422


async def test_ai_analysis_endpoint_contract(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ai_module.llm_client,
        "chat_json",
        AsyncMock(
            return_value={
                "overall_status": "正常",
                "risk_level": "低",
                "key_findings": [],
                "suggestions": [],
                "summary_text": "ok",
            }
        ),
    )
    response = await client.get(
        "/api/v1/warehouse/inspection-progress/ai-analysis",
        params={"scope": "product", "days": 7, "force": True},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["scope_label"] == "成品"
