import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.agent.capability_search import capability_score, schema_search_text
from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.schemas import AgentToolSearchRequest


def test_action_synonyms_and_provider_examples_match():
    schema = {
        "description": "偏差问题定位",
        "properties": {
            "kind": {
                "description": "质量异常台账",
                "examples": ["超标调查", "趋势分析"],
                "default": "private-default",
            },
        },
    }
    text = schema_search_text(schema)
    assert "超标调查" in text and "private-default" not in text
    assert (
        capability_score("帮我找找质量异常", "quality.list_events 查询质量事件", text)
        > 0
    )
    assert capability_score("草拟偏差", "quality.create_deviation 创建偏差草稿") > 0
    assert (
        capability_score("汇总异常", "quality.aggregate_events 统计质量事件", text) > 0
    )


def test_exact_operation_and_summary_outrank_schema_fuzzy_match():
    exact = capability_score("quality.list_events", "quality.list_events 查询质量事件")
    fuzzy = capability_score(
        "quality.list_events", "custom.list", "quality.list_events"
    )
    assert exact > fuzzy > 0
    assert capability_score("不存在的意图", "custom.list 仓库物料") == 0
    assert capability_score("帮我看看一下", "custom.list 查询仓储记录") == 0
    assert capability_score("", "custom.list") == 1


@pytest.mark.asyncio
async def test_ranking_never_sees_unauthorized_or_wrong_module_candidates(monkeypatch):
    from app.modules.agent import catalog

    service = ToolCatalogService()
    service.synchronize = AsyncMock()
    service._trusted_user = AsyncMock(return_value=SimpleNamespace(role="user"))
    service.access_scope.get_current_scope = AsyncMock(
        return_value=SimpleNamespace(tool_names=["custom.allowed", "other.allowed"])
    )

    def row(operation, module, summary):
        return SimpleNamespace(
            operation=operation,
            module=module,
            summary=summary,
            input_schema={"description": "异常台账"},
        )

    rows = [
        row("custom.hidden", "custom", "精确异常台账"),
        row("custom.allowed", "custom", "查询台账"),
        row("other.allowed", "other", "异常台账"),
    ]
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: rows)
            )
        )
    )
    monkeypatch.setattr(
        catalog.tool_registry,
        "get",
        lambda operation: SimpleNamespace(module="custom", required_roles=()),
    )
    seen = []

    def rank(query, primary, schema_text):
        seen.append(primary)
        return capability_score(query, primary, schema_text)

    monkeypatch.setattr(catalog, "capability_score", rank)
    monkeypatch.setattr(catalog, "_catalog_entry", lambda item: item)
    request = AgentToolSearchRequest.model_validate(
        {
            "query": "异常台账",
            "module": "custom",
            "limit": 1,
            "subject": {
                "user_id": str(uuid.uuid4()),
                "tenant_id": "test",
                "source": "web",
            },
        }
    )
    result = await service.search(db, request)
    assert [item.operation for item in result] == ["custom.allowed"]
    assert len(seen) == 1 and "hidden" not in seen[0] and "other" not in seen[0]
