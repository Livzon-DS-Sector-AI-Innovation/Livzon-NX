"""总览驾驶舱聚合服务测试（真实服务 + 独立测试库）。

覆盖：建筑别名匹配（精确/包含/歧义丢弃）、当日风险落点归一、
未映射分组、超储物料 Top 与近 7 日作业类型统计。
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    CampusBuilding,
    ChemicalInventory,
    DailyRiskReport,
    HazardousChemical,
    SpecialOperationReport,
)
from app.modules.safety.schemas.hazchem import (
    ChemicalInventoryCreate,
    HazardousChemicalCreate,
)
from app.modules.safety.service.dashboard import (
    SafetyOverviewService,
    build_alias_map,
    match_building,
    shanghai_today_range,
)
from app.modules.safety.service.hazchem import HazchemService


@pytest.fixture(autouse=True)
async def _cleanup_overview(db_session: AsyncSession) -> AsyncIterator[None]:
    yield
    await db_session.execute(
        delete(ChemicalInventory).where(
            ChemicalInventory.chemical_id.in_(
                select(HazardousChemical.id).where(
                    HazardousChemical.name.like("测试驾驶舱化学品-%")
                )
            )
        )
    )
    await db_session.execute(
        delete(HazardousChemical).where(
            HazardousChemical.name.like("测试驾驶舱化学品-%")
        )
    )
    await db_session.execute(
        delete(DailyRiskReport).where(DailyRiskReport.report_no.like("TEST-OV-%"))
    )
    await db_session.execute(
        delete(SpecialOperationReport).where(
            SpecialOperationReport.report_no.like("TEST-OV-%")
        )
    )
    await db_session.execute(
        delete(CampusBuilding).where(CampusBuilding.name.like("测试建筑-%"))
    )
    await db_session.commit()


def _make_building(
    name: str, aliases: list[str], x: float = 10.0, y: float = 20.0
) -> CampusBuilding:
    return CampusBuilding(
        id=uuid4(),
        code="",
        name=name,
        category="workshop",
        x_pct=x,
        y_pct=y,
        aliases=aliases,
    )


def test_alias_map_and_matching() -> None:
    b1 = _make_building("测试建筑-101车间", ["101一车间", "101"])
    b2 = _make_building("测试建筑-锅炉房东", ["锅炉房东"], 50.0, 50.0)
    b3 = _make_building("测试建筑-锅炉房西", ["锅炉房西"], 60.0, 50.0)
    alias_map, ambiguous = build_alias_map([b1, b2, b3])

    # 名称重复时精确别名仍然唯一可用
    assert "锅炉房东" not in ambiguous and "锅炉房西" not in ambiguous

    assert match_building("101一车间", alias_map) is b1
    assert match_building("101一车间二楼东侧", alias_map) is b1  # 包含匹配
    assert match_building("测试建筑-101车间", alias_map) is b1  # 名称精确
    assert match_building("锅炉房东墙边", alias_map) is b2
    assert match_building("完全未知地点", alias_map) is None
    assert match_building("", alias_map) is None
    assert match_building(None, alias_map) is None

    # 同名歧义：两个建筑注册同一别名 → 别名被丢弃
    dup1 = _make_building("测试建筑-车间甲", ["共同别名"])
    dup2 = _make_building("测试建筑-车间乙", ["共同别名"])
    dup_map, dup_ambiguous = build_alias_map([dup1, dup2])
    assert "共同别名" in dup_ambiguous
    assert match_building("共同别名", dup_map) is None


def test_shanghai_today_range_is_eight_hour_window() -> None:
    start, end = shanghai_today_range(datetime(2026, 10, 27, 2, 0, tzinfo=UTC))
    assert (end - start).total_seconds() == 86400
    assert start.utcoffset().total_seconds() == 8 * 3600
    # 北京 10-27 10:00 = UTC 02:00，北京当日零点 = UTC 10-26 16:00
    assert start.hour == 0 and start.day == 27
    start_utc = start.astimezone(UTC)
    assert start_utc.hour == 16 and start_utc.day == 26


async def test_overview_aggregates_markers_and_over_limit(
    db_session: AsyncSession,
) -> None:
    building = CampusBuilding(
        id=uuid4(),
        code="T01",
        name="测试建筑-聚合车间",
        category="workshop",
        x_pct=30.0,
        y_pct=40.0,
        aliases=["聚合车间"],
    )
    dept_building = CampusBuilding(
        id=uuid4(),
        code="T02",
        name="测试建筑-聚合二部",
        category="workshop",
        x_pct=50.0,
        y_pct=40.0,
        aliases=["聚合二部"],
    )
    db_session.add(building)
    db_session.add(dept_building)

    day_start, _ = shanghai_today_range()
    db_session.add(
        SpecialOperationReport(
            report_no="TEST-OV-SP-1",
            operation_type="hot_work",
            operation_level="grade1",
            department="提炼四部",
            location="聚合车间二楼",
            risk_level="level_2",
            work_description="动火作业测试",
            planned_start_time=day_start + timedelta(hours=4),
            status="approved",
        )
    )
    db_session.add(
        DailyRiskReport(
            report_no="TEST-OV-DR-1",
            report_date=day_start + timedelta(hours=6),
            department="提炼四部",
            location="完全陌生地点",
            risk_level="level_3",
            operation_description="常规巡查报备",
            status="submitted",
        )
    )
    db_session.add(
        SpecialOperationReport(
            report_no="TEST-OV-SP-2",
            operation_type="confined_space",
            operation_level="grade2",
            department="提炼五部",
            location="污水站",
            risk_level="level_1",
            work_description="上周的受限空间作业",
            planned_start_time=day_start - timedelta(days=6),
            status="approved",
        )
    )
    # 地点无法匹配但部门可兜底 → 按部门落点
    db_session.add(
        SpecialOperationReport(
            report_no="TEST-OV-SP-3",
            operation_type="hot_work",
            operation_level="grade2",
            department="聚合二部",
            location="一部四楼",
            risk_level="level_3",
            work_description="部门兜底落点作业",
            planned_start_time=day_start + timedelta(hours=9),
            status="submitted",
        )
    )
    # 驳回的报备未实际发生，不计入当日分布
    db_session.add(
        SpecialOperationReport(
            report_no="TEST-OV-SP-4",
            operation_type="hot_work",
            operation_level="grade2",
            department="聚合二部",
            location="聚合车间",
            risk_level="level_2",
            work_description="被驳回的动火作业",
            planned_start_time=day_start + timedelta(hours=10),
            status="rejected",
        )
    )
    await db_session.flush()
    hazchem = HazchemService(db_session)
    chemical = await hazchem.create_chemical(
        HazardousChemicalCreate(
            name="测试驾驶舱化学品-乙醇", category="flammable_liquid"
        )
    )
    await hazchem.create_inventory(
        ChemicalInventoryCreate(
            chemical_id=chemical.id,
            workshop="测试建筑-聚合车间",
            quantity=4.6,
            upper_limit=3.0,
        )
    )
    await db_session.commit()

    overview = await SafetyOverviewService(db_session).get_overview()

    building_item = next(b for b in overview.buildings if b.name == "测试建筑-聚合车间")
    assert building_item.code == "T01"

    marker = next(m for m in overview.markers if m.building_id == building_item.id)
    assert marker.total == 1  # 驳回的 SP-4 不计入，仅当日报备落点
    item = marker.items[0]
    assert item.source == "special_op"
    assert item.title == "动火作业测试"
    assert item.risk_level == "level_2"
    assert item.matched_by == "location"

    # 部门兜底：地点「一部四楼」匹配失败，部门「聚合二部」命中
    dept_item = next(b for b in overview.buildings if b.name == "测试建筑-聚合二部")
    dept_marker = next(m for m in overview.markers if m.building_id == dept_item.id)
    assert dept_marker.total == 1
    assert dept_marker.items[0].title == "部门兜底落点作业"
    assert dept_marker.items[0].matched_by == "department"

    # 来源总数与 落点+未映射 保持一致（测试库含真实当日数据，只验证自洽性）
    assert overview.source_totals.get("special_op", 0) >= 2
    assert overview.source_totals.get("daily_risk", 0) >= 1
    mapped_total = sum(m.total for m in overview.markers)
    unmapped_total = sum(g.total for g in overview.unmapped)
    assert mapped_total + unmapped_total == sum(overview.source_totals.values())

    unmapped_group = next(
        (g for g in overview.unmapped if g.location_text == "完全陌生地点"), None
    )
    assert unmapped_group is not None
    assert unmapped_group.total == 1
    assert unmapped_group.items[0].source == "daily_risk"

    # 近 7 日统计至少包含本测试的两条 hot_work 与 6 天前的受限空间
    type_totals = {
        row.operation_type: row.total for row in overview.weekly_operation_types
    }
    assert type_totals.get("hot_work", 0) >= 2
    assert type_totals.get("confined_space", 0) >= 1

    assert any(
        chem.chemical_name == "测试驾驶舱化学品-乙醇" and chem.over_pct is not None
        for chem in overview.over_limit_chemicals
    )

    assert overview.open_hazard_count >= 0
    assert overview.generated_at is not None
