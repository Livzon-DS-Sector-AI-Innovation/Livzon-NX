"""Warehouse module public API for cross-module access."""

from __future__ import annotations

import datetime

from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "get_finished_inbound_kg_total",
]


async def get_finished_inbound_kg_total(
    session: AsyncSession,
    *,
    product_name: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> float | None:
    """成品入库总账中指定产品在闭区间日期内的入库合计（KG）。

    数据源为本地飞书快照（分钟级同步延迟），不实时访问飞书；
    返回 None 表示快照尚未建立，调用方应按无数据处理。
    """
    from app.modules.warehouse.service import WarehouseService

    return await WarehouseService(session).get_finished_inbound_kg_total(
        product_name=product_name,
        start_date=start_date,
        end_date=end_date,
    )
