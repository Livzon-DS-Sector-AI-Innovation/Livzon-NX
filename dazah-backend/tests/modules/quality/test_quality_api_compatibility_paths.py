from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.api import quality_capa as capa_api
from app.modules.quality.api import quality_deviation as deviation_api


def _page() -> dict[str, object]:
    return {"items": [], "page": 1, "page_size": 20, "total": 0}


def _data_object(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_quality_deviation_api_compatibility_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    deviation_id = uuid.uuid4()
    monkeypatch.setattr(deviation_api, "_require_user", Mock(return_value="user-1"))
    monkeypatch.setattr(
        "app.platform.identity.data_scope.resolve_user_department_scope",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        deviation_api,
        "_resolve_quality_list_scope",
        AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        deviation_api.service, "get_deviation_list", AsyncMock(return_value=_page())
    )
    listed = await deviation_api.list_deviations(db=db, current_user=user)
    assert listed.status_code == 200

    row = SimpleNamespace(
        deviation_code="DEV-1",
        description="description",
        title="title",
        has_occurred_before=False,
        previous_occurrence_code=None,
        root_cause_analysis=None,
        level="一般",
        investigation_completed_at=None,
        corrective_actions=None,
        material_disposition=None,
        status=None,
        affected_items=None,
        batch_number=None,
    )
    monkeypatch.setattr(
        deviation_api.repo,
        "get_deviations",
        AsyncMock(return_value=([row], 1)),
    )
    monkeypatch.setattr(
        deviation_api,
        "generate_deviation_ledger_export_docx",
        Mock(return_value=b"docx"),
    )
    exported = await deviation_api.export_deviations(db=db, current_user=user)
    assert exported.media_type.endswith("wordprocessingml.document")

    page_services = {
        "list_report_records": _page(),
        "get_deviation_report_record_from_feishu": {"record_id": "r1"},
        "create_deviation_report_record": {"record_id": "r1"},
        "update_deviation_report_record": {"record_id": "r1"},
        "get_deviation_investigation_push_record_list": _page(),
        "update_deviation_investigation_push_record": {"record_id": "r1"},
    }
    for name, result in page_services.items():
        target = (
            deviation_api.service.quality_feishu_pages
            if name
            in {
                "list_report_records",
                "create_deviation_report_record",
                "update_deviation_report_record",
            }
            else deviation_api.service
        )
        if name == "get_deviation_report_record_from_feishu":
            target = deviation_api.service.tracking_records
        monkeypatch.setattr(target, name, AsyncMock(return_value=result))
    monkeypatch.setattr(
        deviation_api.service.quality_feishu_pages,
        "delete_deviation_report_record",
        AsyncMock(),
    )

    assert (
        await deviation_api.list_deviation_report_records_static(
            page=2, page_size=5, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.get_deviation_report_record("r1", db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.create_deviation_report_record(
            {"content": "report"}, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.update_deviation_report_record_api(
            "r1", {"content": "updated"}, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.delete_deviation_report_record_api(
            "r1", db=db, current_user=user
        )
    ).status_code == 200

    monkeypatch.setattr(
        deviation_api.service,
        "batch_update_status",
        AsyncMock(return_value={"updated": 1}),
    )
    monkeypatch.setattr(
        deviation_api.service,
        "get_department_confirmations",
        AsyncMock(return_value=_page()),
    )
    monkeypatch.setattr(
        deviation_api.service,
        "confirm_production_status",
        AsyncMock(return_value={"confirmed": True}),
    )
    monkeypatch.setattr(
        deviation_api.service,
        "get_stopped_departments",
        AsyncMock(return_value=["质量部"]),
    )
    monkeypatch.setattr(
        deviation_api.service,
        "get_deviation_detail",
        AsyncMock(
            return_value=_data_object(
                model_dump=Mock(return_value={"id": str(deviation_id)})
            )
        ),
    )
    monkeypatch.setattr(
        deviation_api.service,
        "get_related_capas_for_deviation",
        AsyncMock(return_value=[]),
    )
    for name in (
        "create_deviation",
        "update_deviation",
        "delete_deviation",
        "submit_for_review",
        "complete_ai_analysis",
        "submit_investigation",
        "submit_review",
        "submit_final_code",
        "resubmit_deviation",
    ):
        monkeypatch.setattr(
            deviation_api.service, name, AsyncMock(return_value={"ok": True})
        )

    batch_request = _data_object(deviation_ids=[deviation_id], target_status="closed")
    assert (
        await deviation_api.batch_update_deviation_status(
            batch_request, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.list_department_confirmations(db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.confirm_department_status(
            _data_object(week_key="2026-W35", department="质量部", status="停产"),
            db=db,
            current_user=user,
        )
    ).status_code == 200
    assert (
        await deviation_api.get_stopped_departments(
            "2026-W35", db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.get_deviation(deviation_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.get_related_capas(deviation_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.create_deviation(_data_object(), db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.update_deviation(
            deviation_id, _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.delete_deviation(deviation_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.batch_delete_deviations(
            {"ids": [str(deviation_id)]}, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.submit_deviation_for_review(
            deviation_id, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.complete_ai_analysis(
            deviation_id,
            _data_object(ai_analysis={"summary": "ok"}),
            db=db,
            current_user=user,
        )
    ).status_code == 200
    assert (
        await deviation_api.submit_investigation(
            deviation_id, _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.submit_review(
            deviation_id, _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.submit_final_code(
            deviation_id, "DEV-FINAL-1", db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.resubmit_deviation(deviation_id, db=db, current_user=user)
    ).status_code == 200

    push_data = _data_object(
        model_dump=Mock(return_value={"deviation_id": str(deviation_id)})
    )
    monkeypatch.setattr(
        deviation_api.service.quality_feishu_pages,
        "create_investigation_push_record",
        AsyncMock(return_value={"record_id": "r1"}),
    )
    monkeypatch.setattr(
        deviation_api.service.quality_feishu_pages,
        "delete_investigation_push_record",
        AsyncMock(),
    )
    assert (
        await deviation_api.list_deviation_investigation_push_records(
            deviation_id=deviation_id,
            deviation_code="DEV-1",
            page=2,
            page_size=5,
            db=db,
            current_user=user,
        )
    ).status_code == 200
    assert (
        await deviation_api.create_deviation_investigation_push_record(
            push_data, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.update_deviation_investigation_push_record(
            "r1", _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await deviation_api.delete_deviation_investigation_push_record(
            "r1", db=db, current_user=user
        )
    ).status_code == 200

    upload = SimpleNamespace(filename="import.docx")
    monkeypatch.setattr(
        deviation_api, "read_upload_with_limit", AsyncMock(return_value=b"file")
    )
    monkeypatch.setattr(
        deviation_api.ie_service,
        "preview_deviation_import",
        AsyncMock(return_value={"total_rows": 0}),
    )
    monkeypatch.setattr(
        deviation_api.ie_service,
        "confirm_deviation_import",
        AsyncMock(return_value={"created": 0}),
    )
    assert (
        await deviation_api.preview_deviation_import(upload, db=db, current_user=user)
    ).status_code == 200
    assert (
        await deviation_api.confirm_deviation_import(
            upload, True, True, db=db, current_user=user
        )
    ).status_code == 200


@pytest.mark.anyio
async def test_quality_capa_api_compatibility_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    capa_id = uuid.uuid4()
    deviation_id = uuid.uuid4()
    track_id = uuid.uuid4()
    monkeypatch.setattr(capa_api, "_require_user", Mock(return_value="user-1"))
    monkeypatch.setattr(
        "app.platform.identity.data_scope.resolve_user_department_scope",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        capa_api.service, "get_capa_plan_track_list", AsyncMock(return_value=_page())
    )
    monkeypatch.setattr(
        capa_api.service, "get_capa_list", AsyncMock(return_value=_page())
    )
    monkeypatch.setattr(
        capa_api.service, "get_capa_departments", AsyncMock(return_value=["质量部"])
    )
    monkeypatch.setattr(
        capa_api.service,
        "auto_fill_from_deviation",
        AsyncMock(return_value={"title": "CAPA"}),
    )
    monkeypatch.setattr(
        capa_api.service,
        "get_capa_detail",
        AsyncMock(
            return_value=_data_object(
                model_dump=Mock(return_value={"id": str(capa_id)})
            )
        ),
    )
    for name in (
        "create_capa_plan_track",
        "update_capa_plan_track",
        "delete_capa_plan_track",
        "create_capa",
        "update_capa",
        "delete_capa",
        "link_deviation",
        "complete_part",
        "submit_capa",
        "confirm_dept_head",
        "approve_capa",
        "resubmit_capa",
        "add_execution_track",
        "delete_execution_track",
        "confirm_execution",
        "submit_evaluation",
    ):
        monkeypatch.setattr(
            capa_api.service, name, AsyncMock(return_value={"ok": True})
        )
    monkeypatch.setattr(
        capa_api.service.quality_feishu_pages,
        "sync_capas_from_feishu",
        AsyncMock(return_value={"synced": 1}),
    )
    monkeypatch.setattr(
        capa_api.service.quality_feishu_pages,
        "sync_capa_plan_tracks_from_feishu",
        AsyncMock(return_value={"synced": 1}),
    )
    monkeypatch.setattr(
        capa_api, "read_upload_with_limit", AsyncMock(return_value=b"file")
    )
    monkeypatch.setattr(
        capa_api.ie_service,
        "preview_capa_import",
        AsyncMock(return_value={"total_rows": 0}),
    )
    monkeypatch.setattr(
        capa_api.ie_service,
        "confirm_capa_import",
        AsyncMock(return_value={"created": 0}),
    )
    monkeypatch.setattr(
        capa_api.ie_service, "export_capas_template", Mock(return_value=b"template")
    )
    monkeypatch.setattr(
        capa_api.ie_service, "export_capas", AsyncMock(return_value=b"export")
    )

    assert (
        await capa_api.list_capa_plan_tracks(db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.create_capa_plan_track(_data_object(), db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.update_capa_plan_track(
            track_id, _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.delete_capa_plan_track(track_id, db=db, current_user=user)
    ).status_code == 200
    assert (await capa_api.list_capas(db=db, current_user=user)).status_code == 200
    assert (
        await capa_api.get_capa_departments(db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.auto_fill_capa_from_deviation(
            deviation_id, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.get_capa(capa_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.create_capa(_data_object(), db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.update_capa(capa_id, _data_object(), db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.delete_capa(capa_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.batch_delete_capas(
            {"ids": [str(capa_id)]}, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.link_capa_to_deviation(
            capa_id,
            _data_object(deviation_id=deviation_id),
            db=db,
            current_user=user,
        )
    ).status_code == 200
    assert (
        await capa_api.complete_capa_part(
            capa_id, _data_object(part="investigation"), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.submit_capa_for_review(capa_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.confirm_capa_by_dept_head(
            capa_id, _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.approve_capa(capa_id, _data_object(), db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.resubmit_capa(capa_id, db=db, current_user=user)
    ).status_code == 200
    execution = _data_object(model_dump=Mock(return_value={"date": "2026-08-27"}))
    assert (
        await capa_api.add_capa_execution_track(
            capa_id, execution, db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.delete_capa_execution_track(capa_id, 0, db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.confirm_capa_execution(capa_id, db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.submit_capa_evaluation(
            capa_id, _data_object(), db=db, current_user=user
        )
    ).status_code == 200
    assert (
        await capa_api.sync_capas_from_feishu(db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.sync_capa_plan_tracks_from_feishu(db=db, current_user=user)
    ).status_code == 200

    upload = SimpleNamespace(filename="import.docx")
    assert (
        await capa_api.preview_capa_import(upload, db=db, current_user=user)
    ).status_code == 200
    assert (
        await capa_api.confirm_capa_import(upload, True, True, db=db, current_user=user)
    ).status_code == 200
    assert (
        (await capa_api.export_capa_template(current_user=user)).media_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert (await capa_api.export_capas(db=db, current_user=user)).media_type.endswith(
        "wordprocessingml.document"
    )
