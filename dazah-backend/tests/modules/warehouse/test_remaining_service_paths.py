from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.warehouse import feishu_fields
from app.modules.warehouse.service import WarehouseService


def _service() -> WarehouseService:
    service = WarehouseService.__new__(WarehouseService)
    service.repo = SimpleNamespace(
        save_analysis_profile=AsyncMock(),
        save_prompt_version=AsyncMock(),
        get_analysis_profile=AsyncMock(),
        list_prompt_versions=AsyncMock(return_value=[]),
        next_prompt_version=AsyncMock(return_value=2),
        get_prompt_version=AsyncMock(),
        save_analysis_run=AsyncMock(),
        save_analysis_result=AsyncMock(),
        get_analysis_result=AsyncMock(return_value=None),
        get_analysis_run=AsyncMock(),
        session=SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock()),
    )
    return service


def test_feishu_field_value_and_detail_conversions_cover_supported_types() -> None:
    assert feishu_fields.field_type_name("2") == "数字"
    assert feishu_fields.field_type_name("bad") == ""
    assert feishu_fields.field_type_name(999) == "未知(999)"
    assert feishu_fields.is_readonly_field(19)
    assert feishu_fields.is_view_only_field("17")
    assert feishu_fields.is_editable_field(1)
    assert not feishu_fields.is_editable_field("bad")

    assert feishu_fields.build_feishu_cell_value(1, 12) == "12"
    assert feishu_fields.build_feishu_cell_value(13, 12) == "12"
    assert feishu_fields.build_feishu_cell_value(2, "1,200.5") == 1200.5
    assert feishu_fields.build_feishu_cell_value(2, "not-a-number") is None
    assert feishu_fields.build_feishu_cell_value(3, "正常") == "正常"
    assert feishu_fields.build_feishu_cell_value(4, "A, B,,") == ["A", "B"]
    assert feishu_fields.build_feishu_cell_value(4, ["A", None, ""]) == ["A"]
    assert feishu_fields.build_feishu_cell_value(5, "2026-08-26")
    assert feishu_fields.build_feishu_cell_value(7, "是") is True
    assert feishu_fields.build_feishu_cell_value(7, "no") is False
    assert feishu_fields.build_feishu_cell_value(15, "https://example.test") == {
        "text": "https://example.test",
        "link": "https://example.test",
    }
    assert (
        feishu_fields.build_feishu_cell_value(15, {"link": "https://example.test"})[
            "link"
        ]
        == "https://example.test"
    )
    assert feishu_fields.build_feishu_cell_value(19, "formula") is None

    assert feishu_fields.format_detail_value(5, 1_756_000_000_000)
    assert feishu_fields.format_detail_value(5, "1756000000000")
    assert feishu_fields.format_detail_value(5, "not-a-date") == "not-a-date"
    assert feishu_fields.format_detail_value(7, 1) is True
    assert feishu_fields.format_detail_value(11, {"id": "u1", "name": "张三"}) == [
        {"id": "u1", "name": "张三", "avatar_url": ""}
    ]
    assert feishu_fields.format_detail_value(
        17, [{"file_token": "f1", "name": "a", "tmp_url": "u"}]
    ) == [{"file_token": "f1", "name": "a", "url": "u"}]
    assert (
        feishu_fields.format_detail_value(15, {"text": "文档", "link": "url"}) == "url"
    )
    assert feishu_fields.format_detail_value(18, [1, 2]) == ["1", "2"]


@pytest.mark.asyncio
async def test_analysis_profile_prompt_and_run_lifecycle() -> None:
    service = _service()
    profile_id = uuid4()
    prompt_id = uuid4()
    service.repo.save_analysis_profile.side_effect = lambda profile: setattr(
        profile, "id", profile_id
    )
    service.repo.save_prompt_version.side_effect = lambda prompt: setattr(
        prompt, "id", prompt_id
    )
    data = SimpleNamespace(
        name="库存分析",
        resource_ids=[uuid4()],
        analysis_goal="分析库存",
        input_field_ids=["数量"],
        time_field_id=None,
        metric_field_ids=["数量"],
        dimension_field_ids=["库区"],
        quality_rules={},
        output_schema={},
        max_raw_rows=50,
        auto_run=False,
        allow_sensitive_fields=False,
        system_prompt="请分析",
        business_context="库存",
        focus_points=["异常"],
    )
    created = await service.create_analysis_profile(data)
    assert created.id == profile_id
    assert created.prompt_version == 1
    service.repo.get_analysis_profile.return_value = SimpleNamespace(
        id=profile_id,
        name="库存分析",
        resource_ids=[str(data.resource_ids[0])],
        analysis_goal="分析库存",
        input_field_ids=["数量"],
        time_field_id=None,
        metric_field_ids=["数量"],
        dimension_field_ids=["库区"],
        max_raw_rows=50,
        auto_run=False,
        allow_sensitive_fields=False,
    )
    draft = await service.create_prompt_draft(profile_id, data)
    assert draft.status == "draft"
    draft_obj = SimpleNamespace(
        id=uuid4(),
        profile_id=profile_id,
        version=2,
        system_prompt="新提示词",
        business_context=None,
        focus_points=[],
        status="draft",
        published_at=None,
    )
    service.repo.get_prompt_version.return_value = draft_obj
    published_obj = SimpleNamespace(
        id=prompt_id,
        profile_id=profile_id,
        version=1,
        system_prompt="旧提示词",
        business_context=None,
        focus_points=[],
        status="published",
        published_at=datetime.now(UTC),
    )
    service.repo.list_prompt_versions.return_value = [published_obj, draft_obj]
    published = await service.publish_prompt_version(profile_id, draft_obj.id)
    assert published.status == "published"
    assert draft_obj.status == "published"
    assert published_obj.status == "draft"

    service.repo.list_prompt_versions.return_value = [published]
    service.repo.save_analysis_run.side_effect = lambda run: setattr(run, "id", uuid4())
    service.repo.get_analysis_result.return_value = SimpleNamespace(
        metrics={"resource_count": 1},
        risks=[],
        trends=[],
        feasibility={"status": "待人工确认"},
        recommendations=[],
        evidence=[],
        confidence=None,
    )
    service._page_key_for_binding = AsyncMock(  # type: ignore[method-assign]
        side_effect=AppException(status_code=404, message="映射不存在")
    )
    run = await service.run_analysis(profile_id)
    assert run.status == "success"
    assert run.result is not None
    assert run.result["metrics"]["resource_count"] == 1
    assert service.repo.session.commit.await_count >= 2

    service.repo.get_analysis_profile.return_value = None
    with pytest.raises(AppException, match="分析配置不存在"):
        await service.run_analysis(uuid4())


@pytest.mark.asyncio
async def test_analysis_run_failure_rolls_back_and_response_helpers() -> None:
    service = _service()
    profile_id = uuid4()
    service.repo.get_analysis_profile.return_value = SimpleNamespace(
        id=profile_id,
        name="分析",
        resource_ids=[],
        analysis_goal="目标",
        input_field_ids=[],
        time_field_id=None,
        metric_field_ids=[],
        dimension_field_ids=[],
        max_raw_rows=10,
        auto_run=False,
        allow_sensitive_fields=False,
    )
    prompt = SimpleNamespace(id=uuid4(), profile_id=profile_id, status="published")
    service.repo.list_prompt_versions.return_value = [prompt]
    service.repo.save_analysis_result.side_effect = RuntimeError("database")
    with pytest.raises(AppException, match="仓储分析运行失败"):
        await service.run_analysis(profile_id)
    service.repo.session.rollback.assert_awaited_once()

    run = SimpleNamespace(
        id=uuid4(),
        profile_id=profile_id,
        trigger_type="manual",
        status="queued",
        started_at=datetime.now(UTC),
        completed_at=None,
        error_message=None,
    )
    service.repo.get_analysis_result.return_value = SimpleNamespace(
        metrics={"a": 1},
        risks=[],
        trends=[],
        feasibility={},
        recommendations=[],
        evidence=[],
        confidence=0.9,
    )
    response = await service._analysis_run_response(run)
    assert response.result == {
        "metrics": {"a": 1},
        "risks": [],
        "trends": [],
        "feasibility": {},
        "recommendations": [],
        "evidence": [],
        "confidence": 0.9,
    }

    service.repo.get_analysis_run.return_value = None
    with pytest.raises(AppException, match="分析运行记录不存在"):
        await service.get_analysis_run_response(uuid4())
