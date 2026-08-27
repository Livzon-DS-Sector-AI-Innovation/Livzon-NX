from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.quality.models.capa import CAPA
from app.modules.quality.schemas.capa import (
    CapaApprovalRequest,
    CapaDeptHeadConfirmRequest,
    CapaEvaluationRequest,
    CreateCapaRequest,
    UpdateCapaRequest,
)
from app.modules.quality.service import quality_capa as service


class _Result:
    def __init__(self, value: object | None = None, rows: list[object] | None = None):
        self.value = value
        self.rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self.value

    def scalar_one(self) -> object:
        return self.value

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


class _Db:
    def __init__(self) -> None:
        self.get = AsyncMock()
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()
        self.add = Mock()


def _capa(*, status: str = "draft") -> CAPA:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    item = CAPA(capa_code="CAPA-260820-001", title="纠正预防措施", status=status)
    item.id = uuid4()
    item.created_at = now
    item.updated_at = now
    item.is_deleted = False
    item.execution_tracks = []
    item.dept_head_confirmations = []
    item.capa_items = []
    item.report_versions = []
    return item


@pytest.mark.anyio
async def test_capa_crud_listing_and_workflow_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capa = _capa()
    db = _Db()
    track = SimpleNamespace(id=uuid4(), capa_id=capa.id, plan_content="验证措施")
    monkeypatch.setattr(
        service.repository,
        "get_capas",
        AsyncMock(return_value=([capa], 1)),
    )
    monkeypatch.setattr(
        service.repository,
        "get_capa_plan_tracks_by_capa_ids",
        AsyncMock(return_value=[track]),
    )
    listed = await service.get_capa_list(
        db,
        keyword="纠正",
        closure_date_from="2026-08-01",
        closure_date_to="2026-08-31",
        page=1,
        page_size=10,
    )
    assert listed["total"] == 1
    assert listed["items"][0]["linked_plan_contents"] == ["验证措施"]

    db.execute.return_value = _Result(capa)
    detail = await service.get_capa_detail(db, capa.id)
    assert detail.capa_code == capa.capa_code

    from app.modules.quality.service import quality_feishu_sync as sync

    created = _capa()
    db.execute.return_value = _Result(created)
    monkeypatch.setattr(sync, "auto_sync_capa_after_write", AsyncMock())
    created_result = await service.create_capa(
        db,
        CreateCapaRequest(
            title="新 CAPA",
            source="deviation",
            source_code="PC-2608001",
            expected_completion_date="2026-09-01T00:00:00+00:00",
        ),
        "system",
    )
    assert created_result["id"] == str(created.id)
    assert db.commit.await_count == 1

    db.execute.return_value = _Result(capa)
    updated = await service.update_capa(
        db,
        capa.id,
        UpdateCapaRequest(
            title="更新 CAPA",
            expected_completion_date="2026-09-02T00:00:00+00:00",
            execution_tracks=[],
            status="submitted",
        ),
        "system",
    )
    assert updated == {"success": True}
    assert capa.title == "更新 CAPA"
    assert capa.status == "submitted"

    monkeypatch.setattr(service, "record_audit_log", AsyncMock())
    db.execute.return_value = _Result(capa)
    assert await service.delete_capa(db, capa.id, uuid4()) == {"success": True}
    assert capa.is_deleted is True

    db.execute.return_value = _Result(rows=[("质量部",), ("生产部",)])
    assert await service.get_capa_departments(db) == ["质量部", "生产部"]


@pytest.mark.anyio
async def test_capa_state_machine_and_deviation_autofill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capa = _capa()
    db = _Db()
    db.get.return_value = capa
    deviation = SimpleNamespace(
        id=uuid4(),
        deviation_code="PC-2608001",
        is_deleted=False,
        title="偏差标题",
        description="原始描述",
        ai_analysis={
            "structured_deviation_description": "AI 描述",
            "preliminary_cause_analysis": "AI 原因",
            "capa_suggestions": "AI 建议",
        },
        investigation_records=[
            {
                "nonconformityDescription": "调查描述",
                "rootCauseAnalysis": "调查原因",
                "capaProposals": [{"summary": "措施一"}, {"content": "措施二"}],
            }
        ],
    )
    db.get.side_effect = [deviation]
    filled = await service.auto_fill_from_deviation(db, deviation.id)
    assert filled["non_conformity_description"] == "调查描述"
    assert "1. 措施一" in filled["capa_content"]

    db.get.side_effect = [capa, deviation]
    assert await service.link_deviation(db, capa.id, deviation.id, "system") == {
        "success": True
    }
    assert capa.source_code == deviation.deviation_code

    db.get.side_effect = None
    db.get.return_value = capa
    assert await service.complete_part(db, capa.id, "a", "system") == {"success": True}
    assert await service.complete_part(db, capa.id, "b", "system") == {"success": True}

    capa.status = "draft"
    assert await service.submit_capa(db, capa.id, "system") == {"success": True}
    assert capa.status == "submitted"

    approved = CapaDeptHeadConfirmRequest(
        department="生产部", dept_head_user_id="u1", result="approved", opinion="通过"
    )
    assert await service.confirm_dept_head(db, capa.id, approved, "system") == {
        "success": True
    }
    assert capa.status == "pending_qa_approval"
    rejected = approved.model_copy(update={"result": "rejected"})
    assert await service.confirm_dept_head(db, capa.id, rejected, "system") == {
        "success": True
    }
    assert capa.status == "returned"

    capa.status = "pending_qa_approval"
    assert await service.approve_capa(
        db,
        capa.id,
        CapaApprovalRequest(step="qa_review", result="approved", opinion="QA 通过"),
        "system",
    ) == {"success": True}
    assert capa.status == "pending_q_head_approval"
    assert await service.approve_capa(
        db,
        capa.id,
        CapaApprovalRequest(
            step="q_head_approval", result="rejected", opinion="补充证据"
        ),
        "system",
    ) == {"success": True}
    assert capa.status == "returned"
    assert await service.resubmit_capa(db, capa.id, "system") == {"success": True}

    assert await service.add_execution_track(
        db,
        capa.id,
        {
            "execution_status": "进行中",
            "qa_confirmer": "QA",
            "qa_confirm_date": "2026-08-20",
        },
        "system",
    ) == {"success": True}
    assert await service.delete_execution_track(db, capa.id, 0, "system") == {
        "success": True
    }
    with pytest.raises(AppException, match="索引无效"):
        await service.delete_execution_track(db, capa.id, 0, "system")

    capa.status = "executing"
    assert await service.confirm_execution(db, capa.id, "system") == {"success": True}
    assert capa.status == "pending_evaluation"
    evaluation = CapaEvaluationRequest(
        evaluation_target="验证",
        evaluation_result="有效",
        evaluation_confirmer=str(uuid4()),
        evaluation_confirm_date="2026-08-20T08:00:00Z",
        closure_date="2026-08-21T08:00:00Z",
    )
    assert await service.submit_evaluation(db, capa.id, evaluation, "system") == {
        "success": True
    }
    assert capa.status == "closed"
