from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.schemas.deviations import (
    SubmitInvestigationRequest,
    SubmitReviewRequest,
)
from app.modules.quality.service import quality_deviation as service


class _Result:
    def __init__(self, value: object = None, rows: list[object] | None = None) -> None:
        self.value = value
        self.rows = rows or []

    def scalar_one_or_none(self) -> object:
        return self.value

    def scalar_one(self) -> object:
        return self.value

    def scalar(self) -> int:
        return int(self.value or 0)

    def all(self) -> list[object]:
        return self.rows

    def scalars(self) -> _Result:
        return self


class _Db:
    def __init__(self, deviation: object | None = None) -> None:
        self.deviation = deviation
        self.get = AsyncMock(return_value=deviation)
        self.execute = AsyncMock(return_value=_Result(deviation))
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()
        self.add = Mock()


def _deviation(*, status: str = "draft", deleted: bool = False) -> SimpleNamespace:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid4(),
        deviation_code="PC-2608001",
        title="偏差",
        department="质量部",
        status=status,
        is_deleted=deleted,
        status_updated_at=now,
        updated_at=now,
        created_at=now,
        updated_by=None,
        returned_step=None,
        review_opinions=[],
        investigation_records=[],
        ai_analysis=None,
        level="一般",
        root_cause_category=None,
        description="原描述",
        final_code=None,
    )


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"report_status": "报告完成", "status": "草稿"}, "报告完成"),
        ({"qa_head_result": "通过", "status": "草稿"}, "通过"),
        ({"qa_result": "待审", "status": "草稿"}, "待审"),
        ({"status": "草稿"}, "草稿"),
        ({}, None),
    ],
)
def test_report_status_precedence(
    item: dict[str, object], expected: str | None
) -> None:
    assert service._pick_report_status(item) == expected


@pytest.mark.anyio
async def test_report_record_pull_maps_records_and_related_deviation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality.service import quality_feishu_sync as sync

    entity = SimpleNamespace(table_id="report-table", field_mappings={})
    runtime = SimpleNamespace(
        is_enabled=lambda: True,
        get_entity_config=lambda code, direction: entity,
    )
    records = [
        {
            "record_id": "report-1",
            "last_modified_time": "2026-08-20T08:00:00Z",
            "fields": {
                "偏差编号": "PC-2608001",
                "偏差内容": "偏差内容",
                "偏差报告": "报告链接",
                "涉及产品名称/批号": "产品/B1",
                "部门": "质量部",
                "报告人": [{"id": "ou_report", "name": "报告人"}],
                "部门负责人确认": "通过",
                "QA确认": "待审",
                "QA负责人确认": "待审",
                "报告状态": "处理中",
                "附件": [{"name": "调查.pdf", "url": "https://file"}],
            },
        }
    ]
    monkeypatch.setattr(
        sync.feishu_sync, "_resolve_runtime", AsyncMock(return_value=runtime)
    )
    monkeypatch.setattr(
        sync.feishu_sync,
        "search_records",
        AsyncMock(return_value=records),
    )
    monkeypatch.setattr(
        service.repository,
        "get_deviations_by_codes",
        AsyncMock(
            return_value=[SimpleNamespace(id=uuid4(), deviation_code="PC-2608001")]
        ),
    )
    result = await service._build_deviation_report_record_items_from_feishu(
        SimpleNamespace(), page=1, page_size=20
    )
    assert result["total"] == 1
    assert result["items"][0]["deviation_code"] == "PC-2608001"
    assert result["items"][0]["report_status"] == "处理中"
    assert result["items"][0]["reporters"][0]["id"] == "ou_report"

    monkeypatch.setattr(
        sync.feishu_sync,
        "_resolve_runtime",
        AsyncMock(
            return_value=SimpleNamespace(
                is_enabled=lambda: False,
                get_entity_config=lambda *args, **kwargs: None,
            )
        ),
    )
    empty = await service._build_deviation_report_record_items_from_feishu(
        SimpleNamespace(), page=2, page_size=5
    )
    assert empty == {"items": [], "total": 0, "page": 2, "page_size": 5}


@pytest.mark.anyio
async def test_deviation_report_lookup_code_generation_and_sync_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality.service import quality_feishu_sync as sync

    entity = SimpleNamespace(table_id="report-table", field_mappings={})
    runtime = SimpleNamespace(
        is_enabled=lambda: True,
        get_entity_config=lambda code, direction: entity,
    )
    record = {"record_id": "report-1", "fields": {"偏差编号": "PC-2608002"}}
    monkeypatch.setattr(
        sync.feishu_sync, "_resolve_runtime", AsyncMock(return_value=runtime)
    )
    monkeypatch.setattr(
        sync.feishu_sync, "search_records", AsyncMock(return_value=[record])
    )
    assert await service._search_deviation_report_record_codes_from_feishu(
        SimpleNamespace()
    ) == ["PC-2608002"]
    assert (
        await service._generate_monthly_deviation_code(
            SimpleNamespace(), datetime(2026, 8, 20, tzinfo=UTC)
        )
        == "PC-2608003"
    )
    monkeypatch.setattr(
        sync.feishu_sync,
        "search_records",
        AsyncMock(return_value=[{"record_id": "other", "fields": {}}]),
    )
    with pytest.raises(NotFoundException):
        await service.ensure_deviation_from_report_record(SimpleNamespace(), "missing")

    deviation_id = uuid4()
    monkeypatch.setattr(
        service.repository,
        "get_deviation_by_id",
        AsyncMock(return_value=SimpleNamespace(id=deviation_id)),
    )
    sync_mock = AsyncMock(return_value={"synced": True})
    monkeypatch.setattr(sync, "sync_deviation_report_record_to_feishu", sync_mock)
    result = await service.sync_deviation_report_record_to_feishu_by_ref(
        SimpleNamespace(), str(deviation_id)
    )
    assert result == {"synced": True}
    sync_mock.assert_awaited_once_with(SimpleNamespace(), deviation_id)


@pytest.mark.anyio
async def test_workflow_submit_complete_batch_and_resubmit_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation = _deviation(status="draft")
    db = _Db(deviation)
    monkeypatch.setattr(service, "_trigger_ai_analysis", AsyncMock())
    assert await service.submit_for_review(db, deviation.id, str(uuid4())) == {
        "success": True
    }
    assert deviation.status == "pending_ai_analysis"
    assert db.flush.await_count == 1

    deviation.status = "pending_ai_analysis"
    assert await service.complete_ai_analysis(
        db, deviation.id, {"risk": "low"}, str(uuid4())
    ) == {"success": True}
    assert deviation.status == "pending_investigation"
    assert deviation.ai_analysis == {"risk": "low"}

    missing = _deviation(deleted=True)
    db.get.side_effect = [deviation, missing, None]
    result = await service.batch_update_status(
        db, [deviation.id, missing.id, uuid4()], "closed", "system"
    )
    assert result["updated_count"] == 1
    assert result["failed_count"] == 2
    assert deviation.status == "closed"

    db.get.side_effect = None
    db.get.return_value = deviation
    deviation.status = "returned"
    deviation.returned_step = "qa_review"
    db.execute.return_value = _Result(deviation)
    assert await service.resubmit_deviation(db, deviation.id, "system") == {
        "success": True
    }
    assert deviation.status == "pending_qa_review"
    assert deviation.returned_step is None

    deviation.status = "draft"
    with pytest.raises(AppException, match="当前状态"):
        await service.complete_ai_analysis(db, deviation.id, None, "system")


@pytest.mark.anyio
async def test_investigation_review_and_final_code_workflow_branches() -> None:
    deviation = _deviation(status="pending_investigation")
    db = _Db(deviation)
    investigation = SubmitInvestigationRequest(
        description="更新调查",
        investigation_records=[{"content": "记录"}],
    )
    assert await service.submit_investigation(
        db, deviation.id, investigation, "u1"
    ) == {"success": True}
    assert deviation.status == "pending_dept_head_review"
    assert deviation.investigation_records == [{"content": "记录"}]

    deviation.status = "pending_dept_head_review"
    approved = SubmitReviewRequest(
        step="dept_head_review", result="approved", content="通过"
    )
    assert await service.submit_review(db, deviation.id, approved, "u1") == {
        "success": True
    }
    assert deviation.status == "pending_cross_dept_head_review"

    deviation.status = "pending_qa_review"
    approved_qa = SubmitReviewRequest(
        step="qa_review",
        result="approved",
        reason_category="设备故障",
        content="通过",
    )
    await service.submit_review(db, deviation.id, approved_qa, "u1")
    assert deviation.root_cause_category == "设备故障"

    deviation.status = "pending_qa_head_review"
    rejected = SubmitReviewRequest(step="qa_head_review", result="rejected")
    await service.submit_review(db, deviation.id, rejected, "u1")
    assert deviation.status == "returned"
    assert deviation.returned_step == "qa_head_review"

    deviation.status = "pending_final_code"
    assert await service.submit_final_code(db, deviation.id, "  FINAL-1  ", "u1") == {
        "success": True
    }
    assert deviation.status == "closed"
    assert deviation.final_code == "FINAL-1"
    deviation.status = "pending_final_code"
    with pytest.raises(AppException, match="最终编号不能为空"):
        await service.submit_final_code(db, deviation.id, " ", "u1")


@pytest.mark.anyio
async def test_department_confirmation_list_create_update_and_stopped_filters() -> None:
    existing = SimpleNamespace(
        id=uuid4(),
        department="质量部",
        week_key="2026-W34",
        production_status="running",
        deviation_status="none",
        confirmed_by_id=None,
        confirmed_at=datetime(2026, 8, 20, tzinfo=UTC),
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        updated_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    db = _Db(existing)
    db.execute.side_effect = [
        _Result(1),
        _Result(rows=[existing]),
        _Result(existing),
        _Result(rows=[("生产部",)]),
    ]
    listed = await service.get_department_confirmations(
        db, week_key="2026-W34", page=1, page_size=10
    )
    assert listed["total"] == 1
    assert listed["items"][0]["department"] == "质量部"

    data = SimpleNamespace(
        department="生产部",
        week_key="2026-W34",
        production_status="stopped",
        deviation_status="pending",
    )
    assert await service.confirm_production_status(db, data, "system") == {
        "success": True
    }
    assert existing.production_status == "stopped"
    db.execute.side_effect = [
        _Result(None),
        _Result(rows=[("生产部",)]),
    ]
    assert await service.confirm_production_status(db, data, "system") == {
        "success": True
    }
    assert db.add.called
    assert await service.get_stopped_departments(db, "2026-W34") == ["生产部"]


@pytest.mark.anyio
async def test_deviation_crud_and_report_record_upsert_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.quality.schemas.deviations import (
        CreateDeviationRequest,
        UpdateDeviationRequest,
    )
    from app.modules.quality.service import quality_feishu_sync as sync

    reporter = service.SelectedReporterContact(
        name="报告人", open_id="ou-1", department="生产部"
    )
    monkeypatch.setattr(
        service,
        "_resolve_selected_reporter_contact",
        AsyncMock(return_value=reporter),
    )
    monkeypatch.setattr(
        service,
        "_generate_monthly_deviation_code",
        AsyncMock(return_value="PC-2608004"),
    )
    monkeypatch.setattr(
        sync,
        "auto_sync_deviation_after_write",
        AsyncMock(),
    )
    created = SimpleNamespace(id=uuid4(), deviation_code="PC-2608004")
    db = _Db()
    db.execute.return_value = _Result(created)
    result = await service.create_deviation(
        db,
        CreateDeviationRequest(
            title="  标题  ",
            department="生产部",
            reporter_open_id="ou-1",
            discovery_date="2026-08-20T08:00:00+00:00",
            description="  偏差内容 ",
            affected_items=" 产品/B1 ",
            cross_dept_reviewers=[{"department": "质量部", "investigators": ["u1"]}],
        ),
        "u1",
    )
    assert result == {"id": str(created.id), "code": "PC-2608004"}
    assert db.commit.await_count == 1

    deviation = _deviation(status="draft")
    db.execute.return_value = _Result(deviation)
    updated = await service.update_deviation(
        db,
        deviation.id,
        UpdateDeviationRequest(
            description="更新内容",
            discovery_date="2026-08-21T08:00:00Z",
            investigation_records=[{"content": "调查"}],
            status="pending_investigation",
        ),
        "u1",
    )
    assert updated == {"success": True}
    assert deviation.description == "更新内容"
    assert deviation.status == "pending_investigation"
    assert deviation.discovery_date.tzinfo is not None

    monkeypatch.setattr(service, "record_audit_log", AsyncMock())
    deleted = await service.delete_deviation(db, deviation.id, uuid4())
    assert deleted == {"success": True}
    assert deviation.is_deleted is True

    entity = SimpleNamespace(table_id="report-table", field_mappings={})
    runtime = SimpleNamespace(
        is_enabled=lambda: True,
        get_entity_config=lambda *_args, **_kwargs: entity,
    )
    record = {
        "record_id": "report-2",
        "fields": {
            "偏差编号": "PC-2608005",
            "偏差内容": "飞书偏差",
            "偏差报告": "报告正文",
            "涉及产品名称/批号": "产品/B2",
            "部门": "质量部",
            "报告人": "张三",
            "报告时间": "2026-08-20T08:00:00Z",
        },
    }
    monkeypatch.setattr(
        sync.feishu_sync, "_resolve_runtime", AsyncMock(return_value=runtime)
    )
    monkeypatch.setattr(
        sync.feishu_sync, "search_records", AsyncMock(return_value=[record])
    )
    monkeypatch.setattr(
        service.repository,
        "get_deviation_by_code",
        AsyncMock(return_value=None),
    )
    imported = SimpleNamespace(id=uuid4(), deviation_code="PC-2608005")
    monkeypatch.setattr(
        service.repository,
        "create_deviation",
        AsyncMock(return_value=imported),
    )
    monkeypatch.setattr(sync, "_mark_sync_success", AsyncMock())
    db.execute.return_value = _Result(None)
    upserted = await service.ensure_deviation_from_report_record(db, "report-2")
    assert upserted == {
        "deviation_id": str(imported.id),
        "deviation_code": "PC-2608005",
        "created": True,
    }
    sync._mark_sync_success.assert_awaited_once()
