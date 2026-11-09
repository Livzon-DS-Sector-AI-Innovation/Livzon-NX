"""备件采购建议：安全线扫描生成、提交采购（对接采购模块）、到货回写。

模块边界：
- equipment 只产出"建议"与数量口径；采购规则、供应商、审批全在
  procurement（提交即生成采购草稿单，由采购员在采购模块走正常流程）；
- 到货支持两条路径：采购建议页人工「登记到货」（当前主路径）与
  procurement 到货流程回调 equipment.public_api.spare_part_purchase_arrived
  （预留自动路径，采购侧到货自动化接入后生效）。
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.modules.equipment.models.purchase_suggestion import (
    SparePartPurchaseSuggestion,
)
from app.modules.equipment.models.spare_part import SparePart, SparePartStock
from app.modules.equipment.schemas.spare_part import StockInboundRequest
from app.modules.equipment.service import spare_part as spare_part_service

logger = logging.getLogger(__name__)

_OPEN_STATUSES = ("suggested", "submitted", "partial")


def calc_suggest_qty(
    current_qty: int, safety_qty: int, min_order_qty: int = 1
) -> int:
    """建议量 = 安全线×2 − 现库存，向上取整到最小采购批量的整数倍。"""
    if current_qty >= safety_qty:
        return 0
    raw = safety_qty * 2 - current_qty
    step = max(1, min_order_qty)
    return int(math.ceil(raw / step) * step)


async def scan_and_suggest(db: AsyncSession) -> dict[str, int]:
    """扫描全部启用备件库存 < 安全线者，upsert 采购建议。

    幂等：同备件存在未关闭建议时只更新数量与库存快照，不重复建；
    库存回升到安全线以上时，suggested 状态的旧建议自动取消。
    """
    rows = (
        (
            await db.execute(
                select(SparePart, SparePartStock)
                .join(SparePartStock, SparePartStock.spare_part_id == SparePart.id)
                .where(
                    SparePart.is_active == True,  # noqa: E712
                    SparePart.is_deleted == False,  # noqa: E712
                    SparePartStock.is_deleted == False,  # noqa: E712
                )
            )
        )
        .all()
    )
    created = updated = cancelled = 0
    for part, stock in rows:
        open_suggestion = (
            (
                await db.execute(
                    select(SparePartPurchaseSuggestion).where(
                        SparePartPurchaseSuggestion.spare_part_id == part.id,
                        SparePartPurchaseSuggestion.status.in_(_OPEN_STATUSES),
                        SparePartPurchaseSuggestion.is_deleted == False,  # noqa: E712
                    )
                )
            )
            .scalars()
            .first()
        )
        suggest_qty = calc_suggest_qty(
            stock.current_qty, stock.safety_qty, stock.min_order_qty
        )
        if suggest_qty <= 0:
            if open_suggestion is not None and open_suggestion.status == "suggested":
                open_suggestion.status = "cancelled"
                cancelled += 1
            continue
        if open_suggestion is not None:
            open_suggestion.current_qty = stock.current_qty
            open_suggestion.safety_qty = stock.safety_qty
            if open_suggestion.status == "suggested":
                open_suggestion.suggest_qty = suggest_qty
            open_suggestion.unit_price = part.unit_price
            updated += 1
        else:
            db.add(
                SparePartPurchaseSuggestion(
                    spare_part_id=part.id,
                    current_qty=stock.current_qty,
                    safety_qty=stock.safety_qty,
                    suggest_qty=suggest_qty,
                    status="suggested",
                    source="auto",
                    unit_price=part.unit_price,
                )
            )
            created += 1
    await db.flush()
    return {"created": created, "updated": updated, "cancelled": cancelled}


async def list_suggestions(
    db: AsyncSession,
    status: str | None = None,
    workshop_code: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """建议列表（联备件名称/编码/车间）。"""
    conditions = [SparePartPurchaseSuggestion.is_deleted == False]  # noqa: E712
    if status:
        conditions.append(SparePartPurchaseSuggestion.status == status)

    rows = (
        (
            await db.execute(
                select(SparePartPurchaseSuggestion, SparePart)
                .join(
                    SparePart,
                    SparePart.id == SparePartPurchaseSuggestion.spare_part_id,
                )
                .where(*conditions)
                .order_by(SparePartPurchaseSuggestion.created_at.desc())
            )
        )
        .all()
    )
    items: list[dict[str, Any]] = []
    for sug, part in rows:
        if workshop_code and part.workshop_code != workshop_code:
            continue
        items.append(
            {
                "id": sug.id,
                "spare_part_id": part.id,
                "spare_part_code": part.code,
                "spare_part_name": part.name,
                "specification": part.specification,
                "unit": part.unit,
                "workshop_code": part.workshop_code,
                "default_supplier": part.default_supplier,
                "current_qty": sug.current_qty,
                "safety_qty": sug.safety_qty,
                "suggest_qty": sug.suggest_qty,
                "arrived_qty": sug.arrived_qty,
                "status": sug.status,
                "source": sug.source,
                "purchase_request_id": sug.purchase_request_id,
                "purchase_ref": sug.purchase_ref,
                "unit_price": (
                    float(sug.unit_price) if sug.unit_price is not None else None
                ),
                "submitted_at": sug.submitted_at.isoformat()
                if sug.submitted_at
                else None,
                "created_at": sug.created_at.isoformat()
                if sug.created_at
                else None,
            }
        )
    total = len(items)
    start = (page - 1) * page_size
    return items[start : start + page_size], total


async def update_suggest_qty(
    db: AsyncSession, suggestion_id: uuid.UUID, qty: int
) -> SparePartPurchaseSuggestion:
    sug = await _get_open(db, suggestion_id, allowed=("suggested",))
    if qty < 1:
        raise AppException(message="建议数量必须大于 0")
    sug.suggest_qty = qty
    await db.flush()
    return sug


async def cancel_suggestion(
    db: AsyncSession, suggestion_id: uuid.UUID, user_id: uuid.UUID
) -> SparePartPurchaseSuggestion:
    sug = await _get_open(
        db, suggestion_id, allowed=("suggested", "submitted", "partial")
    )
    sug.status = "cancelled"
    sug.updated_by = user_id
    await db.flush()
    return sug


async def submit_to_procurement(
    db: AsyncSession, suggestion_ids: list[uuid.UUID], user_id: uuid.UUID
) -> dict[str, Any]:
    """批量提交采购：调采购模块公开契约生成草稿采购申请单。

    单条建议失败不影响其他条；返回 {submitted, purchase_request_id, failed}。
    """
    from datetime import date

    from app.modules.procurement.public_api import (
        create_equipment_purchase_request,
    )

    submitted = 0
    failed: list[dict[str, str]] = []
    purchase_request_id: str | None = None

    for sid in suggestion_ids:
        sug = (
            (
                await db.execute(
                    select(SparePartPurchaseSuggestion)
                    .where(SparePartPurchaseSuggestion.id == sid)
                    .options(
                        selectinload(SparePartPurchaseSuggestion.spare_part)
                    )
                )
            )
            .scalars()
            .first()
        )
        if sug is None or sug.is_deleted:
            failed.append({"id": str(sid), "reason": "建议不存在"})
            continue
        if sug.status != "suggested":
            failed.append(
                {"id": str(sid), "reason": f"状态为 {sug.status}，仅待提交可提交"}
            )
            continue
        part = sug.spare_part
        if part is None:
            failed.append({"id": str(sid), "reason": "关联备件缺失"})
            continue
        try:
            result = await create_equipment_purchase_request(
                db,
                items=[
                    {
                        "product_name": part.name,
                        "specification": part.specification or "",
                        "material_code": part.code,
                        "quantity": sug.suggest_qty,
                        "unit": part.unit,
                        "unit_price": float(sug.unit_price or part.unit_price or 0),
                        "remarks": (
                            f"设备备件低于安全线自动建议（库存 {sug.current_qty}"
                            f"/安全线 {sug.safety_qty}）"
                        ),
                    }
                ],
            )
        except AppException as exc:
            failed.append({"id": str(sid), "reason": exc.message})
            continue
        except Exception:
            logger.exception("提交采购失败: %s", sid)
            failed.append({"id": str(sid), "reason": "采购模块调用失败"})
            continue

        request_id = str(result["request_id"])
        sug.status = "submitted"
        sug.submitted_by = user_id
        sug.submitted_at = datetime.now(UTC)
        sug.purchase_request_id = request_id
        sug.purchase_ref = (
            f"采购申请 {request_id[:8]}（{date.today().isoformat()}）"
        )
        submitted += 1
        if purchase_request_id is None:
            purchase_request_id = request_id

    await db.flush()
    return {
        "submitted": submitted,
        "purchase_request_id": purchase_request_id,
        "failed": failed,
    }


async def register_arrival(
    db: AsyncSession,
    suggestion_id: uuid.UUID,
    arrived_qty: int,
    user_id: uuid.UUID | None = None,
) -> SparePartPurchaseSuggestion:
    """登记到货：执行备件入库并推进建议状态（partial/done）。"""
    if arrived_qty < 1:
        raise AppException(message="到货数量必须大于 0")
    sug = await _get_open(
        db, suggestion_id, allowed=("submitted", "partial")
    )
    await spare_part_service.inbound_stock(
        db,
        sug.spare_part_id,
        StockInboundRequest(
            quantity=arrived_qty,
            remark=(
                f"采购建议到货入库（建议 {sug.suggest_qty}，到货 {arrived_qty}）"
            ),
        ),
    )
    sug.arrived_qty += arrived_qty
    sug.status = "done" if sug.arrived_qty >= sug.suggest_qty else "partial"
    sug.updated_by = user_id
    await db.flush()
    return sug


async def _get_open(
    db: AsyncSession,
    suggestion_id: uuid.UUID,
    *,
    allowed: tuple[str, ...],
) -> SparePartPurchaseSuggestion:
    sug = (
        (
            await db.execute(
                select(SparePartPurchaseSuggestion).where(
                    SparePartPurchaseSuggestion.id == suggestion_id,
                    SparePartPurchaseSuggestion.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if sug is None:
        raise AppException(message="采购建议不存在")
    if sug.status not in allowed:
        raise AppException(
            message=f"建议当前状态为「{sug.status}」，不允许该操作"
        )
    return sug


async def notify_low_stock_summary(db: AsyncSession) -> None:
    """扫描后有新建议时通知设备管理员（当前日志留痕，卡片后续接入）。"""
    rows = (
        (
            await db.execute(
                select(SparePartPurchaseSuggestion).where(
                    SparePartPurchaseSuggestion.status == "suggested",
                    SparePartPurchaseSuggestion.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    if rows:
        logger.info("当前待处理备件采购建议 %d 条", len(rows))
