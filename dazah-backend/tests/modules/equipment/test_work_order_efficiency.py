"""维修效能统计测试：聚合口径、车间过滤、达标率与 TOP 排序。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.work_order import WorkOrder
from app.modules.equipment.service.work_order_efficiency import (
    get_efficiency_statistics,
)

_PAST = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def _hide_foreign_work_orders(db_session: AsyncSession):
    """事务内屏蔽其他测试残留的工单：本地持久测试库非空时断言仍稳。

    delete 发生在回滚事务里，不会真正删除库中数据。
    """
    await db_session.execute(delete(WorkOrder))
    await db_session.flush()
    yield


def _minutes_ago(base: datetime, m: int) -> tuple[datetime, datetime]:
    reported = base
    assigned = base + timedelta(minutes=m)
    return reported, assigned


async def _seed(db: AsyncSession) -> dict[str, Equipment]:
    from app.modules.equipment.models.equipment import Location
    from app.platform.identity.models import User

    location = Location(name="测试位置", code="TEST-LOC")
    db.add(location)
    await db.flush()

    users: dict[str, User] = {}
    for key, name in [("u1", "张三"), ("u2", "李四")]:
        u = User(
            username=f"u_{uuid.uuid4().hex[:6]}",
            name=name,
            feishu_union_id=f"on_{key}",
        )
        db.add(u)
        users[key] = u
    await db.flush()

    eqs: dict[str, Equipment] = {}
    for key, name, no, ws in [
        ("a", "离心泵A", "LB-001", "201-1"),
        ("b", "薄膜蒸发器4", "XT-1", "201-1"),
        ("c", "反应釜C", "FT-1", "101-1"),
    ]:
        eq = Equipment(
            name=name,
            equipment_no=no,
            workshop_code=ws,
            status="在用",
            location_id=location.id,
        )
        db.add(eq)
        eqs[key] = eq
    await db.flush()

    def wo(eq_key: str, *, resp_min: int | None, repair: int, priority="高",
           status="已完成", reported=_PAST, assignee=None) -> None:
        e = eqs[eq_key]
        if resp_min is None:
            reported_at, assigned_at = reported, None
        else:
            reported_at, assigned_at = _minutes_ago(reported, resp_min)
        db.add(
            WorkOrder(
                work_order_no=f"WO-{uuid.uuid4().hex[:8]}",
                equipment_id=e.id,
                order_type="故障维修",
                priority=priority,
                status=status,
                fault_description="测试",
                reported_at=reported_at,
                assigned_at=assigned_at,
                assignee_id=assignee.id if assignee else None,
                started_at=assigned_at,
                completed_at=(
                    assigned_at + timedelta(minutes=repair)
                    if assigned_at is not None
                    else None
                ),
                actual_duration=repair if assigned_at is not None else None,
                original_equipment_status="在用",
            )
        )

    # A：3 单（紧急 3 分钟响应、紧急 8 分钟、高 10 分钟）→ 达标 1/2
    wo("a", resp_min=3, repair=40, priority="紧急", assignee=users["u1"])
    wo("a", resp_min=8, repair=60, priority="紧急", assignee=users["u1"])
    wo("a", resp_min=10, repair=50, priority="高", assignee=users["u1"])
    # B：1 单高（未接单）
    wo("b", resp_min=None, repair=100, priority="高", status="待处理")
    # C（101-1 车间）：1 单，用于车间过滤验证
    wo("c", resp_min=2, repair=30, priority="高", assignee=users["u2"])
    await db.flush()
    return eqs


@pytest.mark.asyncio
async def test_efficiency_aggregates_and_top_faults(db_session) -> None:
    """全车间：响应/MTTR 均值（已接单口径）、紧急达标 1/2、TOP1=离心泵A。"""
    await _seed(db_session)
    stats = await get_efficiency_statistics(db_session, None, months=6)

    # 已接单 4 单（A3+C1，B 未接单不计）：响应 (3+8+10+2)/4 = 5.75；
    # MTTR (40+60+50+30)/4 = 45
    assert stats["total_orders"] == 4
    assert stats["avg_response_minutes"] == 5.8
    assert stats["avg_repair_minutes"] == 45.0
    # 紧急 2 单，仅 3 分钟那单 ≤5min → 0.5
    assert stats["urgent_total"] == 2
    assert stats["urgent_on_time"] == 1
    assert stats["urgent_5min_rate"] == 0.5
    # TOP：A 3 单居首，B/C 各 1
    top = stats["top_faults"]
    assert top[0]["equipment_name"] == "离心泵A"
    assert top[0]["order_count"] == 3
    assert {t["equipment_name"] for t in top} == {
        "离心泵A", "薄膜蒸发器4", "反应釜C",
    }
    # 趋势月包含 2026-06
    assert any(m["month"] == "2026-06" for m in stats["monthly"])


@pytest.mark.asyncio
async def test_efficiency_repairer_ranking(db_session) -> None:
    """排行按接单数降序，取真实姓名；未接单单不进排行。"""
    await _seed(db_session)
    stats = await get_efficiency_statistics(db_session, None, months=6)

    ranking = stats["repairer_ranking"]
    assert [(r["assignee_name"], r["order_count"]) for r in ranking] == [
        ("张三", 3),
        ("李四", 1),
    ]
    assert ranking[0]["avg_response_minutes"] == 7.0  # (3+8+10)/3
    assert ranking[0]["avg_repair_minutes"] == 50.0  # (40+60+50)/3


@pytest.mark.asyncio
async def test_efficiency_response_buckets_sum_to_total(db_session) -> None:
    """五档固定顺序输出，含未接单档；五档之和=全部工单数。"""
    await _seed(db_session)
    stats = await get_efficiency_statistics(db_session, None, months=6)

    buckets = stats["response_buckets"]
    assert [b["bucket"] for b in buckets] == [
        "≤5分钟", "5-30分钟", "30-120分钟", ">120分钟", "未接单",
    ]
    by_bucket = {b["bucket"]: b["count"] for b in buckets}
    # 3/8/10/2 分钟 + 1 未接单 → ≤5:2（3,2）、5-30:2（8,10）、未接单:1
    assert by_bucket["≤5分钟"] == 2
    assert by_bucket["5-30分钟"] == 2
    assert by_bucket["30-120分钟"] == 0
    assert by_bucket[">120分钟"] == 0
    assert by_bucket["未接单"] == 1
    assert sum(by_bucket.values()) == 5  # 全部工单（含未接单）


@pytest.mark.asyncio
async def test_efficiency_filters_by_workshop(db_session) -> None:
    """仅 201-1：反应釜C（101-1）不出现。"""
    await _seed(db_session)
    stats = await get_efficiency_statistics(db_session, "201-1", months=6)

    assert stats["total_orders"] == 3  # 已接单：A 3 单（B 未接单不计）
    names = {t["equipment_name"] for t in stats["top_faults"]}
    assert "反应釜C" not in names
    # 排行只剩张三；分档未接单只含 B 单
    assert [r["assignee_name"] for r in stats["repairer_ranking"]] == ["张三"]
    by_bucket = {b["bucket"]: b["count"] for b in stats["response_buckets"]}
    assert by_bucket["未接单"] == 1


@pytest.mark.asyncio
async def test_efficiency_empty_returns_zero_state(db_session) -> None:
    """无工单：全 0、达标率 None、趋势/TOP/排行/分档为空或零。"""
    stats = await get_efficiency_statistics(db_session, None, months=6)

    assert stats["total_orders"] == 0
    assert stats["avg_response_minutes"] == 0.0
    assert stats["avg_repair_minutes"] == 0.0
    assert stats["urgent_5min_rate"] is None
    assert stats["monthly"] == []
    assert stats["top_faults"] == []
    assert stats["repairer_ranking"] == []
    assert [b["count"] for b in stats["response_buckets"]] == [0, 0, 0, 0, 0]
