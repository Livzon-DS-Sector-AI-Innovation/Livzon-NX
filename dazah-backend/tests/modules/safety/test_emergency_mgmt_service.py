"""应急管理服务层测试（真实服务 + 独立测试库）。

覆盖：预案/演练/物资的创建与枚举校验、软删除、演练按年度筛选
与汇总统计。
"""

from collections.abc import AsyncIterator
from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.models import EmergencyDrill, EmergencyPlan, EmergencySupply
from app.modules.safety.schemas.emergency_mgmt import (
    EmergencyDrillCreate,
    EmergencyDrillUpdate,
    EmergencyPlanCreate,
    EmergencyPlanUpdate,
    EmergencySupplyCreate,
    EmergencySupplyUpdate,
)
from app.modules.safety.service.emergency_mgmt import EmergencyMgmtService

_YEAR = date.today().year


@pytest.fixture(autouse=True)
async def _cleanup_emergency(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.execute(
        delete(EmergencySupply).where(EmergencySupply.name.like("测试物资-%"))
    )
    await db_session.execute(
        delete(EmergencyDrill).where(EmergencyDrill.name.like("测试演练-%"))
    )
    await db_session.execute(
        delete(EmergencyPlan).where(EmergencyPlan.name.like("测试预案-%"))
    )
    await db_session.commit()


async def test_plan_crud_and_invalid_type(db_session: AsyncSession) -> None:
    service = EmergencyMgmtService(db_session)
    plan = await service.create_plan(
        EmergencyPlanCreate(
            name=f"测试预案-液氨泄漏-{_YEAR}",
            plan_type="special",
            version="V2.0",
            department="安环部",
            review_due_date=date(_YEAR, 12, 31),
        )
    )
    assert plan.status == "active"
    assert "液氨泄漏" in plan.search_text

    with pytest.raises(AppException) as exc:
        await service.create_plan(
            EmergencyPlanCreate(name="测试预案-非法", plan_type="unknown")
        )
    assert exc.value.status_code == 422

    updated = await service.update_plan(plan.id, EmergencyPlanUpdate(status="obsolete"))
    assert updated.status == "obsolete"
    await db_session.commit()

    items, total = await service.list_plans(status="obsolete", keyword="测试预案")
    assert total == 1
    assert items[0].name.startswith("测试预案-")

    assert await service.delete_plan(plan.id) is True
    await db_session.commit()
    assert await service.get_plan(plan.id) is None


async def test_drill_year_filter_and_stats(db_session: AsyncSession) -> None:
    service = EmergencyMgmtService(db_session)
    done = await service.create_drill(
        EmergencyDrillCreate(
            name=f"测试演练-液氨泄漏实战-{_YEAR}",
            drill_type="practical",
            scenario="液氨泄漏",
            planned_date=date(_YEAR, 3, 15),
            actual_date=date(_YEAR, 3, 15),
            location="203车间",
            status="done",
            summary="按预案完成",
        )
    )
    await service.create_drill(
        EmergencyDrillCreate(
            name=f"测试演练-计划中-{_YEAR}",
            drill_type="tabletop",
            planned_date=date(_YEAR, 11, 1),
            status="planned",
        )
    )
    await db_session.commit()

    items, total = await service.list_drills(year=_YEAR, keyword="测试演练")
    assert total == 2

    items, total = await service.list_drills(status="done", keyword="测试演练")
    assert total == 1
    assert items[0].id == done.id

    stats = await service.get_stats()
    assert stats.drills_done >= 1
    assert stats.drills_planned >= 1

    with pytest.raises(AppException):
        await service.update_drill(done.id, EmergencyDrillUpdate(status="bad-status"))


async def test_supply_crud_and_abnormal_count(db_session: AsyncSession) -> None:
    service = EmergencyMgmtService(db_session)
    supply = await service.create_supply(
        EmergencySupplyCreate(
            name="测试物资-正压呼吸器",
            category="protective",
            quantity=4,
            unit="套",
            department="安环部",
        )
    )
    assert supply.status == "good"

    with pytest.raises(AppException) as exc:
        await service.create_supply(
            EmergencySupplyCreate(name="测试物资-非法", category="vehicle")
        )
    assert exc.value.status_code == 422

    await service.update_supply(
        supply.id, EmergencySupplyUpdate(status="repair", quantity=3)
    )
    await db_session.commit()

    items, total = await service.list_supplies(status="repair", keyword="测试物资")
    assert total == 1
    assert float(items[0].quantity) == 3.0

    stats = await service.get_stats()
    assert stats.supplies_abnormal >= 1
    assert stats.supplies_by_category.get("protective", 0) >= 1

    assert await service.delete_supply(supply.id) is True
    await db_session.commit()
    assert await service.get_supply(supply.id) is None
