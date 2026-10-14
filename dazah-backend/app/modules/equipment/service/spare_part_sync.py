"""五金备件库存同步：仓储五金镜像 → 设备备件台账（按车间）。

数据源为仓储模块的飞书镜像（material_page_rows），不直连飞书；
五金分布表是批次台账（一行一批次），按物料编号聚合批次结存量后
写入 equipment.spare_parts + spare_part_stocks。仓储多出的表
（202、203-3、热动站等）设备侧无对应车间，不参与；102-2 无对应
五金表（五金表中的“102车间”即 102一车间），备件页为空态。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.spare_part import SparePart, SparePartStock
from app.modules.warehouse import public_api as warehouse_public_api

logger = logging.getLogger(__name__)

# 设备车间 → 仓储五金分布表 page_key
WORKSHOP_HARDWARE_PAGE_KEYS: dict[str, str] = {
    "101-1": "hardware-101-1-workshop",
    "101-2": "hardware-101-2-workshop",
    "102-1": "hardware-102-workshop",
    "103": "hardware-103-workshop",
    "201-1": "hardware-201-1-workshop",
    "201-2": "hardware-201-2-workshop",
    "201-3": "hardware-201-3-workshop",
    "203": "hardware-203-workshop",
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class _AggregatedPart:
    """同一物料编号聚合后的台账行（结存量 = 各批次之和）。"""

    name: str | None
    unit: str | None
    unit_price: float | None
    supplier: str | None
    current_qty: float
    latest_inbound_ms: int


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, _AggregatedPart]:
    """按物料编号聚合批次：结存量求和，其余字段取最近入库批次。"""
    result: dict[str, _AggregatedPart] = {}
    for cells in rows:
        code = _text(cells.get("物料编号"))
        if not code:
            continue  # 空行/占位行不产生备件
        inbound_ms = cells.get("入库日期")
        inbound_ms = inbound_ms if isinstance(inbound_ms, int) else 0
        qty = _num(cells.get("结存量")) or 0.0
        name = _text(cells.get("物料说明"))
        unit = _text(cells.get("单位"))
        price = _num(cells.get("单价（元）"))
        supplier = _text(cells.get("供应商名称"))
        entry = result.get(code)
        if entry is None:
            result[code] = _AggregatedPart(
                name=name,
                unit=unit,
                unit_price=price,
                supplier=supplier,
                current_qty=qty,
                latest_inbound_ms=inbound_ms,
            )
            continue
        entry.current_qty += qty
        if inbound_ms >= entry.latest_inbound_ms:
            entry.latest_inbound_ms = inbound_ms
            if name:
                entry.name = name
            if unit:
                entry.unit = unit
            if price is not None:
                entry.unit_price = price
            if supplier:
                entry.supplier = supplier
    return result


async def sync_workshop(db: AsyncSession, workshop_code: str) -> dict[str, Any]:
    """同步一个车间的五金库存到备件台账；无对应表的车间跳过。"""
    page_key = WORKSHOP_HARDWARE_PAGE_KEYS.get(workshop_code)
    if not page_key:
        return {"skipped": "no-hardware-page"}
    rows, synced_at = await warehouse_public_api.get_material_page_rows(
        db, page_key=page_key
    )
    aggregated = _aggregate_rows(rows)

    existing = {
        part.code: part
        for part in (
            await db.execute(
                select(SparePart).where(
                    SparePart.is_deleted == False,  # noqa: E712
                    SparePart.workshop_code == workshop_code,
                )
            )
        ).scalars().all()
    }
    touched_codes: set[str] = set()
    for code, item in aggregated.items():
        part = existing.get(code)
        if part is None:
            part = SparePart(code=code, workshop_code=workshop_code)
            db.add(part)
            existing[code] = part
        part.name = item.name or part.name or code
        part.unit = item.unit or part.unit or "-"
        part.default_supplier = item.supplier or part.default_supplier
        if item.unit_price is not None:
            part.unit_price = round(item.unit_price, 2)
        touched_codes.add(code)

    # 新增备件先落库拿 id，再建 1:1 库存行
    await db.flush()

    # 库存行（1:1）：同步只更新现存量，安全库存等人工字段不覆盖；
    # 该车间上次同步过但本次消失的物料清零，避免残留过期库存
    stock_map = {
        stock.spare_part_id: stock
        for stock in (
            await db.execute(
                select(SparePartStock).where(SparePartStock.is_deleted == False)  # noqa: E712
            )
        ).scalars().all()
    }
    zeroed = 0
    for code, part in existing.items():
        if part.workshop_code != workshop_code:
            continue
        stock = stock_map.get(part.id)
        if code in touched_codes:
            if stock is None:
                stock = SparePartStock(spare_part_id=part.id, current_qty=0)
                db.add(stock)
            stock.current_qty = round(aggregated[code].current_qty, 2)
        elif stock is not None and (stock.current_qty or 0) != 0:
            stock.current_qty = 0
            zeroed += 1

    return {
        "page": page_key,
        "rows": len(rows),
        "parts": len(aggregated),
        "zeroed": zeroed,
        "source_synced_at": synced_at.isoformat() if synced_at else None,
    }


async def sync_all(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """同步全部映射车间；单车间失败不影响其余。"""
    results: dict[str, dict[str, Any]] = {}
    for workshop_code in WORKSHOP_HARDWARE_PAGE_KEYS:
        try:
            results[workshop_code] = await sync_workshop(db, workshop_code)
        except Exception as error:  # noqa: BLE001
            logger.exception("spare part hardware sync failed [%s]", workshop_code)
            results[workshop_code] = {"error": f"{type(error).__name__}: {error}"[:200]}
    return results
