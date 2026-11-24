"""烟酒礼品仪表台 AI 分析测试（AsyncClient 真实调用路由，mock 统一 LLM 客户端）。"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.administration import service as admin_service
from app.modules.administration.schemas import TobaccoGiftDashboardStats
from app.modules.administration.service import (
    AdministrationTobaccoGiftService,
    _build_analysis_digest,
)

API = "/api/v1/administration/tobacco-gift/ai-analysis"

_VALID_RESULT = {
    "summary": "库存与领用整体平稳，无低于预警库存物品。",
    "insights": ["宽盒中华领用 91 件居首", "作废单 6 张占 11%"],
    "anomalies": [],
    "suggestions": ["关注烟类库存补货节奏", "控制单次领用数量"],
}


@pytest.fixture
def _mock_chat_json(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """替换统一 LLM 客户端的 chat_json；记录调用参数并可注入行为。"""
    state: dict[str, Any] = {
        "calls": 0,
        "result": dict(_VALID_RESULT),
        "error": None,
    }

    async def _chat_json(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        state["calls"] += 1
        state["kwargs"] = _kwargs
        error = state["error"]
        if error is not None:
            raise error
        return dict(state["result"])

    # 替换 administration 模块命名空间的 llm_client 引用（03c79aac 同款），
    # 不触碰单例：对单例实例属性打补丁会在 teardown 残留绑定方法，
    # 遮蔽同 shard 后续 quality/equipment 测试的类属性 LLM mock。
    monkeypatch.setattr(
        admin_service, "llm_client", SimpleNamespace(chat_json=_chat_json)
    )
    return state


# ---------- 摘要构建（纯函数） ----------


def _stats() -> TobaccoGiftDashboardStats:
    return TobaccoGiftDashboardStats(
        item_categories=3,
        item_total_value=100.0,
        item_total_count=35,
        requisitioned_total=5,
        inventory_by_item=[],
        requisition_by_item=[],
        value_by_item=[],
        requisition_by_employee=[],
    )


def test_digest_contains_kpis_alerts_and_status() -> None:
    digest = _build_analysis_digest(
        _stats(),
        ["五粮液：现有2，预警10"],
        {"已领用": 3, "已作废": 6, "总经理已审批": 21},
    )
    assert "物品品类：3" in digest
    assert "已领用物品总数（已领用状态单合计）：5" in digest
    assert "五粮液：现有2，预警10" in digest
    assert "已作废6" in digest


def test_digest_without_data_reports_placeholder() -> None:
    digest = _build_analysis_digest(_stats(), [], {})
    assert "低于预警库存的物品：无" in digest
    assert "无数据" in digest


# ---------- 端点场景 ----------


async def test_ai_analysis_success(
    client: Any, _mock_chat_json: dict[str, Any]
) -> None:
    resp = await client.post(API)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["summary"].startswith("库存与领用整体平稳")
    assert data["insights"] == _VALID_RESULT["insights"]
    assert data["anomalies"] == []
    assert data["suggestions"] == _VALID_RESULT["suggestions"]
    assert data["generated_at"]
    assert _mock_chat_json["calls"] == 1
    kwargs = _mock_chat_json["kwargs"]
    assert kwargs["expected_keys"] == [
        "summary",
        "insights",
        "anomalies",
        "suggestions",
    ]
    assert kwargs["timeout"] == admin_service._ANALYSIS_AI_TIMEOUT_SECONDS


async def test_ai_analysis_config_error_maps_503(
    client: Any, _mock_chat_json: dict[str, Any]
) -> None:
    _mock_chat_json["error"] = LLMConfigError()
    resp = await client.post(API)
    assert resp.status_code == 503
    assert "模型未配置" in resp.json()["message"]


async def test_ai_analysis_rate_limit_maps_429(
    client: Any, _mock_chat_json: dict[str, Any]
) -> None:
    _mock_chat_json["error"] = LLMRateLimitError("rate limited")
    resp = await client.post(API)
    assert resp.status_code == 429
    assert "限流" in resp.json()["message"]


async def test_ai_analysis_output_error_maps_502(
    client: Any, _mock_chat_json: dict[str, Any]
) -> None:
    _mock_chat_json["error"] = LLMOutputError("bad json")
    resp = await client.post(API)
    assert resp.status_code == 502
    assert "AI 生成失败" in resp.json()["message"]


async def test_ai_analysis_provider_error_maps_502(
    client: Any, _mock_chat_json: dict[str, Any]
) -> None:
    _mock_chat_json["error"] = LLMProviderError(500, "upstream down")
    resp = await client.post(API)
    assert resp.status_code == 502


async def test_ai_analysis_missing_summary_maps_502(
    client: Any, _mock_chat_json: dict[str, Any]
) -> None:
    _mock_chat_json["result"] = {
        "insights": ["只有发现"],
        "anomalies": [],
        "suggestions": [],
    }
    resp = await client.post(API)
    assert resp.status_code == 502
    assert "缺少总体概述" in resp.json()["message"]


async def test_service_validation_clamps_and_strips(
    monkeypatch: pytest.MonkeyPatch,
    _mock_chat_json: dict[str, Any],
) -> None:
    """输出清洗：去空、去首尾空格、按上限截断；generated_at 有值。"""

    async def _get_default(self: Any, page_key: str) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.administration.service.AdministrationRepository.get_default_bound_table",
        _get_default,
    )
    data = dict(_VALID_RESULT)
    data["insights"] = [
        "  带空格发现  ",
        "",
        123,
        "第四条",
        "第五条",
        "第六条",
        "第七条",
    ]
    _mock_chat_json["result"] = data

    service = AdministrationTobaccoGiftService(session=None)  # type: ignore[arg-type]
    analysis = await service.generate_ai_analysis()

    assert analysis.summary.startswith("库存与领用整体平稳")
    assert analysis.insights == [
        "带空格发现",
        "123",
        "第四条",
        "第五条",
        "第六条",
        "第七条",
    ]
    assert analysis.generated_at is not None
