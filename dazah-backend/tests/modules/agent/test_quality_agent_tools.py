import pytest

from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import EmptyToolInput, ToolContext, tool_registry
from app.modules.quality import agent_tools
from app.modules.quality.schemas import DeviationStatistics
from app.platform.identity.page_policy import (
    PAGES_BY_KEY,
    QUALITY_PRODUCT_PAGES,
    api_binding_for_route,
)


def test_quality_agent_tools_project_reviewed_page_contracts():
    ensure_agent_tools_registered()

    quality_tools = [
        spec for spec in tool_registry.list() if spec.module == "quality"
    ]

    assert quality_tools
    assert all(spec.page_keys for spec in quality_tools)
    for spec in quality_tools:
        for page_key in spec.page_keys:
            assert page_key in PAGES_BY_KEY

        binding = api_binding_for_route(spec.method, "/api/v1" + spec.path)
        if binding is not None:
            assert spec.page_keys == binding.page_keys
            assert spec.sensitive_action == binding.sensitive_action


def test_quality_agent_tool_decorator_keeps_explicit_contracts():
    ensure_agent_tools_registered()

    cpv = tool_registry.require("quality.create_cpv_product")
    assert cpv.page_keys == QUALITY_PRODUCT_PAGES
    assert cpv.sensitive_action is None

    feishu_pull = tool_registry.require("quality.pull_feishu_validations")
    assert feishu_pull.page_keys == ("quality:validation:validation-plans",)
    assert feishu_pull.sensitive_action == "sync_config"


def test_deviation_statistics_tool_is_registered_read_only():
    ensure_agent_tools_registered()

    spec = tool_registry.require("quality.get_deviation_statistics")

    assert spec.write is False
    assert spec.path == "/quality/statistics/deviations"


def _deviation_statistics_context() -> ToolContext:
    return ToolContext(
        db=object(),  # type: ignore[arg-type]
        session_id=None,
        user_id=None,
        user=None,
        reason=None,
        raw_request=object(),
    )


@pytest.mark.anyio
async def test_get_deviation_statistics_delegates_to_quality_statistics(
    monkeypatch: pytest.MonkeyPatch,
):
    statistics = DeviationStatistics(
        total=3,
        closed_count=2,
        major_count=1,
        level_distribution=[{"name": "major", "count": 1}],
        department_distribution=[{"name": "QC", "count": 3}],
        root_cause_distribution=[{"name": "人员", "count": 2}],
        monthly_trend=[{"month": "2026-09", "count": 3}],
    )
    received_db: list[object] = []

    async def fake_statistics(db: object) -> DeviationStatistics:
        received_db.append(db)
        return statistics

    monkeypatch.setattr(
        agent_tools.quality_statistics, "get_deviation_statistics", fake_statistics
    )

    result = await agent_tools.get_deviation_statistics(
        _deviation_statistics_context(), EmptyToolInput()
    )

    assert len(received_db) == 1
    # 人机料法环口径字段原样透出，不再经过旧 quality_management 死实现
    assert result["total"] == 3
    assert result["closed_count"] == 2
    assert result["major_count"] == 1
    assert result["root_cause_distribution"] == [{"name": "人员", "count": 2}]
    assert result["monthly_trend"] == [{"month": "2026-09", "count": 3}]
