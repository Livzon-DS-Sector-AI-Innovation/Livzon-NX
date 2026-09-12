"""Warehouse module public API.

跨模块调用的唯一入口（见 dazah-backend/AGENTS.md 跨模块边界）：
其他模块不得直接 import 本模块内部 service/repository。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.warehouse.service import WarehouseService


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

    固体按 厂内代码+厂内批号、液体按 入库批号（质量批号整串作为 batch_no）
    定位台账记录并更新 检测结果/不合格项目。详见
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
