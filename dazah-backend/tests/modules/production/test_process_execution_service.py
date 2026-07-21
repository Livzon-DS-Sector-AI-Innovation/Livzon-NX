from datetime import UTC, datetime

import pytest

from app.core.exceptions import AppException
from app.modules.production.models import ProcessExecutionRecord
from app.modules.production.process_catalog import PROCESS_STEPS
from app.modules.production.process_schemas import (
    ProcessExecutionRecordCreate,
    ProcessExecutionRecordUpdate,
)
from app.modules.production.process_service import ProcessExecutionService


def _record(process_code: str, status: str = "completed") -> ProcessExecutionRecord:
    definition = next(step for step in PROCESS_STEPS if step["code"] == process_code)
    return ProcessExecutionRecord(
        batch_no="B203-001",
        workshop_code="203",
        process_code=process_code,
        step_sequence=definition["sequence"],
        status=status,
        recorded_at=datetime.now(UTC),
        data={},
    )


def test_builds_thirteen_step_batch_progress() -> None:
    item = ProcessExecutionService._build_batch_progress(
        "B203-001",
        "203",
        [_record("receive"), _record("pretreat"), _record("ceramic", "in_progress")],
    )

    assert item.total == 13
    assert item.completed == 2
    assert item.progress_percent == 15.4
    ceramic = next(step for step in item.steps if step.code == "ceramic")
    assert ceramic.has_record is True
    assert ceramic.completed is False


def test_extracts_packaging_output_number() -> None:
    assert ProcessExecutionService._number_from_data("1,234.50 kg") == 1234.5
    assert ProcessExecutionService._number_from_data(None) == 0


@pytest.mark.anyio
async def test_process_steps_require_completed_predecessor(db_session) -> None:
    service = ProcessExecutionService(db_session)
    with pytest.raises(AppException, match="前序工序"):
        await service.create_record(
            ProcessExecutionRecordCreate(
                batch_no="ORDER-001",
                workshop_code="203",
                process_code="pretreat",
                status="draft",
                recorded_at=datetime.now(UTC),
                data={"broth_volume": 100},
            )
        )

    receive = await service.create_record(
        ProcessExecutionRecordCreate(
            batch_no="ORDER-001",
            workshop_code="203",
            process_code="receive",
            status="draft",
            recorded_at=datetime.now(UTC),
            data={"received_volume": 100},
        )
    )
    await service.complete_record(receive.id)
    pretreat = await service.create_record(
        ProcessExecutionRecordCreate(
            batch_no="ORDER-001",
            workshop_code="203",
            process_code="pretreat",
            status="in_progress",
            recorded_at=datetime.now(UTC),
            data={"broth_volume": 100},
        )
    )

    assert pretreat.step_sequence == 2


@pytest.mark.anyio
async def test_completed_process_record_is_locked(db_session) -> None:
    service = ProcessExecutionService(db_session)
    record = await service.create_record(
        ProcessExecutionRecordCreate(
            batch_no="LOCK-001",
            workshop_code="203",
            process_code="receive",
            status="completed",
            recorded_at=datetime.now(UTC),
            data={"received_volume": 80},
        )
    )

    with pytest.raises(AppException, match="锁定"):
        await service.update_record(
            record.id, data=ProcessExecutionRecordUpdate(remarks="试图修改")
        )
    with pytest.raises(AppException, match="不能删除"):
        await service.delete_record(record.id)
