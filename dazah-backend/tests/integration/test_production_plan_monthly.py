"""生产计划月度筛选与汇总集成测试（真实 PostgreSQL）。

覆盖口径：日期落在哪个自然月即哪个月的计划；
汇总按单位分组（KG 与批分开统计），完成率 = Σ实际 ÷ Σ计划。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.production.api import _parse_month_range
from app.modules.production.models import ProductionPlan
from app.modules.production.service import ProductionService


async def _seed_plans(session) -> None:
    session.add_all(
        [
            ProductionPlan(
                workshop="203车间",
                product_name="L-苯丙氨酸",
                plan_date=date(2026, 7, 1),
                unit="KG",
                planned_yield=800000,
                actual_completion=92400,
                row_order=1,
                source="feishu",
            ),
            ProductionPlan(
                workshop="201-2车间",
                product_name="霉酚酸",
                plan_date=date(2026, 7, 15),
                unit="KG",
                planned_yield=61000,
                actual_completion=6920,
                row_order=2,
                source="feishu",
            ),
            ProductionPlan(
                workshop="101-2发酵车间",
                product_name="霉酚酸",
                plan_date=date(2026, 7, 1),
                unit="批",
                planned_yield=30,
                actual_completion=7,
                row_order=3,
                source="feishu",
            ),
            ProductionPlan(
                workshop="201-1车间",
                product_name="洛伐他汀",
                plan_date=date(2026, 6, 30),
                unit="KG",
                planned_yield=44280,
                actual_completion=0,
                row_order=4,
                source="feishu",
            ),
            ProductionPlan(
                workshop="菌种中心",
                product_name="供种/接种/培养基",
                plan_date=date(2026, 7, 1),
                unit=None,
                planned_yield=None,
                actual_completion=None,
                row_order=5,
                source="feishu",
            ),
        ]
    )
    await session.flush()


async def test_get_plans_filters_by_calendar_month(db_session) -> None:
    await _seed_plans(db_session)
    service = ProductionService(db_session)

    plans, total = await service.get_plans(
        0,
        20,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
    )

    # 7 月 4 条（含无产量的菌种中心类目行）；6 月那条不计入
    assert total == 4
    assert all(p.plan_date is not None and p.plan_date.month == 7 for p in plans)


async def test_monthly_summary_groups_by_unit(db_session) -> None:
    await _seed_plans(db_session)
    service = ProductionService(db_session)

    summary = await service.get_plan_monthly_summary(
        date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )

    by_unit = {item["unit"]: item for item in summary}
    kg = by_unit["KG"]
    assert kg["planned_yield"] == pytest.approx(861000)
    assert kg["actual_completion"] == pytest.approx(99320)
    assert kg["completion_rate"] == pytest.approx(0.1154)
    batch = by_unit["批"]
    assert batch["planned_yield"] == 30
    assert batch["actual_completion"] == 7
    assert batch["completion_rate"] == pytest.approx(0.2333)
    # KG 在前、批在后；无单位且无产量的类目行（菌种中心）不进汇总
    assert [item["unit"] for item in summary] == ["KG", "批"]


def test_parse_month_range_variants() -> None:
    assert _parse_month_range("2026-07") == (date(2026, 7, 1), date(2026, 7, 31))
    assert _parse_month_range("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert _parse_month_range("2026-13") is None
    assert _parse_month_range("202607") is None
    assert _parse_month_range("bad") is None
