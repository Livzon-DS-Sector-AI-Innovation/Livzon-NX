"""维修成本核算：工时费率、工单成本钩子与成本报表。

成本三段：备件（既有 spare_parts_cost）+ 工时（完成时按费率×维修时长）
+ 外委（人工补录 external_cost/vendor）。费率解析优先级 person > role > 0。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException
from app.modules.equipment.models.labor_rate import MaintenanceLaborRate
from app.modules.equipment.models.personnel import (
    EquipmentPersonnel,
    EquipmentPersonnelRole,
)
from app.modules.equipment.models.work_order import WorkOrder

logger = logging.getLogger(__name__)


# ── 费率管理 ────────────────────────────────────────────────────────


async def create_labor_rate(
    db: AsyncSession,
    *,
    scope: str,
    hourly_rate: float,
    effective_from: date | None = None,
    role_id: uuid.UUID | None = None,
    person_id: uuid.UUID | None = None,
    remark: str | None = None,
    operator_id: uuid.UUID | None = None,
) -> MaintenanceLaborRate:
    if scope not in ("role", "person"):
        raise AppException(message="费率范围必须为 role 或 person")
    if (scope == "role") != (role_id is not None):
        raise AppException(message="岗位费率必须指定设备角色")
    if (scope == "person") != (person_id is not None):
        raise AppException(message="人员费率必须指定人员")
    if hourly_rate < 0:
        raise AppException(message="时薪不能为负数")

    conditions = [
        MaintenanceLaborRate.scope == scope,
        MaintenanceLaborRate.role_id == role_id,
        MaintenanceLaborRate.person_id == person_id,
        MaintenanceLaborRate.is_deleted == False,  # noqa: E712
    ]
    existing = (
        (await db.execute(select(MaintenanceLaborRate).where(*conditions)))
        .scalars()
        .first()
    )
    if existing is not None:
        raise AppException(message="该目标的费率已存在，请直接编辑")

    rate = MaintenanceLaborRate(
        scope=scope,
        role_id=role_id,
        person_id=person_id,
        hourly_rate=hourly_rate,
        effective_from=effective_from or date.today(),
        remark=remark,
        created_by=operator_id,
    )
    db.add(rate)
    await db.flush()
    return rate


async def update_labor_rate(
    db: AsyncSession,
    rate_id: uuid.UUID,
    *,
    hourly_rate: float | None = None,
    effective_from: date | None = None,
    remark: str | None = None,
    operator_id: uuid.UUID | None = None,
) -> MaintenanceLaborRate:
    rate = await _get_rate(db, rate_id)
    if hourly_rate is not None:
        if hourly_rate < 0:
            raise AppException(message="时薪不能为负数")
        rate.hourly_rate = hourly_rate
    if effective_from is not None:
        rate.effective_from = effective_from
    if remark is not None:
        rate.remark = remark
    rate.updated_by = operator_id
    await db.flush()
    return rate


async def delete_labor_rate(
    db: AsyncSession, rate_id: uuid.UUID, operator_id: uuid.UUID | None = None
) -> None:
    rate = await _get_rate(db, rate_id)
    rate.is_deleted = True
    rate.updated_by = operator_id
    await db.flush()


async def list_labor_rates(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        (
            await db.execute(
                select(MaintenanceLaborRate)
                .where(MaintenanceLaborRate.is_deleted == False)  # noqa: E712
                .order_by(
                    MaintenanceLaborRate.scope,
                    MaintenanceLaborRate.hourly_rate.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    result: list[dict[str, Any]] = []
    for r in rows:
        result.append(
            {
                "id": r.id,
                "scope": r.scope,
                "role_id": r.role_id,
                "person_id": r.person_id,
                "hourly_rate": float(r.hourly_rate),
                "effective_from": r.effective_from.isoformat(),
                "remark": r.remark,
            }
        )
    return result


async def _get_rate(db: AsyncSession, rate_id: uuid.UUID) -> MaintenanceLaborRate:
    rate = (
        (
            await db.execute(
                select(MaintenanceLaborRate).where(
                    MaintenanceLaborRate.id == rate_id,
                    MaintenanceLaborRate.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if rate is None:
        raise AppException(message="费率记录不存在")
    return rate


# ── 费率解析与工时成本 ──────────────────────────────────────────────


async def resolve_hourly_rate(
    db: AsyncSession, person_user_id: uuid.UUID | None
) -> float:
    """人员费率 > 其设备角色费率（取最高）> 0。"""
    if person_user_id is None:
        return 0.0

    person_rate = (
        (
            await db.execute(
                select(MaintenanceLaborRate.hourly_rate).where(
                    MaintenanceLaborRate.scope == "person",
                    MaintenanceLaborRate.person_id == person_user_id,
                    MaintenanceLaborRate.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if person_rate is not None:
        return float(person_rate)

    role_rates = (
        (
            await db.execute(
                select(func.max(MaintenanceLaborRate.hourly_rate))
                .select_from(EquipmentPersonnelRole)
                .join(
                    MaintenanceLaborRate,
                    (MaintenanceLaborRate.scope == "role")
                    & (
                        MaintenanceLaborRate.role_id
                        == EquipmentPersonnelRole.role_id
                    )
                    & (MaintenanceLaborRate.is_deleted == False),  # noqa: E712
                )
                .where(
                    EquipmentPersonnelRole.personnel_id.in_(
                        select(EquipmentPersonnel.id).where(
                            EquipmentPersonnel.user_id == person_user_id,
                            EquipmentPersonnel.is_deleted == False,  # noqa: E712
                        )
                    ),
                    EquipmentPersonnelRole.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalar_one_or_none()
    )
    return float(role_rates) if role_rates is not None else 0.0


async def apply_labor_cost(db: AsyncSession, wo: WorkOrder) -> float:
    """完成工单时计算工时成本（时长 × 维修人费率；无费率记 0）。"""
    duration_min = wo.actual_duration or 0
    rate = await resolve_hourly_rate(
        db, wo.assignee_id if "assignee_id" in wo.__dict__ else None
    )
    labor_cost = round(duration_min / 60 * rate, 2)
    wo.labor_cost = labor_cost
    await db.flush()
    return labor_cost


async def update_external_cost(
    db: AsyncSession,
    work_order_id: uuid.UUID,
    *,
    external_cost: float | None = None,
    external_vendor: str | None = None,
    operator_id: uuid.UUID | None = None,
) -> WorkOrder:
    wo = (
        (
            await db.execute(
                select(WorkOrder).where(
                    WorkOrder.id == work_order_id,
                    WorkOrder.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if wo is None:
        raise AppException(message="工单不存在")
    if external_cost is not None:
        if external_cost < 0:
            raise AppException(message="外委费用不能为负数")
        wo.external_cost = external_cost
    if external_vendor is not None:
        wo.external_vendor = external_vendor or None
    wo.updated_by = operator_id
    await db.flush()
    return wo


# ── 成本报表 ────────────────────────────────────────────────────────


async def get_cost_report(
    db: AsyncSession,
    *,
    workshop_code: str | None = None,
    month: str | None = None,
    group_by: str = "equipment",
) -> dict[str, Any]:
    """维修成本报表：按设备/车间/分类/故障类型聚合三段成本。

    month 格式 YYYY-MM，按 reported_at 过滤；缺省为当月。
    """
    from app.modules.equipment.models.equipment import Equipment

    try:
        if month:
            year, mon = (int(x) for x in month.split("-"))
        else:
            now = datetime.now(UTC)
            year, mon = now.year, now.month
        start = date(year, mon, 1)
        end = (
            date(year + 1, 1, 1)
            if mon == 12
            else date(year, mon + 1, 1)
        )
    except ValueError as e:
        raise AppException(message="月份格式必须为 YYYY-MM") from e

    rows = (
        (
            await db.execute(
                select(WorkOrder, Equipment)
                .join(Equipment, Equipment.id == WorkOrder.equipment_id)
                .where(
                    WorkOrder.reported_at >= start,
                    WorkOrder.reported_at < end,
                    WorkOrder.is_deleted == False,  # noqa: E712
                    Equipment.is_deleted == False,  # noqa: E712
                )
                .options(selectinload(WorkOrder.fault_symptom))
            )
        )
        .all()
    )
    if workshop_code:
        rows = [r for r in rows if r[1].workshop_code == workshop_code]

    buckets: dict[str, dict[str, Any]] = {}
    totals = {
        "orders": 0,
        "spare_cost": 0.0,
        "labor_cost": 0.0,
        "external_cost": 0.0,
    }
    for wo, eq in rows:
        spare = float(wo.spare_parts_cost or 0)
        labor = float(wo.labor_cost or 0)
        external = float(wo.external_cost or 0)
        if group_by == "equipment":
            key = eq.name
            label = f"{eq.name}（{eq.equipment_no}）"
        elif group_by == "workshop":
            key = eq.workshop_code or "-"
            label = eq.workshop_code or "-"
        elif group_by == "fault_type":
            symptom = wo.fault_symptom
            key = symptom.name if symptom else "未分类"
            label = key
        else:
            raise AppException(message="group_by 仅支持 equipment/workshop/fault_type")

        bucket = buckets.setdefault(
            key,
            {
                "label": label,
                "orders": 0,
                "spare_cost": 0.0,
                "labor_cost": 0.0,
                "external_cost": 0.0,
                "total_cost": 0.0,
            },
        )
        bucket["orders"] += 1
        bucket["spare_cost"] += spare
        bucket["labor_cost"] += labor
        bucket["external_cost"] += external
        bucket["total_cost"] += spare + labor + external

        totals["orders"] += 1
        totals["spare_cost"] += spare
        totals["labor_cost"] += labor
        totals["external_cost"] += external

    for b in buckets.values():
        for k in ("spare_cost", "labor_cost", "external_cost", "total_cost"):
            b[k] = round(b[k], 2)
    totals = {
        "orders": totals["orders"],
        "spare_cost": round(totals["spare_cost"], 2),
        "labor_cost": round(totals["labor_cost"], 2),
        "external_cost": round(totals["external_cost"], 2),
        "total_cost": round(
            totals["spare_cost"]
            + totals["labor_cost"]
            + totals["external_cost"],
            2,
        ),
    }
    top = sorted(
        buckets.values(), key=lambda b: b["total_cost"], reverse=True
    )[:10]
    return {
        "month": f"{year}-{mon:02d}",
        "workshop": workshop_code,
        "group_by": group_by,
        "totals": totals,
        "top": top,
    }
