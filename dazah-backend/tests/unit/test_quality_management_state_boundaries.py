from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.schemas import (
    CreateCapaRequest,
    CreateChangeRequest,
    SubmitInvestigationRequest,
    SubmitReviewRequest,
    UpdateCapaRequest,
    UpdateChangeRequest,
    UpdateDeviationRequest,
)
from app.modules.quality.service import quality_feishu_pages, quality_feishu_sync
from app.modules.quality.service import quality_management as service


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object:
        return self.value


def _db(item: object) -> SimpleNamespace:
    return SimpleNamespace(
        execute=AsyncMock(return_value=_ScalarResult(item)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        flush=AsyncMock(),
        add=Mock(),
    )


@pytest.mark.anyio
async def test_deviation_update_close_reopen_delete_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation_id = uuid.uuid4()
    deviation = SimpleNamespace(
        id=deviation_id,
        status="draft",
        is_deleted=False,
        review_opinions=[],
        returned_step=None,
    )
    db = _db(deviation)
    auto_sync = AsyncMock()
    monkeypatch.setattr(
        quality_feishu_sync,
        "auto_sync_deviation_after_write",
        auto_sync,
    )

    closed = UpdateDeviationRequest.model_construct(
        title="更新后的偏差",
        discovery_date="2026-07-01T08:00:00+00:00",
        investigation_completed_at="2026-07-02T08:00:00+00:00",
        ai_analysis={"risk": "medium"},
        is_closed=True,
        close_time="2026-07-03T08:00:00+00:00",
    )
    assert await service.update_deviation(
        db,
        deviation_id,
        closed,
        "user-1",
    ) == {"success": True}
    assert deviation.status == "closed"
    assert deviation.ai_analysis == {"risk": "medium"}
    assert deviation.investigation_completed_at.isoformat().startswith(
        "2026-07-02"
    )
    auto_sync.assert_awaited_once_with(db, deviation_id)

    reopened = UpdateDeviationRequest.model_construct(
        is_closed=False,
        investigation_completed_at=None,
    )
    await service.update_deviation(db, deviation_id, reopened, "user-1")
    assert deviation.status == "draft"
    assert deviation.investigation_completed_at is None

    assert await service.delete_deviation(db, deviation_id) == {
        "success": True
    }
    assert deviation.is_deleted is True

    db.commit.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await service.delete_deviation(db, deviation_id)
    db.rollback.assert_awaited()


@pytest.mark.anyio
async def test_deviation_investigation_and_review_state_machine() -> None:
    deviation_id = uuid.uuid4()
    deviation = SimpleNamespace(
        id=deviation_id,
        status="pending_investigation",
        review_opinions=[],
        returned_step=None,
        is_deleted=False,
    )
    db = _db(deviation)

    investigation = SubmitInvestigationRequest.model_construct(
        description="完成根因调查",
        investigation_records=[{"root_cause": "密封件磨损"}],
    )
    assert await service.submit_investigation(
        db,
        deviation_id,
        investigation,
        "investigator",
    ) == {"success": True}
    assert deviation.status == "pending_dept_head_review"
    assert deviation.description == "完成根因调查"

    rejected = SubmitReviewRequest.model_construct(
        step="dept_head_review",
        content="请补充证据",
        result="rejected",
        reason_category=None,
        deviation_level=None,
    )
    assert await service.submit_review(
        db,
        deviation_id,
        rejected,
        "department-head",
    ) == {"success": True}
    assert deviation.status == "returned"
    assert deviation.returned_step == "dept_head_review"

    assert await service.resubmit_deviation(
        db,
        deviation_id,
        "investigator",
    ) == {"success": True}
    assert deviation.status == "pending_dept_head_review"
    assert deviation.returned_step is None

    deviation.status = "pending_qa_review"
    approved = SubmitReviewRequest.model_construct(
        step="qa_review",
        content="审核通过",
        result="approved",
        reason_category="设备",
        deviation_level=None,
    )
    await service.submit_review(db, deviation_id, approved, "qa")
    assert deviation.status == "pending_qa_head_review"
    assert deviation.root_cause_category == "设备"

    deviation.status = "pending_qa_head_review"
    head_approved = SubmitReviewRequest.model_construct(
        step="qa_head_review",
        content="负责人通过",
        result="approved",
        reason_category=None,
        deviation_level="major",
    )
    await service.submit_review(db, deviation_id, head_approved, "qa-head")
    assert deviation.level == "major"
    assert deviation.status == "pending_quality_head_review"

    deviation.status = "pending_final_code"
    assert await service.submit_final_code(
        db,
        deviation_id,
        " FINAL-001 ",
        "quality-head",
    ) == {"success": True}
    assert deviation.final_code == "FINAL-001"
    assert deviation.status == "closed"


@pytest.mark.anyio
async def test_deviation_state_machine_rejects_invalid_boundaries() -> None:
    deviation_id = uuid.uuid4()
    deviation = SimpleNamespace(
        id=deviation_id,
        status="draft",
        review_opinions=[],
        returned_step=None,
        is_deleted=False,
    )
    db = _db(deviation)

    with pytest.raises(ValueError, match="待调查"):
        await service.submit_investigation(
            db,
            deviation_id,
            SubmitInvestigationRequest.model_construct(),
            "user",
        )
    with pytest.raises(ValueError, match="不在审核流程"):
        await service.submit_review(
            db,
            deviation_id,
            SubmitReviewRequest.model_construct(
                step="qa_review",
                content="x",
                result="approved",
            ),
            "user",
        )
    with pytest.raises(ValueError, match="退回状态"):
        await service.resubmit_deviation(db, deviation_id, "user")
    with pytest.raises(ValueError, match="不允许提交最终编号"):
        await service.submit_final_code(db, deviation_id, "X", "user")

    db.execute.return_value = _ScalarResult(None)
    with pytest.raises(ValueError, match="not found"):
        await service.delete_deviation(db, deviation_id)


@pytest.mark.anyio
async def test_change_create_update_delete_and_best_effort_feishu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(None)
    monkeypatch.setattr(
        service,
        "generate_next_change_code",
        AsyncMock(return_value="BG-2607001"),
    )
    monkeypatch.setattr(
        service.repository.quality_management,
        "exists_by_change_code",
        AsyncMock(return_value=False),
    )
    sync = AsyncMock(side_effect=RuntimeError("feishu unavailable"))
    delete_sync = AsyncMock(side_effect=RuntimeError("feishu unavailable"))
    monkeypatch.setattr(quality_feishu_pages, "sync_change_to_feishu", sync)
    monkeypatch.setattr(
        quality_feishu_pages,
        "delete_change_from_feishu",
        delete_sync,
    )

    create = CreateChangeRequest.model_construct(
        serial_number="1",
        change_code="",
        applicant_department="质量部",
        change_object="反应釜",
        change_content="更换密封件",
        impact_assessment="低风险",
        change_level="一级",
        application_date=None,
        planned_approval_date=None,
        execution_date=None,
        closure_date=None,
    )
    created = await service.create_change(db, create, "user")
    assert created["code"] == "BG-2607001"
    change = db.add.call_args.args[0]
    assert change.change_code == "BG-2607001"
    assert db.commit.await_count == 1

    db.execute.return_value = _ScalarResult(change)
    update = UpdateChangeRequest.model_construct(
        change_code=" BG-2607002 ",
        change_content="更新后的变更内容",
    )
    assert await service.update_change(
        db,
        change.id,
        update,
        "user",
    ) == {"success": True}
    assert change.change_code == "BG-2607002"

    assert await service.delete_change(db, change.id) == {"success": True}
    assert change.is_deleted is True
    delete_sync.assert_awaited_once_with(db, "BG-2607002")


@pytest.mark.anyio
async def test_change_duplicate_and_code_sequence_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(None)
    exists = AsyncMock(return_value=True)
    monkeypatch.setattr(
        service.repository.quality_management,
        "exists_by_change_code",
        exists,
    )
    create = CreateChangeRequest.model_construct(
        serial_number="1",
        change_code="BG-DUPLICATE",
        applicant_department="质量部",
        change_object="设备",
        change_content="内容",
        impact_assessment=None,
        change_level=None,
        application_date=None,
        planned_approval_date=None,
        execution_date=None,
        closure_date=None,
    )
    with pytest.raises(ValueError, match="已存在"):
        await service.create_change(db, create, "user")

    monkeypatch.setattr(
        service.repository.quality_management,
        "list_change_codes_by_prefix",
        AsyncMock(
            return_value=[
                "invalid",
                f"BG-{datetime.now():%y%m}001",
                f"BG-{datetime.now():%y%m}009",
            ]
        ),
    )
    code = await service.generate_next_change_code(db)
    assert code.endswith("010")


@pytest.mark.anyio
async def test_capa_create_update_delete_and_commit_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _db(None)
    auto_sync = AsyncMock()
    monkeypatch.setattr(
        quality_feishu_sync,
        "auto_sync_capa_after_write",
        auto_sync,
    )
    create = CreateCapaRequest.model_construct(
        title="更换密封件",
        deviation_id=None,
        source="deviation",
        source_code="DEV-001",
        category="corrective",
        root_cause_category="equipment",
        non_conformity_description="密封失效",
        root_cause_analysis="磨损",
        capa_content="更换并复核",
        capa_items=[],
        executors=["张三"],
        expected_completion_date="2026-08-01T00:00:00+00:00",
        reporter="李四",
    )
    created = await service.create_capa(db, create, "user")
    capa = db.add.call_args.args[0]
    assert created["id"] == str(capa.id)
    assert capa.status == "draft"
    auto_sync.assert_awaited_once_with(db, capa.id)

    db.execute.return_value = _ScalarResult(capa)
    update = UpdateCapaRequest.model_construct(
        title="更换密封件并验证",
        expected_completion_date="2026-08-02T00:00:00+00:00",
        capa_items=[{"action": "更换"}],
        status="in_progress",
    )
    assert await service.update_capa(
        db,
        capa.id,
        update,
        "user",
    ) == {"success": True}
    assert capa.expected_completion_date.isoformat().startswith("2026-08-02")

    assert await service.delete_capa(db, capa.id) == {"success": True}
    assert capa.is_deleted is True

    db.commit.side_effect = RuntimeError("database unavailable")
    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.delete_capa(db, capa.id)
    db.rollback.assert_awaited()


@pytest.mark.anyio
async def test_deviation_workflow_batch_and_auto_fill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation_id = uuid.uuid4()
    user_id = uuid.uuid4()
    deviation = SimpleNamespace(
        id=deviation_id,
        is_deleted=False,
        status="draft",
        ai_analysis={
            "structured_deviation_description": "AI 偏差描述",
            "preliminary_cause_analysis": "AI 根因",
            "capa_suggestions": "AI CAPA 建议",
        },
        investigation_records=[
            {
                "nonconformityDescription": "调查偏差描述",
                "rootCauseAnalysis": "调查根因",
                "capaProposals": [
                    {"summary": "更换密封件"},
                    {"content": "复核压差"},
                ],
            }
        ],
        description="原始描述",
        title="压差偏差",
    )
    db = SimpleNamespace(
        get=AsyncMock(return_value=deviation),
        flush=AsyncMock(),
    )

    created_coroutines = []

    def _capture_task(coro):
        created_coroutines.append(coro)
        coro.close()
        return Mock()

    monkeypatch.setattr(asyncio, "create_task", _capture_task)
    assert await service.submit_for_review(
        db,
        deviation_id,
        str(user_id),
    ) == {"success": True}
    assert deviation.status == "pending_ai_analysis"
    assert created_coroutines

    assert await service.complete_ai_analysis(
        db,
        deviation_id,
        {"risk": "high"},
        str(user_id),
    ) == {"success": True}
    assert deviation.status == "pending_investigation"
    assert deviation.ai_analysis == {"risk": "high"}

    deviation.ai_analysis = {
        "structured_deviation_description": "AI 偏差描述",
        "preliminary_cause_analysis": "AI 根因",
        "capa_suggestions": "AI CAPA 建议",
    }
    filled = await service.auto_fill_from_deviation(db, deviation_id)
    assert filled["non_conformity_description"] == "调查偏差描述"
    assert filled["root_cause_analysis"] == "调查根因"
    assert filled["capa_content"] == "1. 更换密封件\n2. 复核压差"

    missing_id = uuid.uuid4()
    failing_id = uuid.uuid4()

    async def _get(_model, item_id):
        if item_id == missing_id:
            return None
        if item_id == failing_id:
            raise RuntimeError("lookup failed")
        return deviation

    db.get.side_effect = _get
    batch = await service.batch_update_status(
        db,
        [deviation_id, missing_id, failing_id],
        "closed",
        "system",
    )
    assert batch["updated_count"] == 1
    assert batch["failed_count"] == 2
    assert {item["reason"] for item in batch["failures"]} == {
        "偏差不存在",
        "lookup failed",
    }


@pytest.mark.anyio
async def test_department_confirmation_create_update_and_queries() -> None:
    existing = SimpleNamespace(
        production_status="running",
        deviation_status="none",
    )
    scalar_result = SimpleNamespace(
        scalar_one_or_none=lambda: existing,
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=scalar_result),
        add=Mock(),
        flush=AsyncMock(),
    )
    data = SimpleNamespace(
        department="生产部",
        week_key="2026-W30",
        production_status="stopped",
        deviation_status="open",
    )
    assert await service.confirm_production_status(
        db,
        data,
        "system",
    ) == {"success": True}
    assert existing.production_status == "stopped"
    assert existing.deviation_status == "open"

    db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: None,
    )
    await service.confirm_production_status(db, data, "system")
    db.add.assert_called_once()

    db.execute.side_effect = [
        SimpleNamespace(all=lambda: [("生产部",), ("工程部",)]),
        SimpleNamespace(all=lambda: [("质量部",), ("生产部",)]),
    ]
    assert await service.get_stopped_departments(db, "2026-W30") == [
        "生产部",
        "工程部",
    ]
    assert await service.get_capa_departments(db) == ["质量部", "生产部"]


@pytest.mark.anyio
async def test_capa_full_workflow_and_execution_tracks() -> None:
    capa_id = uuid.uuid4()
    deviation_id = uuid.uuid4()
    user_id = uuid.uuid4()
    capa = SimpleNamespace(
        id=capa_id,
        is_deleted=False,
        status="draft",
        returned_step=None,
        deviation_id=None,
        source_code=None,
        capa_items=[],
        dept_head_confirmations=[],
        execution_tracks=[],
    )
    deviation = SimpleNamespace(
        id=deviation_id,
        is_deleted=False,
        deviation_code="DEV-001",
    )

    async def _get(model, item_id):
        if item_id == capa_id:
            return capa
        if item_id == deviation_id:
            return deviation
        return None

    db = SimpleNamespace(get=AsyncMock(side_effect=_get), flush=AsyncMock())

    assert await service.link_deviation(
        db,
        capa_id,
        deviation_id,
        str(user_id),
    ) == {"success": True}
    assert capa.deviation_id == deviation_id
    assert capa.source_code == "DEV-001"

    await service.complete_part(db, capa_id, "a", str(user_id))
    await service.complete_part(db, capa_id, "b", "system")
    assert await service.submit_capa(
        db,
        capa_id,
        str(user_id),
    ) == {"success": True}
    assert capa.status == "submitted"

    approved = SimpleNamespace(
        department="生产部",
        dept_head_user_id="user-head",
        result="approved",
        opinion="通过",
    )
    await service.confirm_dept_head(db, capa_id, approved, str(user_id))
    assert capa.status == "pending_qa_approval"

    rejected = SimpleNamespace(
        department="生产部",
        dept_head_user_id="user-head",
        result="rejected",
        opinion="退回",
    )
    await service.confirm_dept_head(db, capa_id, rejected, str(user_id))
    assert capa.status == "returned"
    assert capa.returned_step == "dept_head_confirm"

    await service.resubmit_capa(db, capa_id, str(user_id))
    assert capa.status == "draft"

    qa_approved = SimpleNamespace(
        step="qa_review",
        result="approved",
        opinion="QA通过",
    )
    await service.approve_capa(db, capa_id, qa_approved, str(user_id))
    assert capa.status == "pending_q_head_approval"

    head_approved = SimpleNamespace(
        step="q_head_approval",
        result="approved",
        opinion="质量负责人通过",
    )
    await service.approve_capa(db, capa_id, head_approved, str(user_id))
    assert capa.status == "executing"

    await service.add_execution_track(
        db,
        capa_id,
        {
            "execution_status": "completed",
            "qa_confirmer": "QA",
            "qa_confirm_date": "2026-07-30",
        },
        str(user_id),
    )
    assert capa.execution_tracks[0]["execution_status"] == "completed"
    assert await service.delete_execution_track(
        db,
        capa_id,
        0,
        str(user_id),
    ) == {"success": True}
    assert capa.execution_tracks == []

    with pytest.raises(ValueError, match="索引无效"):
        await service.delete_execution_track(
            db,
            capa_id,
            0,
            str(user_id),
        )

    assert await service.confirm_execution(
        db,
        capa_id,
        str(user_id),
    ) == {"success": True}
    assert capa.status == "pending_evaluation"

    evaluation = SimpleNamespace(
        evaluation_target="确认措施有效",
        evaluation_result="effective",
        evaluation_confirmer=str(user_id),
        evaluation_confirm_date="2026-07-30T08:00:00Z",
        closure_date="2026-07-31T08:00:00Z",
    )
    assert await service.submit_evaluation(
        db,
        capa_id,
        evaluation,
        str(user_id),
    ) == {"success": True}
    assert capa.status == "closed"
    assert capa.evaluation_confirm_date.tzinfo is not None


@pytest.mark.anyio
async def test_capa_workflow_rejects_missing_and_invalid_states() -> None:
    capa_id = uuid.uuid4()
    capa = SimpleNamespace(
        id=capa_id,
        is_deleted=False,
        status="closed",
        returned_step=None,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=capa), flush=AsyncMock())

    with pytest.raises(ValueError, match="草稿状态"):
        await service.submit_capa(db, capa_id, "system")
    with pytest.raises(ValueError, match="已退回状态"):
        await service.resubmit_capa(db, capa_id, "system")
    with pytest.raises(ValueError, match="执行中状态"):
        await service.confirm_execution(db, capa_id, "system")
    with pytest.raises(ValueError, match="待效果评价状态"):
        await service.submit_evaluation(
            db,
            capa_id,
            SimpleNamespace(
                evaluation_target=None,
                evaluation_result=None,
                evaluation_confirmer=None,
                evaluation_confirm_date=None,
                closure_date=None,
            ),
            "system",
        )

    db.get.return_value = None
    with pytest.raises(ValueError, match="CAPA不存在"):
        await service.submit_capa(db, capa_id, "system")
