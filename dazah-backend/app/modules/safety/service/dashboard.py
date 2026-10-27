"""总览驾驶舱聚合：厂区平面图当日风险落点、超储物料与近 7 日统计。

地点归一：自由文本地点/部门 → 建筑底册（CampusBuilding.aliases
精确/最长包含匹配），匹配不上的进入 unmapped 分组。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    Accident,
    CampusBuilding,
    ChemicalInventory,
    DailyRiskReport,
    HazardousChemical,
    HazardReport,
    SpecialOperationReport,
)
from app.modules.safety.schemas.dashboard import (
    CampusBuildingItem,
    MapBuildingMarkers,
    MapRiskItem,
    OverLimitChemicalItem,
    SafetyOverviewResponse,
    UnmappedRiskGroup,
    WeeklyOperationTypeCount,
)
from app.modules.safety.service.hazchem import inventory_over_limit

CN_TZ = timezone(timedelta(hours=8))

_OPERATION_TYPE_LABELS: dict[str, str] = {
    "hot_work": "动火作业",
    "confined_space": "受限空间",
    "blind_plate": "盲板抽堵",
    "height_work": "高处作业",
    "lifting": "吊装作业",
    "temporary_electricity": "临时用电",
    "excavation": "动土作业",
    "road_breaking": "断路作业",
}


def shanghai_today_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    local_now = now.astimezone(CN_TZ)
    start = datetime.combine(local_now.date(), time.min, tzinfo=CN_TZ)
    end = start + timedelta(days=1)
    return start, end


def build_alias_map(
    buildings: list[CampusBuilding],
) -> tuple[dict[str, CampusBuilding], list[str]]:
    """别名 → 建筑；同别名命中多个建筑时丢弃并在 ambiguous 中返回。"""
    alias_targets: dict[str, set[int]] = defaultdict(set)
    for building in buildings:
        keys = {building.name}
        for alias in building.aliases or []:
            if isinstance(alias, str) and alias.strip():
                keys.add(alias.strip())
        for key in keys:
            alias_targets[key].add(id(building))
    ambiguous = {key for key, ids in alias_targets.items() if len(ids) > 1}
    alias_map: dict[str, CampusBuilding] = {}
    for building in buildings:
        keys = {building.name}
        for alias in building.aliases or []:
            if isinstance(alias, str) and alias.strip():
                keys.add(alias.strip())
        for key in keys:
            if key not in ambiguous:
                alias_map[key] = building
    return alias_map, sorted(ambiguous)


def match_building(
    text: str | None,
    alias_map: dict[str, CampusBuilding],
    *,
    exact_only: bool = False,
) -> CampusBuilding | None:
    """地点文本 → 建筑。exact_only 用于部门兜底：部门名只有精确命中
    （如「聚合二部」）才落点，避免「201三车间」这类部门被子串吸附到
    错误建筑。"""
    if not text:
        return None
    value = text.strip()
    if not value:
        return None
    direct = alias_map.get(value)
    if direct is not None:
        return direct
    if exact_only:
        return None
    best: tuple[int, CampusBuilding] | None = None
    for alias, building in alias_map.items():
        if len(alias) >= 2 and alias in value:
            if best is None or len(alias) > best[0]:
                best = (len(alias), building)
    return best[1] if best else None


def match_department_building(
    text: str | None, alias_map: dict[str, CampusBuilding]
) -> CampusBuilding | None:
    """部门兜底：仅接受精确命中或以已知建筑名/别名为前缀的部门
    （如「201二车间MC」→ 201二车间），杜绝「201三车间」被子串误吸附。"""
    value = (text or "").strip()
    if not value:
        return None
    direct = alias_map.get(value)
    if direct is not None:
        return direct
    best: tuple[int, CampusBuilding] | None = None
    for alias, building in alias_map.items():
        if len(alias) >= 3 and value.startswith(alias):
            if best is None or len(alias) > best[0]:
                best = (len(alias), building)
    return best[1] if best else None


def _truncate(value: str | None, limit: int = 40) -> str:
    value = (value or "").strip()
    return value[:limit] + "…" if len(value) > limit else value


class SafetyOverviewService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_overview(self) -> SafetyOverviewResponse:
        buildings = (
            (
                await self.db.execute(
                    select(CampusBuilding)
                    .where(CampusBuilding.is_deleted.is_(False))
                    .order_by(CampusBuilding.sort_order.asc(), CampusBuilding.id.asc())
                )
            )
            .scalars()
            .all()
        )
        alias_map, _ambiguous = build_alias_map(list(buildings))
        building_items = [
            CampusBuildingItem(
                id=b.id,
                code=b.code,
                name=b.name,
                category=b.category,
                x_pct=b.x_pct,
                y_pct=b.y_pct,
            )
            for b in buildings
        ]

        day_start, day_end = shanghai_today_range()
        week_ago = day_start - timedelta(days=7)

        items: list[MapRiskItem] = []

        # 当日特殊作业报备（驾驶舱口径：驳回/草稿未实际发生，不计入当日分布）
        special_rows = (
            await self.db.execute(
                select(SpecialOperationReport).where(
                    SpecialOperationReport.is_deleted.is_(False),
                    SpecialOperationReport.status.notin_(["draft", "rejected"]),
                    SpecialOperationReport.planned_start_time >= day_start,
                    SpecialOperationReport.planned_start_time < day_end,
                )
            )
        ).scalars()
        for report in special_rows:
            items.append(
                MapRiskItem(
                    source="special_op",
                    title=_truncate(report.work_description or report.report_no),
                    location_text=report.location or "",
                    department=report.department or "",
                    risk_level=report.risk_level or "",
                    operation_type=report.operation_type or "",
                    happened_at=report.planned_start_time,
                    detail_url="/safety/special-ops",
                )
            )

        # 当日风险作业报备（同样排除驳回/草稿）
        daily_rows = (
            await self.db.execute(
                select(DailyRiskReport).where(
                    DailyRiskReport.is_deleted.is_(False),
                    DailyRiskReport.status.notin_(["draft", "rejected"]),
                    DailyRiskReport.report_date >= day_start,
                    DailyRiskReport.report_date < day_end,
                )
            )
        ).scalars()
        for daily in daily_rows:
            items.append(
                MapRiskItem(
                    source="daily_risk",
                    title=_truncate(daily.operation_description or daily.report_no),
                    location_text=daily.location or "",
                    department=daily.department or "",
                    risk_level=daily.risk_level or "",
                    happened_at=daily.report_date,
                    detail_url="/safety/risk-reporting",
                )
            )

        # 近 24h 事故（展示当日 0 点起）
        accident_rows = (
            await self.db.execute(
                select(Accident).where(
                    Accident.is_deleted.is_(False),
                    Accident.happened_at >= day_start,
                )
            )
        ).scalars()
        for accident in accident_rows:
            items.append(
                MapRiskItem(
                    source="accident",
                    title=_truncate(accident.description or accident.accident_no),
                    location_text=accident.location or "",
                    department=accident.department or "",
                    risk_level=accident.accident_level or "",
                    happened_at=accident.happened_at,
                    detail_url="/safety/accident",
                )
            )

        # 未关闭隐患（按部门兜底映射，无 location 字段）
        hazard_rows = (
            await self.db.execute(
                select(HazardReport).where(
                    HazardReport.is_deleted.is_(False),
                    or_(
                        HazardReport.status.is_(None),
                        HazardReport.status.notin_(["closed", "verified"]),
                    ),
                )
            )
        ).scalars()
        for hazard in hazard_rows:
            items.append(
                MapRiskItem(
                    source="hazard",
                    title=_truncate(hazard.description or hazard.hazard_no),
                    location_text=hazard.department or "",
                    department=hazard.department or "",
                    risk_level=hazard.hazard_level or "",
                    detail_url="/safety/hazard",
                )
            )

        # 归一落点：先按地点文本匹配，失败时按部门兜底（标记 matched_by）
        markers_by_building: dict[UUID, MapBuildingMarkers] = {}
        unmapped: dict[str, list[MapRiskItem]] = defaultdict(list)
        for item in items:
            building = match_building(item.location_text, alias_map)
            if building is not None:
                item.matched_by = "location"
            else:
                # 部门兜底仅接受精确/前缀命中，杜绝「201三车间」被子串误吸附
                building = match_department_building(item.department, alias_map)
                if building is not None:
                    item.matched_by = "department"
            if building is None:
                key = item.location_text or item.department or "未填写地点"
                unmapped[key].append(item)
                continue
            marker = markers_by_building.get(building.id)
            if marker is None:
                marker = MapBuildingMarkers(
                    building_id=building.id,
                    name=building.name,
                    x_pct=building.x_pct,
                    y_pct=building.y_pct,
                    total=0,
                )
                markers_by_building[building.id] = marker
            marker.total += 1
            if item.risk_level:
                marker.levels[item.risk_level] = (
                    marker.levels.get(item.risk_level, 0) + 1
                )
            marker.items.append(item)

        # 近 7 日作业类型统计
        type_rows = (
            await self.db.execute(
                select(SpecialOperationReport.operation_type).where(
                    SpecialOperationReport.is_deleted.is_(False),
                    SpecialOperationReport.planned_start_time >= week_ago,
                )
            )
        ).scalars()
        type_counts: dict[str, int] = defaultdict(int)
        for operation_type in type_rows:
            type_counts[operation_type or ""] += 1
        weekly = sorted(
            (
                WeeklyOperationTypeCount(operation_type=key, total=total)
                for key, total in type_counts.items()
            ),
            key=lambda row: -row.total,
        )

        # 超储物料 Top
        over_rows = (
            await self.db.execute(
                select(ChemicalInventory, HazardousChemical)
                .join(
                    HazardousChemical,
                    HazardousChemical.id == ChemicalInventory.chemical_id,
                )
                .where(
                    ChemicalInventory.is_deleted.is_(False),
                    HazardousChemical.is_deleted.is_(False),
                    ChemicalInventory.upper_limit.is_not(None),
                    ChemicalInventory.quantity > ChemicalInventory.upper_limit,
                )
                .order_by(
                    (ChemicalInventory.quantity / ChemicalInventory.upper_limit).desc()
                )
                .limit(10)
            )
        ).all()
        over_limit = [
            OverLimitChemicalItem(
                inventory_id=inventory.id,
                chemical_name=chemical.name,
                workshop=inventory.workshop,
                quantity=float(inventory.quantity),
                upper_limit=float(inventory.upper_limit)
                if inventory.upper_limit
                else None,
                over_pct=(
                    round(
                        (float(inventory.quantity) - float(inventory.upper_limit))
                        / float(inventory.upper_limit)
                        * 100,
                        1,
                    )
                    if inventory_over_limit(
                        float(inventory.quantity), float(inventory.upper_limit)
                    )
                    and inventory.upper_limit
                    and float(inventory.upper_limit) > 0
                    else None
                ),
                unit=inventory.unit,
            )
            for inventory, chemical in over_rows
        ]

        open_hazard_count = sum(1 for item in items if item.source == "hazard")
        source_totals: dict[str, int] = {}
        for item in items:
            source_totals[item.source] = source_totals.get(item.source, 0) + 1

        return SafetyOverviewResponse(
            buildings=building_items,
            markers=sorted(markers_by_building.values(), key=lambda m: -m.total),
            unmapped=[
                UnmappedRiskGroup(
                    location_text=key,
                    total=len(group),
                    items=group,
                )
                for key, group in sorted(unmapped.items(), key=lambda kv: -len(kv[1]))
            ],
            over_limit_chemicals=over_limit,
            weekly_operation_types=weekly,
            source_totals=source_totals,
            open_hazard_count=open_hazard_count,
            generated_at=datetime.now(UTC),
        )
