from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.core.exceptions import AppException
from app.modules.production.operations_schemas import (
    FermentationCreate,
    FermentationUpdate,
)
from app.modules.production.operations_service import OperationsService


def test_fermentation_discharge_cannot_precede_entry() -> None:
    with pytest.raises(AppException):
        OperationsService._validate_fermentation(date(2026, 7, 15), date(2026, 7, 14))


def test_event_impact_duration_is_calculated() -> None:
    start = datetime(2026, 7, 15, 8, tzinfo=UTC)
    data = {"event_time": start, "restore_time": start + timedelta(minutes=135)}

    OperationsService._set_impact_duration(data)

    assert data["impact_duration"] == "2小时15分钟"


def test_event_restore_cannot_precede_start() -> None:
    start = datetime(2026, 7, 15, 8, tzinfo=UTC)
    with pytest.raises(AppException):
        OperationsService._set_impact_duration(
            {"event_time": start, "restore_time": start - timedelta(minutes=1)}
        )


@pytest.mark.anyio
async def test_fermentation_crud_uses_soft_delete(db_session: Any) -> None:
    service = OperationsService(db_session)
    record = await service.create_fermentation(
        FermentationCreate(
            batch_no="FERMENT-TEST-001",
            product_name="测试产品",
            fermenter="F-01",
            entry_date=date(2026, 7, 15),
            cycle_data={"cycle_1": 12.5},
        ),
        None,
    )
    record_id = record.id

    updated = await service.update_fermentation(
        record_id,
        FermentationUpdate(status="completed", tank_yield=88.5),
        None,
    )
    assert updated is not None
    assert updated.status == "completed"
    assert updated.tank_yield == 88.5

    assert await service.delete(type(record), record_id) is True
    assert await service.repo.get(type(record), record_id) is None
