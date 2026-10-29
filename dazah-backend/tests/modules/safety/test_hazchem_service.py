"""危化品与 MSDS 服务层测试（真实服务 + 独立测试库）。

覆盖：档案查重、存量唯一约束（同化学品同车间）、超储判定与
超储 Top 排序、统计聚合。
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import (
    ChemicalInventory,
    ChemicalMsdsAttachment,
    HazardousChemical,
)
from app.modules.safety.schemas.hazchem import (
    ChemicalInventoryCreate,
    ChemicalInventoryUpdate,
    HazardousChemicalCreate,
)
from app.modules.safety.service.hazchem import (
    HazchemService,
    inventory_over_limit,
)


@pytest.fixture(autouse=True)
async def _cleanup_hazchem(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    chemical_ids = select(HazardousChemical.id).where(
        HazardousChemical.name.like("测试化学品-%")
    )
    await db_session.execute(
        delete(ChemicalMsdsAttachment).where(
            ChemicalMsdsAttachment.chemical_id.in_(chemical_ids)
        )
    )
    await db_session.execute(
        delete(ChemicalInventory).where(
            ChemicalInventory.chemical_id.in_(chemical_ids)
        )
    )
    await db_session.execute(
        delete(HazardousChemical).where(HazardousChemical.name.like("测试化学品-%"))
    )
    await db_session.commit()


async def test_inventory_over_limit_helper() -> None:
    assert inventory_over_limit(5.0, 3.0) is True
    assert inventory_over_limit(3.0, 3.0) is False
    assert inventory_over_limit(5.0, None) is False


async def test_create_chemical_and_duplicate_name(db_session: AsyncSession) -> None:
    service = HazchemService(db_session)
    chemical = await service.create_chemical(
        HazardousChemicalCreate(
            name="测试化学品-乙醇",
            cas_no="64-17-5",
            category="flammable_liquid",
            hazard_statements="易燃液体",
        )
    )
    assert chemical.category == "flammable_liquid"
    assert "64-17-5" in chemical.search_text

    with pytest.raises(AppException) as exc:
        await service.create_chemical(
            HazardousChemicalCreate(name="测试化学品-乙醇", category="other")
        )
    assert exc.value.status_code == 409

    with pytest.raises(AppException) as exc:
        await service.create_chemical(
            HazardousChemicalCreate(name="测试化学品-放射源", category="radioactive")
        )
    assert exc.value.status_code == 422


async def test_inventory_unique_and_over_limit_top(db_session: AsyncSession) -> None:
    service = HazchemService(db_session)
    chemical = await service.create_chemical(
        HazardousChemicalCreate(name="测试化学品-浓氨水", category="corrosive")
    )
    other = await service.create_chemical(
        HazardousChemicalCreate(name="测试化学品-氢氧化钠", category="corrosive")
    )

    await service.create_inventory(
        ChemicalInventoryCreate(
            chemical_id=chemical.id,
            workshop="测试车间A",
            quantity=9.0,
            upper_limit=3.0,
            unit="kg",
        )
    )
    # 同化学品同车间 → 409
    with pytest.raises(AppException) as exc:
        await service.create_inventory(
            ChemicalInventoryCreate(
                chemical_id=chemical.id, workshop="测试车间A", quantity=1.0
            )
        )
    assert exc.value.status_code == 409

    await service.create_inventory(
        ChemicalInventoryCreate(
            chemical_id=other.id, workshop="测试车间A", quantity=1.0, upper_limit=8.0
        )
    )
    await db_session.commit()

    over_limit = await service.get_over_limit_top(limit=10)
    assert any(
        item.chemical_name == "测试化学品-浓氨水" and item.workshop == "测试车间A"
        for item in over_limit
    )
    assert all(item.chemical_name != "测试化学品-氢氧化钠" for item in over_limit)
    target = next(i for i in over_limit if i.chemical_name == "测试化学品-浓氨水")
    assert target.over_pct == 200.0

    items, total = await service.list_inventories(over_limit_only=True)
    assert total == 1
    assert items[0].over_limit is True

    stats = await service.get_stats()
    assert stats.chemicals_total >= 2
    assert stats.inventory.over_limit_count == 1
    assert stats.inventory.limited_count == 2


async def test_update_and_delete_inventory(db_session: AsyncSession) -> None:
    service = HazchemService(db_session)
    chemical = await service.create_chemical(
        HazardousChemicalCreate(name="测试化学品-盐酸", category="corrosive")
    )
    inventory = await service.create_inventory(
        ChemicalInventoryCreate(
            chemical_id=chemical.id, workshop="测试车间B", quantity=2.0, upper_limit=5.0
        )
    )
    await db_session.commit()

    updated = await service.update_inventory(
        inventory.id, ChemicalInventoryUpdate(quantity=6.0)
    )
    assert float(updated.quantity) == 6.0
    await db_session.commit()

    response = await service.get_inventory_response(inventory.id)
    assert response.over_limit is True

    assert await service.delete_inventory(inventory.id) is True
    await db_session.commit()
    with pytest.raises(NotFoundException):
        await service.get_inventory_response(inventory.id)

    assert await service.delete_chemical(chemical.id) is True
    assert await service.get_chemical(chemical.id) is None
