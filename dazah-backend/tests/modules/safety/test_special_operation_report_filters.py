"""特殊作业报备日期筛选与统计口径回归（独立测试库）。

日期筛选此前把 YYYY-MM-DD 字符串直接与 timestamptz 列比较（VARCHAR 绑定
报错），且结束侧 ``<= 当天`` 会漏掉当天内带时刻的计划结束时间。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.safety.models import SpecialOperationReport
from app.modules.safety.repository import SafetyRepository


async def _add(
    db,
    report_no: str,
    start: datetime,
    end: datetime | None = None,
    *,
    level: str = "grade2",
    critical: bool = False,
    risk_level: str | None = None,
    department: str | None = None,
) -> None:
    db.add(
        SpecialOperationReport(
            report_no=report_no,
            operation_type="hot_work",
            operation_level=level,
            planned_start_time=start,
            planned_end_time=end or start,
            status="approved",
            is_critical=critical,
            risk_level=risk_level,
            department=department,
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_date_filter_covers_full_day(db_session) -> None:
    """date_from/date_to=同一天时，当天 0 点与带时刻的记录都命中，次日不命中。"""
    repo = SafetyRepository(db_session)
    day = datetime(2026, 10, 14, tzinfo=UTC)
    await _add(db_session, "T-FULL-1", day)
    await _add(
        db_session,
        "T-FULL-2",
        day + timedelta(hours=8),
        day + timedelta(hours=17),
    )
    await _add(db_session, "T-FULL-3", day + timedelta(days=1))

    items, total = await repo.get_special_operation_reports(
        0, 10, date_from="2026-10-14", date_to="2026-10-14"
    )

    assert total == 2
    assert {item.report_no for item in items} == {"T-FULL-1", "T-FULL-2"}


@pytest.mark.asyncio
async def test_ledger_stats_share_filter_scope(db_session) -> None:
    """统计与列表共用筛选口径：日期与作业级别过滤都生效。"""
    repo = SafetyRepository(db_session)
    day = datetime(2026, 10, 14, tzinfo=UTC)
    await _add(db_session, "T-STAT-1", day, critical=True)
    await _add(db_session, "T-STAT-2", day, level="grade1")
    await _add(db_session, "T-STAT-3", day + timedelta(days=5))

    stats = await repo.get_special_operation_ledger_stats(
        date_from="2026-10-14", date_to="2026-10-14"
    )
    hot = next(s for s in stats if s["operation_type"] == "hot_work")
    assert hot["count"] == 2
    assert hot["critical_count"] == 1

    grade1_only = await repo.get_special_operation_ledger_stats(
        operation_level="grade1"
    )
    hot_g1 = next(s for s in grade1_only if s["operation_type"] == "hot_work")
    assert hot_g1["count"] == 1


@pytest.mark.anyio
async def test_filters_cover_remaining_dimensions(db_session) -> None:
    """risk_level/department/is_critical/keyword/date_from 单独过滤各覆盖一遍。"""
    repo = SafetyRepository(db_session)
    day = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)

    await _add(db_session, "T-DIM-1", day, level="grade1", risk_level="high")
    await _add(db_session, "T-DIM-2", day, department="机修车间")
    await _add(db_session, "T-DIM-3", day, critical=True)
    await _add(db_session, "T-DIM-4", day)
    await db_session.flush()

    # risk_level
    items, _ = await repo.get_special_operation_reports(0, 10, risk_level="high")
    assert {item.report_no for item in items} == {"T-DIM-1"}
    # department
    items, _ = await repo.get_special_operation_reports(0, 10, department="机修车间")
    assert {item.report_no for item in items} == {"T-DIM-2"}
    # is_critical
    items, total = await repo.get_special_operation_reports(0, 10, is_critical=True)
    assert {item.report_no for item in items} == {"T-DIM-3"}
    assert total == 1
    # keyword（编号模糊）
    items, _ = await repo.get_special_operation_reports(0, 10, keyword="T-DIM-4")
    assert {item.report_no for item in items} == {"T-DIM-4"}
    # 仅 date_from：含当天及以后
    items, _ = await repo.get_special_operation_reports(0, 10, date_from="2026-10-14")
    assert {"T-DIM-1", "T-DIM-2", "T-DIM-3", "T-DIM-4"} <= {
        item.report_no for item in items
    }


@pytest.mark.anyio
async def test_ledger_filters_cover_all_dimensions(db_session) -> None:
    """台账列表（get_special_operation_ledger）的各过滤维度。"""
    repo = SafetyRepository(db_session)
    day = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)

    await _add(db_session, "T-LED-1", day, level="grade1", risk_level="high",
               department="设备部")
    await _add(db_session, "T-LED-2", day, critical=True)
    await db_session.flush()

    items, total = await repo.get_special_operation_ledger(
        0, 10, risk_level="high", department="设备部",
        date_from="2026-10-14", date_to="2026-10-14",
    )
    assert {item.report_no for item in items} == {"T-LED-1"}
    assert total == 1

    items, total = await repo.get_special_operation_ledger(
        0, 10, operation_type="hot_work", operation_level="grade2",
        is_critical=True, keyword="T-LED-2",
    )
    assert {item.report_no for item in items} == {"T-LED-2"}
    assert total == 1
