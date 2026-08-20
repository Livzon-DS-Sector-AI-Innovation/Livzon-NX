"""生产模块 Service 层单元测试（真实测试库 + 业务成功/失败路径）。"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.service import ProductionService
from app.modules.production.schemas import (
    BatchCreate,
    BatchStatusUpdate,
    ProcessSpecCreate,
    ProcessStepCreate,
    ProductionPlanCreate,
)


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
