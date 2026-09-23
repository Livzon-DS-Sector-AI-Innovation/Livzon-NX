"""Warehouse module public API.

跨模块调用的唯一入口（见 dazah-backend/AGENTS.md 跨模块边界）：
其他模块不得直接 import 本模块内部 service/repository。
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.service import WarehouseService

__all__ = [
    "get_finished_inbound_batches",
    "get_finished_inbound_kg_total",
    "get_finished_inbound_summary",
    "update_inbound_inspection_result",
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
    return await WarehouseService(session).get_finished_inbound_kg_total(
        product_name=product_name,
        start_date=start_date,
        end_date=end_date,
    )


async def get_finished_inbound_summary(
    session: AsyncSession,
    *,
    product_name: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> tuple[int, float] | None:
    """成品入库总账中指定产品在闭区间日期内的 (入库批次数, KG 合计)。

    一行即一次入库（预混剂等一批一行），行数即入库批次；KG 与
    get_finished_inbound_kg_total 同口径。返回 None 表示快照尚未建立。
    """
    return await WarehouseService(session).get_finished_inbound_summary(
        product_name=product_name,
        start_date=start_date,
        end_date=end_date,
    )


async def get_finished_inbound_batches(
    session: AsyncSession,
    *,
    product_name: str,
) -> list[dict[str, Any]] | None:
    """成品入库明细（飞书「入库台账（明细）」）中该产品的批次级行。

    每行含 batch_no（入库标签批号）、inbound_date、qty、confirmed；
    「入库确认」未勾的行不算实际入库，由调用方按业务过滤。
    返回 None 表示快照尚未建立。
    """
    return await WarehouseService(session).get_finished_inbound_batches(
        product_name=product_name,
    )


async def update_inbound_inspection_result(
    db: AsyncSession,
    *,
    material_module: str,
    material_code: str,
    batch_no: str,
    result: str,
    unqualified_items: str | None = None,
) -> dict[str, Any]:
    """质量物料检验结果 → 仓储入库台账联动。

    固体按 厂内代码+厂内批号（入库总账）匹配；液体先按 入库批号（质量批号
    整串作为 batch_no，液体原辅料入库/槽车类）匹配，未命中再拆 代码+批号
    到 入库总账（桶装液体）。定位后更新 检测结果/不合格项目。详见
    WarehouseService.update_inbound_inspection_result。
    """
    service = WarehouseService(db)
    return await service.update_inbound_inspection_result(
        material_module=material_module,
        material_code=material_code,
        batch_no=batch_no,
        result=result,
        unqualified_items=unqualified_items,
    )
