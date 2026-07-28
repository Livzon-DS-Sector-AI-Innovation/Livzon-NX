from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.production import pressure_service as module
from app.modules.production.pressure_schemas import BatchManualEntryRow


def _service() -> tuple[module.PressureService, SimpleNamespace]:
    service = module.PressureService(object())
    repo = SimpleNamespace(
        get_point_mapping_by_point_id=AsyncMock(return_value=None),
        create_record=AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4())
        ),
        get_points_by_area=AsyncMock(return_value=[]),
        create_records_batch=AsyncMock(),
        update_ocr_task=AsyncMock(),
        get_record_by_id=AsyncMock(return_value=None),
        delete_record=AsyncMock(),
        batch_delete_records=AsyncMock(return_value=1),
        audit_record=AsyncMock(),
        batch_audit_records=AsyncMock(return_value=1),
        list_merged_records=AsyncMock(return_value=([], 0)),
        delete_merged_row=AsyncMock(return_value=1),
        batch_delete_merged_rows=AsyncMock(return_value=2),
        update_merged_row=AsyncMock(return_value=3),
        get_export_by_area=AsyncMock(return_value=[]),
        list_ocr_tasks=AsyncMock(return_value=([], 0)),
        get_ocr_task_by_id=AsyncMock(return_value=None),
        list_data_master=AsyncMock(return_value=([], 0)),
        get_data_master_by_id=AsyncMock(return_value=None),
        delete_data_master=AsyncMock(),
        batch_delete_data_master=AsyncMock(return_value=1),
        list_notifications=AsyncMock(return_value=([], 0)),
        get_unread_count=AsyncMock(return_value=2),
        mark_read=AsyncMock(),
        mark_all_read=AsyncMock(),
    )
    service.repo = repo
    return service, repo


@pytest.mark.anyio
async def test_manual_batch_and_ocr_record_creation_paths() -> None:
    service, repo = _service()
    manual = module.CreateManualRecordRequest.model_construct(
        point_id="P-001",
        pressure_value=15,
        record_time=None,
        time_slot="morning",
        remark="人工录入",
    )
    result = await service.create_manual_record(manual, creator="operator")
    assert result["success"] is True
    payload = repo.create_record.await_args.args[0]
    assert payload["area"] == "其他"
    assert payload["standard_pressure"] == 0
    assert payload["input_type"] == "manual"

    repo.get_points_by_area.return_value = [
        SimpleNamespace(
            point_id="P-001",
            area="洁净区",
            standard_pressure=12,
        )
    ]
    batch = module.BatchManualEntryRequest.model_construct(
        area="洁净区",
        time_slots=["morning", "evening", "night"],
        rows=[
            BatchManualEntryRow.model_construct(
                date="2026-07-01",
                values={
                    "P-001::morning": 15,
                    "P-001::evening": None,
                    "P-UNKNOWN::night": 8,
                },
            )
        ],
        remark="批量录入",
    )
    batch_result = await service.create_batch_manual(batch, creator="operator")
    assert batch_result.success_count == 2
    records = repo.create_records_batch.await_args.args[0]
    assert records[0].point_id == "P-001"
    assert records[0].time_slot == "morning"
    assert records[0].standard_pressure == 12
    assert records[1].area == "洁净区"

    mapping = SimpleNamespace(area="生产区", standard_pressure=10)
    repo.get_point_mapping_by_point_id.return_value = mapping
    task_id = uuid.uuid4()
    ocr = module.CreateOcrRecordRequest.model_construct(
        records=[
            {
                "point_id": "P-002",
                "pressure_value": "18",
                "record_time": "2026-07-02T08:00:00Z",
            },
            {
                "point_id": "P-003",
                "pressure_value": 9,
                "record_time": "invalid",
                "area": "自定义区域",
                "standard_pressure": 7,
            },
        ],
        image_url="https://example.com/pressure.png",
        task_id=str(task_id),
    )
    ocr_result = await service.create_ocr_records(ocr, creator="ocr-user")
    assert ocr_result.success_count == 2
    repo.update_ocr_task.assert_awaited_with(
        task_id,
        {
            "status": "submitted",
            "batch_id": ocr_result.batch_id,
        },
    )

    repo.update_ocr_task.side_effect = RuntimeError("task update failed")
    retry_result = await service.create_ocr_records(ocr, creator="ocr-user")
    assert retry_result.success is True


@pytest.mark.anyio
async def test_record_delete_audit_and_batch_result_boundaries() -> None:
    service, repo = _service()
    record_id = uuid.uuid4()

    with pytest.raises(Exception):
        await service.delete_record(record_id)
    with pytest.raises(Exception):
        await service.audit_record(
            record_id,
            module.AuditRequest.model_construct(
                status="approved",
                reject_reason=None,
            ),
        )

    repo.get_record_by_id.return_value = SimpleNamespace(id=record_id)
    await service.delete_record(record_id)
    repo.delete_record.assert_awaited_once_with(record_id)
    assert await service.audit_record(
        record_id,
        module.AuditRequest.model_construct(
            status="rejected",
            reject_reason="读数异常",
        ),
    ) == {"success": True}
    repo.audit_record.assert_awaited_once_with(
        record_id,
        "rejected",
        "读数异常",
    )

    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    deleted = await service.batch_delete_records(ids)
    assert deleted.success_count == 1
    assert deleted.fail_count == 2

    audited = await service.batch_audit(
        module.BatchAuditRequest.model_construct(
            ids=ids,
            status="approved",
            reject_reason=None,
        )
    )
    assert audited.success_count == 1
    assert audited.fail_count == 2


@pytest.mark.anyio
async def test_merged_export_and_empty_list_paths() -> None:
    service, repo = _service()
    merged = await service.list_merged(
        area="洁净区",
        point_id="P-001",
        input_type="manual",
        page=2,
        page_size=10,
    )
    assert merged.items == []
    assert merged.total == 0
    assert repo.list_merged_records.await_args.kwargs["page"] == 2

    deleted = await service.delete_merged_row(
        module.DeleteMergedRowRequest.model_construct(
            point_id="P-001",
            date="2026-07-01",
        )
    )
    assert deleted == {"success_count": 1, "success": True}

    rows = [
        module.DeleteMergedRowRequest.model_construct(
            point_id="P-001",
            date="2026-07-01",
        ),
        module.DeleteMergedRowRequest.model_construct(
            point_id="P-002",
            date="2026-07-01",
        ),
    ]
    batch_deleted = await service.batch_delete_merged_rows(
        module.BatchDeleteMergedRowsRequest.model_construct(rows=rows)
    )
    assert batch_deleted["success_count"] == 2

    updated = await service.update_merged_row(
        module.UpdateMergedRowRequest.model_construct(
            point_id="P-001",
            date="2026-07-01",
            time_slot_values={"morning": 12},
        )
    )
    assert updated.success_count == 3

    assert await service.get_export_by_area(area="洁净区") == []
    tasks, task_total = await service.list_ocr_tasks(status="completed")
    assert tasks == []
    assert task_total == 0
    items, item_total = await service.list_data_master(
        material_name="物料A"
    )
    assert items == []
    assert item_total == 0


@pytest.mark.anyio
async def test_missing_ocr_data_master_and_notification_paths() -> None:
    service, repo = _service()
    item_id = uuid.uuid4()
    task_id = uuid.uuid4()

    with pytest.raises(Exception):
        await service.get_ocr_task(task_id)
    with pytest.raises(Exception):
        await service.submit_ocr_task_result(
            task_id,
            module.SubmitOcrTaskResultRequest.model_construct(records=[]),
        )
    with pytest.raises(Exception):
        await service.get_data_master(item_id)
    with pytest.raises(Exception):
        await service.update_data_master(item_id, {"supplier": "供应商"})
    with pytest.raises(Exception):
        await service.delete_data_master(item_id)

    deleted = await service.batch_delete_data_master(
        [item_id, uuid.uuid4()]
    )
    assert deleted.success_count == 1
    assert deleted.fail_count == 1

    notifications = await service.list_notifications(
        user_id="operator",
        page=1,
        page_size=20,
    )
    assert notifications.items == []
    assert notifications.unread_count == 2

    notification_id = uuid.uuid4()
    await service.mark_notification_read(notification_id)
    await service.mark_all_notifications_read("operator")
    repo.mark_read.assert_awaited_once_with(notification_id)
    repo.mark_all_read.assert_awaited_once_with("operator")
