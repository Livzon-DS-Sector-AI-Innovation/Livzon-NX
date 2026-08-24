"""Warehouse 模块暴露给 AI Agent 的 MCP Tools。

覆盖：原辅料库存、包材库存、成品库存、飞书页面查询、异常检测。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.modules.warehouse.models import (
    PackagingMaterialInventory,
    ProductInventory,
    RawMaterialInventory,
)
from app.platform.mcp.deps import get_db
from app.platform.mcp.server import mcp

# ── Tool 1: 原辅料库存 ────────────────────────────────────


@mcp.tool()
async def warehouse_list_raw_materials(
    product_line: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询原辅料库存列表。可按产品线或关键词过滤。

    Args:
        product_line: 产品线/使用类别，可选
        keyword: 搜索关键词（物料名称、编码），可选
    """
    db = get_db()
    stmt = select(RawMaterialInventory).where(
        RawMaterialInventory.is_deleted == False  # noqa: E712
    )
    if product_line:
        stmt = stmt.where(RawMaterialInventory.product_line.ilike(f"%{product_line}%"))
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (RawMaterialInventory.name.ilike(pattern))
            | (RawMaterialInventory.code.ilike(pattern))
        )
    stmt = stmt.order_by(
        RawMaterialInventory.product_line, RawMaterialInventory.name
    ).limit(100)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "code": r.code or "",
            "name": r.name or "",
            "spec": r.spec or "",
            "unit": r.unit or "",
            "available": r.available or 0,
            "safety": r.safety or 0,
            "warning": r.warning or "",
            "product_line": r.product_line or "",
            "today_balance": r.today_balance or 0,
        }
        for r in items
    ]


# ── Tool 2: 包材库存 ──────────────────────────────────────


@mcp.tool()
async def warehouse_list_packaging_materials(
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询包材库存列表。

    Args:
        keyword: 搜索关键词，可选
    """
    db = get_db()
    stmt = select(PackagingMaterialInventory).where(
        PackagingMaterialInventory.is_deleted == False  # noqa: E712
    )
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            (PackagingMaterialInventory.name.ilike(pattern))
            | (PackagingMaterialInventory.code.ilike(pattern))
        )
    stmt = stmt.order_by(PackagingMaterialInventory.name).limit(100)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "code": p.code or "",
            "name": p.name or "",
            "spec": p.spec or "",
            "unit": getattr(p, "unit", "") or "",
            "available": p.available or 0,
            "safety": p.safety or 0,
            "warning": p.warning or "",
        }
        for p in items
    ]


# ── Tool 3: 成品库存 ──────────────────────────────────────


@mcp.tool()
async def warehouse_list_products(
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """
    查询成品库存列表。

    Args:
        keyword: 搜索关键词（产品名称），可选
    """
    db = get_db()
    stmt = select(ProductInventory).where(
        ProductInventory.is_deleted == False  # noqa: E712
    )
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(ProductInventory.name.ilike(pattern))
    stmt = stmt.order_by(ProductInventory.name).limit(100)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name or "",
            "spec": p.spec or "",
            "unit": p.unit or "",
            "order_quantity": p.order_quantity or 0,
            "pending_quantity": p.pending_quantity or 0,
            "qualified_quantity": p.qualified_quantity or 0,
            "remaining_quantity": p.remaining_quantity or 0,
        }
        for p in items
    ]


# ── Tool 4: 库存异常检测 ───────────────────────────────────


@mcp.tool()
async def warehouse_detect_anomalies() -> dict[str, Any]:
    """
    检测库存异常：安全库存不足、零库存预警。
    返回异常物料列表和统计。
    """
    db = get_db()

    # 原辅料异常
    raw_stmt = select(RawMaterialInventory).where(
        RawMaterialInventory.is_deleted == False,  # noqa: E712
        (
            (RawMaterialInventory.available <= RawMaterialInventory.safety)
            | (RawMaterialInventory.warning.isnot(None))
            | (RawMaterialInventory.warning != "")
        ),
    )
    raw_result = await db.execute(raw_stmt)
    raw_anomalies = raw_result.scalars().all()

    # 包材异常
    pkg_stmt = select(PackagingMaterialInventory).where(
        PackagingMaterialInventory.is_deleted == False,  # noqa: E712
        (
            (PackagingMaterialInventory.available <= PackagingMaterialInventory.safety)
            | (PackagingMaterialInventory.warning.isnot(None))
            | (PackagingMaterialInventory.warning != "")
        ),
    )
    pkg_result = await db.execute(pkg_stmt)
    pkg_anomalies = pkg_result.scalars().all()

    return {
        "raw_material_anomalies": len(raw_anomalies),
        "raw_material_details": [
            {
                "name": r.name or "",
                "code": r.code or "",
                "available": r.available or 0,
                "safety": r.safety or 0,
                "warning": r.warning or "",
            }
            for r in raw_anomalies[:10]
        ],
        "packaging_anomalies": len(pkg_anomalies),
        "packaging_details": [
            {
                "name": p.name or "",
                "available": p.available or 0,
                "safety": p.safety or 0,
                "warning": p.warning or "",
            }
            for p in pkg_anomalies[:10]
        ],
    }


# ── Tool 5: 库存概览 ──────────────────────────────────────


@mcp.tool()
async def warehouse_inventory_summary() -> dict[str, Any]:
    """
    获取库存概览统计：原辅料、包材、成品的总数和预警数。
    """
    db = get_db()
    from sqlalchemy import func as sa_func

    # 原辅料统计
    raw_total = await db.scalar(
        select(sa_func.count())
        .select_from(RawMaterialInventory)
        .where(
            RawMaterialInventory.is_deleted == False  # noqa: E712
        )
    )
    raw_low = await db.scalar(
        select(sa_func.count())
        .select_from(RawMaterialInventory)
        .where(
            RawMaterialInventory.is_deleted == False,  # noqa: E712
            RawMaterialInventory.available <= RawMaterialInventory.safety,
            RawMaterialInventory.safety > 0,
        )
    )

    # 包材统计
    pkg_total = await db.scalar(
        select(sa_func.count())
        .select_from(PackagingMaterialInventory)
        .where(
            PackagingMaterialInventory.is_deleted == False  # noqa: E712
        )
    )

    # 成品统计
    prod_total = await db.scalar(
        select(sa_func.count())
        .select_from(ProductInventory)
        .where(
            ProductInventory.is_deleted == False  # noqa: E712
        )
    )

    return {
        "raw_materials": {"total": raw_total or 0, "low_stock": raw_low or 0},
        "packaging_materials": {"total": pkg_total or 0},
        "products": {"total": prod_total or 0},
    }
