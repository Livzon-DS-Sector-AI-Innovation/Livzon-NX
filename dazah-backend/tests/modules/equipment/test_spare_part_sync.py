"""五金备件同步：仓储五金镜像 → 设备备件台账（按车间聚合批次）。"""

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.spare_part import SparePart, SparePartStock
from app.modules.equipment.service import spare_part_sync


@pytest.fixture(autouse=True)
async def _clean_spare_tables(db_session: AsyncSession) -> Any:
    async def cleanup() -> None:
        for row in (await db_session.execute(select(SparePartStock))).scalars().all():
            await db_session.delete(row)
        for row in (await db_session.execute(select(SparePart))).scalars().all():
            await db_session.delete(row)
        await db_session.commit()

    await cleanup()
    yield
    await cleanup()


def _row(code: str, qty: Any, inbound_ms: int, **extra: Any) -> dict[str, Any]:
    return {
        "物料编号": code,
        "物料说明": extra.get("name"),
        "单位": extra.get("unit", "个"),
        "结存量": qty,
        "入库日期": inbound_ms,
        "单价（元）": extra.get("price"),
        "供应商名称": extra.get("supplier"),
    }


async def test_sync_workshop_aggregates_batches_by_code(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同物料多批次结存量求和（小数不丢），字段取最近入库批次；空行丢弃。"""
    rows = [
        {"物料编号": None, "结存量": 0, "入库日期": 1791734400000},
        _row("51018847", 5, 1762272000000, name="碳钢衬氟球阀,DN20-PN16",
             price="300.88", supplier="宁夏永徽阀门机电有限公司"),
        _row("51119736", 12.5, 1791734400000, name="碳钢管,脚手架用/φ48",
             unit="米", price="22", supplier="供应商A"),
        _row("51119736", 3.5, 1791820800000, name="碳钢管,脚手架用/φ48",
             unit="米", price="25", supplier="供应商B"),
    ]
    captured: dict[str, str] = {}

    async def fake_get_rows(session: Any, *, page_key: str) -> Any:
        captured["page_key"] = page_key
        return rows, datetime(2026, 10, 13, 8, 0, tzinfo=UTC)

    monkeypatch.setattr(
        spare_part_sync.warehouse_public_api, "get_material_page_rows", fake_get_rows
    )

    result = await spare_part_sync.sync_workshop(db_session, "102-1")
    # 五金表中的“102车间”即 102一车间
    assert captured["page_key"] == "hardware-102-workshop"
    assert result["parts"] == 2

    parts = {
        p.code: p
        for p in (await db_session.execute(select(SparePart))).scalars().all()
    }
    valve = parts["51018847"]
    assert valve.workshop_code == "102-1"
    assert valve.name == "碳钢衬氟球阀,DN20-PN16"
    assert float(valve.unit_price) == 300.88
    assert valve.default_supplier == "宁夏永徽阀门机电有限公司"

    tube = parts["51119736"]
    assert float(tube.unit_price) == 25  # 最近批次
    assert tube.default_supplier == "供应商B"
    stocks = {
        s.spare_part_id: s
        for s in (await db_session.execute(select(SparePartStock))).scalars().all()
    }
    assert float(stocks[tube.id].current_qty) == 16.0  # 12.5 + 3.5


async def test_sync_workshop_updates_and_zeroes_missing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重复同步更新现存量；镜像里消失的物料清零，不残留过期库存。"""
    holder: dict[str, list[dict[str, Any]]] = {
        "rows": [
            _row("A1", 4, 1791734400000, name="物料A", price="10"),
            _row("B2", 2, 1791734400000, name="物料B", price="8"),
        ]
    }

    async def fake_get_rows(session: Any, *, page_key: str) -> Any:
        return holder["rows"], None

    monkeypatch.setattr(
        spare_part_sync.warehouse_public_api, "get_material_page_rows", fake_get_rows
    )

    await spare_part_sync.sync_workshop(db_session, "101-1")
    holder["rows"] = [_row("A1", 1, 1791734400000, name="物料A", price="10")]
    result = await spare_part_sync.sync_workshop(db_session, "101-1")
    assert result["zeroed"] == 1

    parts = {
        p.code: p
        for p in (await db_session.execute(select(SparePart))).scalars().all()
    }
    stocks = {
        s.spare_part_id: s
        for s in (await db_session.execute(select(SparePartStock))).scalars().all()
    }
    assert float(stocks[parts["A1"].id].current_qty) == 1
    assert float(stocks[parts["B2"].id].current_qty) == 0


async def test_sync_workshop_skips_unmapped_workshop(
    db_session: AsyncSession,
) -> None:
    """无对应五金表的车间（如 102-2）跳过，不产生数据。"""
    result = await spare_part_sync.sync_workshop(db_session, "102-2")
    assert result == {"skipped": "no-hardware-page"}
    assert (await db_session.execute(select(SparePart))).scalars().first() is None


async def test_sync_same_code_in_two_workshops_keeps_both(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一物料编号出现在多个车间表：各车间保留各自的行，互不覆盖。"""
    by_workshop: dict[str, list[dict[str, Any]]] = {
        "hardware-101-1-workshop": [
            _row("C1", 4, 1791734400000, name="共用物料", price="10")
        ],
        "hardware-101-2-workshop": [
            _row("C1", 7, 1791734400000, name="共用物料", price="11")
        ],
    }

    async def fake_get_rows(session: Any, *, page_key: str) -> Any:
        return by_workshop[page_key], None

    monkeypatch.setattr(
        spare_part_sync.warehouse_public_api, "get_material_page_rows", fake_get_rows
    )

    await spare_part_sync.sync_workshop(db_session, "101-1")
    await spare_part_sync.sync_workshop(db_session, "101-2")

    parts = (
        await db_session.execute(select(SparePart).order_by(SparePart.workshop_code))
    ).scalars().all()
    assert [(p.workshop_code, p.code) for p in parts] == [
        ("101-1", "C1"),
        ("101-2", "C1"),
    ]
    stocks = {
        p.code + "@" + p.workshop_code: s.current_qty
        for p in parts
        for s in (await db_session.execute(select(SparePartStock))).scalars().all()
        if s.spare_part_id == p.id
    }
    assert stocks == {"C1@101-1": 4, "C1@101-2": 7}


async def test_sync_201_2_split_workshops_share_hardware_page(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """201 二车间按产品线拆分后 MC/DR 共用同一五金表：各车间保留各自的行。"""
    rows = [_row("C9", 5, 1791734400000, name="五金件", price="9")]
    seen_page_keys: list[str] = []

    async def fake_get_rows(session: Any, *, page_key: str) -> Any:
        seen_page_keys.append(page_key)
        return rows, None

    monkeypatch.setattr(
        spare_part_sync.warehouse_public_api, "get_material_page_rows", fake_get_rows
    )

    await spare_part_sync.sync_workshop(db_session, "201-2-MC")
    await spare_part_sync.sync_workshop(db_session, "201-2-DR")

    # 两个新车间代码都映射到 201 二车间的五金分布表
    assert seen_page_keys == ["hardware-201-2-workshop", "hardware-201-2-workshop"]
    parts = (await db_session.execute(select(SparePart))).scalars().all()
    assert sorted(p.workshop_code for p in parts) == ["201-2-DR", "201-2-MC"]
