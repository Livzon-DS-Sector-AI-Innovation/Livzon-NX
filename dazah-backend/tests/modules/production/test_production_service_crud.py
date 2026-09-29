"""生产模块 Service 层单元测试（真实测试库 + 业务成功/失败路径）。"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production import fermentation_board_service as board
from app.modules.production.fermentation_batch_actual_models import (
    FermentationBatchActual,
)
from app.modules.production.schemas import (
    BatchCreate,
    BatchStatusUpdate,
    ProcessSpecCreate,
    ProcessStepCreate,
    ProductionPlanCreate,
)
from app.modules.production.service import ProductionService


@pytest.mark.anyio
async def test_create_and_get_batch(db_session: AsyncSession) -> None:
    service = ProductionService(db_session)
    created = await service.create_batch(
        BatchCreate(
            batch_no=f"B-{uuid.uuid4().hex[:8]}",
            product_code="FA",
            product_name="L-苯丙氨酸",
        )
    )
    assert created.id is not None
    fetched = await service.get_batch(created.id)
    assert fetched is not None
    assert fetched.batch_no == created.batch_no

    # 更新状态
    await service.update_batch_status(created.id, BatchStatusUpdate(status="released"))
    updated = await service.get_batch(created.id)
    assert updated is not None
    assert updated.status == "released"

    # 删除（软删除）
    assert await service.delete_batch(created.id) is True
    assert await service.get_batch(created.id) is None


@pytest.mark.anyio
async def test_create_and_get_plan(db_session: AsyncSession) -> None:
    service = ProductionService(db_session)
    created = await service.create_plan(
        ProductionPlanCreate(
            plan_no=f"P-{uuid.uuid4().hex[:8]}",
            product_code="FA",
            product_name="L-苯丙氨酸",
            planned_qty=100,
            plan_date=date(2026, 8, 1),
        )
    )
    assert created.id is not None
    fetched = await service.get_plan(created.id)
    assert fetched is not None
    assert fetched.product_name == "L-苯丙氨酸"
    assert await service.delete_plan(created.id) is True


@pytest.mark.anyio
async def test_create_and_get_process_spec(db_session: AsyncSession) -> None:
    service = ProductionService(db_session)
    created = await service.create_process_spec(
        ProcessSpecCreate(
            spec_code=f"S-{uuid.uuid4().hex[:8]}",
            product_code="FA",
            spec_name="无菌工艺",
        )
    )
    assert created.id is not None
    fetched = await service.get_process_spec(created.id)
    assert fetched is not None
    assert fetched.spec_code == created.spec_code


@pytest.mark.anyio
async def test_create_process_step(db_session: AsyncSession) -> None:
    service = ProductionService(db_session)
    spec = await service.create_process_spec(
        ProcessSpecCreate(
            spec_code=f"S-{uuid.uuid4().hex[:8]}",
            product_code="FA",
        )
    )
    step = await service.create_process_step(
        ProcessStepCreate(spec_id=spec.id, step_no=1, step_name="投料"),
    )
    assert step.id is not None
    fetched_spec = await service.get_process_spec(spec.id)
    assert fetched_spec is not None


@pytest.mark.anyio
async def test_get_missing_records_return_none(db_session: AsyncSession) -> None:
    service = ProductionService(db_session)
    missing = uuid.uuid4()
    assert await service.get_batch(missing) is None
    assert await service.get_plan(missing) is None
    assert await service.get_process_spec(missing) is None


def test_serialize_batch_actual_includes_actual_times() -> None:
    """实际移种/放罐时刻随批次产量序列化（分钟精度 ISO 串）。"""
    item = SimpleNamespace(
        id=uuid.uuid4(),
        batch_no="FA26232",
        dump_date=date(2026, 9, 9),
        inoculated_at=datetime(2026, 9, 8, 21, 30),
        dumped_at=datetime(2026, 9, 9, 10, 5),
        yield_kg=100.0,
        extract_kg=None,
        remark=None,
    )
    data = board.serialize_batch_actual(item)
    assert data["inoculated_at"] == "2026-09-08T21:30:00"
    assert data["dumped_at"] == "2026-09-09T10:05:00"
    assert data["dump_date"] == "2026-09-09"


@pytest.mark.anyio
async def test_upsert_batch_actual_partial_actual_times() -> None:
    """「确认移种」部分更新：只覆盖显式给出的实际移种时刻，不清产量。"""

    class _Result:
        def scalar_one_or_none(self) -> Any:
            return existing

    class _Session:
        async def execute(self, *_args: Any, **_kwargs: Any) -> _Result:
            return _Result()

        async def commit(self) -> None:
            return None

        async def refresh(self, _item: Any) -> None:
            return None

    existing = FermentationBatchActual(
        batch_no="FA26232",
        product_code="FA",
        dump_date=date(2026, 9, 9),
        yield_kg=100.0,
    )
    operator = uuid.uuid4()
    await board.upsert_batch_actual(
        _Session(),  # type: ignore[arg-type]
        batch_no="FA26232",
        inoculated_at=datetime(2026, 9, 8, 21, 30),
        product_code="FA",
        created_by=operator,
        provided_fields={"inoculated_at"},
    )
    assert existing.inoculated_at == datetime(2026, 9, 8, 21, 30)
    # 显式字段之外的产量与放罐日期保持原值
    assert existing.yield_kg == 100.0
    assert existing.dump_date == date(2026, 9, 9)
    assert existing.updated_by == operator


@pytest.mark.anyio
async def test_list_batch_actuals_keeps_dump_date_null_in_period(
    db_session: AsyncSession,
) -> None:
    """仅「确认移种」（dump_date 为空）的记录不受周期过滤，
    否则看板永远取不到实际移种时刻；放罐日期在周期外的仍被过滤。"""
    suffix = uuid.uuid4().hex[:8]
    in_tank = await board.upsert_batch_actual(
        db_session,
        batch_no=f"FA-NULL-{suffix}",
        inoculated_at=datetime(2026, 9, 8, 21, 30),
        product_code="FA",
        provided_fields={"inoculated_at"},
    )
    out_of_period = await board.upsert_batch_actual(
        db_session,
        batch_no=f"FA-OUT-{suffix}",
        dump_date=date(2026, 8, 1),
        product_code="FA",
        provided_fields={"dump_date"},
    )
    items = await board.list_batch_actuals(
        db_session,
        period_start=date(2026, 8, 27),
        period_end=date(2026, 9, 26),
        product_code="FA",
    )
    batch_nos = {item.batch_no for item in items}
    assert in_tank.batch_no in batch_nos
    assert out_of_period.batch_no not in batch_nos
