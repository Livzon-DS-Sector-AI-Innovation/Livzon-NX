from datetime import date
from typing import Any

import pytest

from app.modules.production.schemas import (
    ProductionExecutionPlanCreate,
    ProductionExecutionPlanUpdate,
)
from app.modules.production.service import ProductionService


def test_execution_plan_completion_rate_is_derived() -> None:
    payload = ProductionService._execution_plan_payload(
        {"planned_yield": 250, "actual_completion": 187.5}
    )

    assert payload["completion_rate"] == 75.0


@pytest.mark.anyio
async def test_execution_plan_crud_uses_soft_delete(db_session: Any) -> None:
    service = ProductionService(db_session)
    plan = await service.create_execution_plan(
        ProductionExecutionPlanCreate(
            workshop="203",
            product_name="L-苯丙氨酸",
            plan_date=date(2026, 7, 15),
            unit="kg",
            planned_yield=100,
            actual_completion=40,
        )
    )

    assert plan.completion_rate == 40.0

    updated = await service.update_execution_plan(
        plan.id,
        ProductionExecutionPlanUpdate(actual_completion=100),
    )
    assert updated is not None
    assert updated.completion_rate == 100.0

    assert await service.delete_execution_plan(plan.id) is True
    assert await service.repo.get_execution_plan_by_id(plan.id) is None
