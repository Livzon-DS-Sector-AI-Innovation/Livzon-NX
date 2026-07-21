"""Read-side dashboard and trend analysis for quality inspection records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.inspection import (
    FinishedProductInspection,
    InspectionRecord,
    LabInstrument,
    LabItem,
    LiquidMaterialInspection,
    SolidMaterialInspection,
)
from app.modules.quality.schemas.inspection_dashboard import (
    InspectionDashboardLatestRecord,
    InspectionDashboardResourceSummary,
    InspectionDashboardResponse,
    InspectionTrendAlert,
    InspectionTrendPoint,
    InspectionTrendResponse,
    InspectionTrendSummary,
)

_QUALIFIED_CONCLUSIONS = {"合格", "通过", "正常"}
_NUMERIC_VALUE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")
_RANGE_PATTERN = re.compile(
    r"(?P<lower>[-+]?\d+(?:\.\d+)?)\s*(?:~|～|至|—|–|-)\s*"
    r"(?P<upper>[-+]?\d+(?:\.\d+)?)"
)
_UPPER_LIMIT_PATTERN = re.compile(r"(?:≤|<=|<)\s*(?P<value>[-+]?\d+(?:\.\d+)?)")
_LOWER_LIMIT_PATTERN = re.compile(r"(?:≥|>=|>)\s*(?P<value>[-+]?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class InspectionDashboardResource:
    code: str
    label: str
    model: type[Any]
    subject_field: str
    batch_field: str | None
    is_measurement_resource: bool


_RESOURCES: tuple[InspectionDashboardResource, ...] = (
    InspectionDashboardResource(
        "inspection_records",
        "通用检验",
        InspectionRecord,
        "product_name",
        "batch_no",
        True,
    ),
    InspectionDashboardResource(
        "finished_product_inspections",
        "成品检验",
        FinishedProductInspection,
        "product_name",
        "batch_no",
        True,
    ),
    InspectionDashboardResource(
        "solid_material_inspections",
        "固体物料检验",
        SolidMaterialInspection,
        "material_name",
        "material_batch",
        True,
    ),
    InspectionDashboardResource(
        "liquid_material_inspections",
        "液体物料检验",
        LiquidMaterialInspection,
        "material_name",
        "material_batch",
        True,
    ),
    InspectionDashboardResource(
        "lab_items",
        "实验室物品",
        LabItem,
        "name",
        "batch_no",
        False,
    ),
    InspectionDashboardResource(
        "lab_instruments",
        "实验室仪器",
        LabInstrument,
        "name",
        "serial_no",
        False,
    ),
)
_RESOURCES_BY_CODE = {resource.code: resource for resource in _RESOURCES}


def get_resource(resource_code: str) -> InspectionDashboardResource:
    resource = _RESOURCES_BY_CODE.get(resource_code)
    if resource is None:
        raise ValueError("不支持的检验资源")
    return resource


def _get_value(record: Any, field_name: str | None) -> Any:
    return getattr(record, field_name, None) if field_name else None


def _record_conclusion(record: Any) -> str | None:
    return _get_value(record, "conclusion") or _get_value(record, "status")


def _parse_numeric_value(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    match = _NUMERIC_VALUE_PATTERN.search(raw_value.replace(",", ""))
    return float(match.group()) if match else None


def _parse_specification_limits(
    specification: str | None,
) -> tuple[float | None, float | None]:
    if not specification:
        return None, None
    normalized = specification.replace(",", "")
    range_match = _RANGE_PATTERN.search(normalized)
    if range_match:
        return float(range_match.group("lower")), float(range_match.group("upper"))

    lower_match = _LOWER_LIMIT_PATTERN.search(normalized)
    upper_match = _UPPER_LIMIT_PATTERN.search(normalized)
    lower_limit = float(lower_match.group("value")) if lower_match else None
    upper_limit = float(upper_match.group("value")) if upper_match else None
    return lower_limit, upper_limit


async def get_inspection_dashboard(db: AsyncSession) -> InspectionDashboardResponse:
    summaries: list[InspectionDashboardResourceSummary] = []
    latest_records: list[InspectionDashboardLatestRecord] = []

    for resource in _RESOURCES:
        model = resource.model
        total = (
            await db.execute(
                select(func.count()).select_from(model).where(model.is_deleted.is_(False))
            )
        ).scalar_one()
        conclusion_column = getattr(model, "conclusion", None)
        if conclusion_column is None:
            conclusion_column = model.status
        qualified = (
            await db.execute(
                select(func.count())
                .select_from(model)
                .where(
                    model.is_deleted.is_(False),
                    conclusion_column.in_(_QUALIFIED_CONCLUSIONS),
                )
            )
        ).scalar_one()
        summaries.append(
            InspectionDashboardResourceSummary(
                resource_code=resource.code,
                resource_name=resource.label,
                total=total,
                qualified=qualified,
                attention_required=max(total - qualified, 0),
            )
        )

        inspection_date_column = getattr(model, "inspection_date", None)
        order_by = [model.created_at.desc()]
        if inspection_date_column is not None:
            order_by.insert(0, inspection_date_column.desc().nulls_last())
        rows = list(
            (
                await db.execute(
                    select(model)
                    .where(model.is_deleted.is_(False))
                    .order_by(*order_by)
                    .limit(4)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            latest_records.append(
                InspectionDashboardLatestRecord(
                    id=row.id,
                    resource_code=resource.code,
                    resource_name=resource.label,
                    inspection_no=_get_value(row, "inspection_no"),
                    subject=_get_value(row, resource.subject_field),
                    batch_no=_get_value(row, resource.batch_field),
                    inspection_item=_get_value(row, "inspection_item"),
                    test_result=_get_value(row, "test_result"),
                    specification=_get_value(row, "specification"),
                    conclusion=_record_conclusion(row),
                    inspection_date=_get_value(row, "inspection_date"),
                    created_at=row.created_at,
                )
            )

    latest_records.sort(
        key=lambda item: (
            item.inspection_date or item.created_at.date(),
            item.created_at,
        ),
        reverse=True,
    )
    return InspectionDashboardResponse(
        resource_summaries=summaries,
        latest_records=latest_records[:12],
    )


async def get_inspection_trend(
    db: AsyncSession,
    *,
    resource_code: str,
    subject: str | None,
    inspection_item: str | None,
    limit: int,
) -> InspectionTrendResponse:
    resource = get_resource(resource_code)
    if not resource.is_measurement_resource:
        raise ValueError("当前资源不支持检验趋势分析")

    model = resource.model
    conditions = [model.is_deleted.is_(False), model.test_result.is_not(None)]
    if subject and subject.strip():
        conditions.append(getattr(model, resource.subject_field) == subject.strip())
    if inspection_item and inspection_item.strip():
        conditions.append(model.inspection_item == inspection_item.strip())

    rows = list(
        (
            await db.execute(
                select(model)
                .where(*conditions)
                .order_by(
                    model.inspection_date.desc().nulls_last(),
                    model.created_at.desc(),
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    rows.reverse()

    normalized_rows = [(row, _parse_numeric_value(row.test_result)) for row in rows]
    normalized_rows = [item for item in normalized_rows if item[1] is not None]
    values = [value for _, value in normalized_rows if value is not None]
    mean = fmean(values) if values else None
    standard_deviation = pstdev(values) if len(values) > 1 else None
    lower_control_limit = (
        mean - 3 * standard_deviation
        if mean is not None and standard_deviation is not None and len(values) >= 6
        else None
    )
    upper_control_limit = (
        mean + 3 * standard_deviation
        if mean is not None and standard_deviation is not None and len(values) >= 6
        else None
    )

    points: list[InspectionTrendPoint] = []
    alerts: list[InspectionTrendAlert] = []
    for row, value in normalized_rows:
        assert value is not None
        (
            lower_specification_limit,
            upper_specification_limit,
        ) = _parse_specification_limits(row.specification)
        alert_type: str | None = None
        if (
            lower_specification_limit is not None
            and value < lower_specification_limit
        ) or (
            upper_specification_limit is not None
            and value > upper_specification_limit
        ):
            alert_type = "specification_limit"
        elif (
            lower_control_limit is not None
            and value < lower_control_limit
        ) or (
            upper_control_limit is not None
            and value > upper_control_limit
        ):
            alert_type = "control_limit"

        label = (
            _get_value(row, resource.batch_field)
            or _get_value(row, "inspection_no")
            or str(row.id)
        )
        point = InspectionTrendPoint(
            record_id=row.id,
            label=label,
            subject=_get_value(row, resource.subject_field),
            inspection_date=row.inspection_date,
            value=value,
            specification=row.specification,
            lower_specification_limit=lower_specification_limit,
            upper_specification_limit=upper_specification_limit,
            is_alert=alert_type is not None,
        )
        points.append(point)
        if alert_type:
            message = (
                "检验结果超出标准限度"
                if alert_type == "specification_limit"
                else "检验结果超出统计控制限"
            )
            alerts.append(
                InspectionTrendAlert(
                    record_id=row.id,
                    label=label,
                    subject=point.subject,
                    actual_value=value,
                    alert_type=alert_type,
                    message=message,
                )
            )

    return InspectionTrendResponse(
        resource_code=resource.code,
        resource_name=resource.label,
        subject=subject.strip() if subject and subject.strip() else None,
        inspection_item=(inspection_item or "").strip() or None,
        points=points,
        alerts=alerts,
        summary=InspectionTrendSummary(
            sample_count=len(points),
            mean=mean,
            standard_deviation=standard_deviation,
            lower_control_limit=lower_control_limit,
            upper_control_limit=upper_control_limit,
            alert_count=len(alerts),
        ),
    )
