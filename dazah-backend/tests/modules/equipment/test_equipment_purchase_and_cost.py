"""方案C：备件采购建议 + 维修成本核算 测试."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select as _sel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentPersonnel,
    EquipmentRole,
    Location,
    SparePart,
    SparePartPurchaseSuggestion,
    SparePartStock,
    WorkOrder,
)
from app.modules.equipment.schemas import (
    WorkOrderComplete,
    WorkOrderCreate,
)
from app.modules.equipment.service import (
    assign_work_order,
    calc_suggest_qty,
    cancel_suggestion,
    complete_work_order,
    create_labor_rate,
    create_work_order,
    get_cost_report,
    list_suggestions,
    register_arrival,
    resolve_hourly_rate,
    scan_and_suggest,
    start_work_order,
    submit_to_procurement,
    update_suggest_qty,
)
from app.platform.identity.models import User


def _hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


@pytest.fixture
async def c_user(db_session: AsyncSession) -> User:
    """方案C 服务层测试专用用户（须与被测数据同会话，满足外键）。"""
    user = User(name="方案C测试用户", employee_no=f"EMP-C-{_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


# ==================== 建议量计算 ====================


def test_calc_suggest_qty_rounds_to_min_order() -> None:
    assert calc_suggest_qty(10, 10, 1) == 0  # 已达安全线
    assert calc_suggest_qty(0, 5, 1) == 10  # 安全线×2 − 现库存
    assert calc_suggest_qty(3, 5, 4) == 8  # 向上取整到 4 的倍数
    assert calc_suggest_qty(9, 5, 6) == 0  # 已达安全线
    assert calc_suggest_qty(2, 5, 6) == 12  # 8 向上取整到 6 的倍数


# ==================== 扫描 / upsert / 取消 ====================


async def _make_part_with_stock(
    db: AsyncSession, current: int, safety: int, min_order: int = 1
) -> SparePart:
    part = SparePart(
        code=f"SP-{_hex()}",
        name="机械密封",
        workshop_code="201-1",
        unit="套",
        unit_price=150,
    )
    db.add(part)
    await db.flush()
    db.add(
        SparePartStock(
            spare_part_id=part.id,
            current_qty=current,
            safety_qty=safety,
            min_order_qty=min_order,
        )
    )
    await db.flush()
    return part


async def test_scan_creates_updates_and_cancels(db_session: AsyncSession) -> None:
    await _make_part_with_stock(db_session, current=2, safety=6)

    stats = await scan_and_suggest(db_session)
    assert stats["created"] == 1
    items, total = await list_suggestions(db_session, status="suggested")
    assert total == 1
    assert items[0]["suggest_qty"] == 10  # 6*2-2

    # 幂等：重跑不重复建
    stats2 = await scan_and_suggest(db_session)
    assert stats2["created"] == 0
    _, total2 = await list_suggestions(db_session, status="suggested")
    assert total2 == 1

    # 库存回升 → suggested 自动取消
    stock = (
        await db_session.execute(
            _sel(SparePartStock)
        )
    ).scalars().first()
    stock.current_qty = 10
    await db_session.flush()
    stats3 = await scan_and_suggest(db_session)
    assert stats3["cancelled"] == 1
    _, total3 = await list_suggestions(db_session, status="suggested")
    assert total3 == 0


async def test_update_qty_and_cancel_flow(
    db_session: AsyncSession, c_user: User
) -> None:
    await _make_part_with_stock(db_session, current=0, safety=5)
    await scan_and_suggest(db_session)
    sug = (
        (
            await db_session.execute(
                _sel(
                    SparePartPurchaseSuggestion
                )
            )
        )
        .scalars()
        .first()
    )

    updated = await update_suggest_qty(db_session, sug.id, 12)
    assert updated.suggest_qty == 12

    with pytest.raises(AppException):
        await update_suggest_qty(db_session, sug.id, 0)

    cancelled = await cancel_suggestion(db_session, sug.id, c_user.id)
    assert cancelled.status == "cancelled"
    with pytest.raises(AppException):
        await cancel_suggestion(db_session, sug.id, c_user.id)


# ==================== 提交采购（mock 采购契约） ====================


async def test_submit_to_procurement_marks_submitted(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    c_user: User,
) -> None:
    part = await _make_part_with_stock(db_session, current=1, safety=4)
    await scan_and_suggest(db_session)
    sug = (
        (
            await db_session.execute(
                _sel(
                    SparePartPurchaseSuggestion
                )
            )
        )
        .scalars()
        .first()
    )

    calls: list[dict] = []

    async def _fake_create(db, *, items, **kw):
        calls.append({"items": items})
        return {"request_id": "pr-123", "total_amount": 450.0, "status": "draft"}

    from app.modules.procurement import public_api as procurement_api

    monkeypatch.setattr(
        procurement_api, "create_equipment_purchase_request", _fake_create
    )

    result = await submit_to_procurement(db_session, [sug.id], c_user.id)
    assert result["submitted"] == 1
    assert result["purchase_request_id"] == "pr-123"
    assert calls[0]["items"][0]["material_code"] == part.code
    assert calls[0]["items"][0]["quantity"] == 7

    # 重复提交被拒
    result2 = await submit_to_procurement(db_session, [sug.id], c_user.id)
    assert result2["submitted"] == 0
    assert result2["failed"]


async def test_register_arrival_inbounds_and_completes(
    db_session: AsyncSession, c_user: User
) -> None:
    part = await _make_part_with_stock(db_session, current=0, safety=3)
    await scan_and_suggest(db_session)
    sug = (
        (
            await db_session.execute(
                _sel(
                    SparePartPurchaseSuggestion
                )
            )
        )
        .scalars()
        .first()
    )
    sug.status = "submitted"
    await db_session.flush()

    # 分批到货
    partial = await register_arrival(db_session, sug.id, 2, user_id=c_user.id)
    assert partial.status == "partial"
    assert partial.arrived_qty == 2
    stock = (
        (
            await db_session.execute(
                _sel(SparePartStock).where(
                    SparePartStock.spare_part_id == part.id
                )
            )
        )
        .scalars()
        .first()
    )
    assert int(stock.current_qty) == 2  # 已入库

    done = await register_arrival(db_session, sug.id, 4, user_id=c_user.id)
    assert done.status == "done"
    assert done.arrived_qty == 6


# ==================== 费率 / 工时成本 / 报表 ====================


async def _make_equipment(db: AsyncSession, no: str) -> Equipment:
    category = EquipmentCategory(name="泵类C", code=f"PC-{_hex()}")
    db.add(category)
    await db.flush()
    location = Location(name="泵房C", code=f"LC-{_hex()}")
    db.add(location)
    await db.flush()
    eq = Equipment(
        equipment_no=no, name=f"离心泵-{no}", location_id=location.id, status="在用"
    )
    db.add(eq)
    await db.flush()
    return eq


async def test_labor_rate_crud_and_resolution(
    db_session: AsyncSession, c_user: User
) -> None:
    # FK 校验需要用户在本会话内真实存在
    assignee = User(name="费率测试维修员", employee_no=f"EMP-RATE-{_hex()}")
    db_session.add(assignee)
    await db_session.flush()
    role = EquipmentRole(name="维修工C", code=f"MW-{_hex()}")
    db_session.add(role)
    await db_session.flush()

    role_rate = await create_labor_rate(
        db_session, scope="role", hourly_rate=50, role_id=role.id
    )
    assert role_rate.id is not None

    # 重复建被拒
    with pytest.raises(AppException):
        await create_labor_rate(
            db_session, scope="role", hourly_rate=60, role_id=role.id
        )

    # 人员费率优先于岗位费率
    person_rate = await create_labor_rate(
        db_session, scope="person", hourly_rate=80, person_id=assignee.id
    )
    assert await resolve_hourly_rate(db_session, assignee.id) == 80.0

    from app.modules.equipment.service import (
        delete_labor_rate as del_rate,
    )
    from app.modules.equipment.service import (
        update_labor_rate,
    )

    await del_rate(db_session, person_rate.id)
    # 无人员费率且未加入设备人员池 → 0
    assert await resolve_hourly_rate(db_session, assignee.id) == 0.0

    # 加入人员池并挂角色 → 取岗位费率
    personnel = EquipmentPersonnel(user_id=assignee.id, name=assignee.name)
    db_session.add(personnel)
    await db_session.flush()
    from app.modules.equipment.models import EquipmentPersonnelRole

    db_session.add(
        EquipmentPersonnelRole(personnel_id=personnel.id, role_id=role.id)
    )
    await db_session.flush()
    assert await resolve_hourly_rate(db_session, assignee.id) == 50.0

    updated = await update_labor_rate(
        db_session, role_rate.id, hourly_rate=66
    )
    assert float(updated.hourly_rate) == 66.0
    assert await resolve_hourly_rate(db_session, assignee.id) == 66.0


async def test_complete_work_order_applies_labor_cost(
    db_session: AsyncSession, c_user: User
) -> None:
    assignee = User(name="工时测试维修员", employee_no=f"EMP-LC-{_hex()}")
    db_session.add(assignee)
    await db_session.flush()
    await create_labor_rate(
        db_session, scope="person", hourly_rate=60, person_id=assignee.id
    )
    eq = await _make_equipment(db_session, f"EQ-C-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="日常维护"),
        reporter_id=c_user.id,
    )
    await assign_work_order(db_session, wo.id, assignee.id)
    await start_work_order(db_session, wo.id)
    # 拉长维修时长：把开始时间回拨 2 小时
    wo.started_at = datetime.now(UTC) - timedelta(hours=2)
    await db_session.flush()

    completed = await complete_work_order(
        db_session,
        wo.id,
        WorkOrderComplete(repair_detail="例行保养"),
    )
    assert completed.actual_duration is not None
    assert completed.labor_cost is not None
    expected = round(completed.actual_duration / 60 * 60, 2)
    assert float(completed.labor_cost) == pytest.approx(expected, rel=0.05)


async def test_cost_report_grouping(
    db_session: AsyncSession, c_user: User
) -> None:
    eq = await _make_equipment(db_session, f"EQ-CR-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=c_user.id,
    )
    wo.spare_parts_cost = 100
    wo.labor_cost = 40
    wo.external_cost = 60
    wo.external_vendor = "外协厂"
    await db_session.flush()

    month = datetime.now(UTC).strftime("%Y-%m")
    report = await get_cost_report(db_session, month=month, group_by="equipment")
    assert report["totals"]["orders"] >= 1
    assert report["totals"]["spare_cost"] >= 100
    assert report["totals"]["labor_cost"] >= 40
    assert report["totals"]["external_cost"] >= 60
    top_labels = [t["label"] for t in report["top"]]
    assert any(eq.name in label for label in top_labels)

    # 车间过滤：不匹配车间 → 空
    other = await get_cost_report(
        db_session, workshop_code="999-9", month=month
    )
    assert other["totals"]["orders"] == 0

    # 非法分组 → 业务异常
    with pytest.raises(AppException):
        await get_cost_report(db_session, group_by="invalid")


# ==================== API 集成 ====================


async def test_purchase_suggestion_api_flow(
    client: AsyncClient,
    _equipment_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    part = SparePart(
        code=f"SP-API-{_hex()}",
        name="API测试备件",
        workshop_code="201-1",
        unit="个",
        unit_price=20,
    )
    _equipment_session.add(part)
    await _equipment_session.flush()
    _equipment_session.add(
        SparePartStock(
            spare_part_id=part.id, current_qty=0, safety_qty=5, min_order_qty=1
        )
    )
    await _equipment_session.flush()

    # 扫描
    resp = await client.post(
        "/api/v1/equipment/spare-parts/purchase-suggestions/scan"
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["created"] == 1

    # 列表
    resp_list = await client.get(
        "/api/v1/equipment/spare-parts/purchase-suggestions",
        params={"status": "suggested"},
    )
    assert resp_list.status_code == 200
    items = resp_list.json()["data"]
    assert items and items[0]["spare_part_code"] == part.code
    sid = items[0]["id"]

    # 调整数量（非法值 → 422）
    resp_bad = await client.put(
        f"/api/v1/equipment/spare-parts/purchase-suggestions/{sid}/qty",
        json={"suggest_qty": 0},
    )
    assert resp_bad.status_code == 422

    # 提交（mock 采购契约）
    from app.modules.procurement import public_api as procurement_api

    async def _fake_create(db, *, items, **kw):
        return {"request_id": "pr-api-1", "total_amount": 200.0, "status": "draft"}

    monkeypatch.setattr(
        procurement_api, "create_equipment_purchase_request", _fake_create
    )
    resp_submit = await client.post(
        "/api/v1/equipment/spare-parts/purchase-suggestions/submit",
        json={"suggestion_ids": [sid]},
    )
    assert resp_submit.status_code == 200
    body = resp_submit.json()["data"]
    assert body["submitted"] == 1
    assert body["purchase_request_id"] == "pr-api-1"

    # 到货
    resp_arrival = await client.post(
        f"/api/v1/equipment/spare-parts/purchase-suggestions/{sid}/arrival",
        json={"arrived_qty": 10},
    )
    assert resp_arrival.status_code == 200
    assert resp_arrival.json()["data"]["status"] == "done"


async def test_cost_api_flow(
    client: AsyncClient,
    _equipment_session: AsyncSession,
    test_assignee: User,
) -> None:
    # 费率 CRUD
    resp_create = await client.post(
        "/api/v1/equipment/spare-parts/purchase-suggestions/labor-rates",
        json={
            "scope": "person",
            "person_id": str(test_assignee.id),
            "hourly_rate": 55,
        },
    )
    assert resp_create.status_code == 200
    rate_id = resp_create.json()["data"]["id"]

    resp_list = await client.get(
        "/api/v1/equipment/spare-parts/purchase-suggestions/labor-rates"
    )
    assert any(r["id"] == rate_id for r in resp_list.json()["data"])

    resp_update = await client.put(
        f"/api/v1/equipment/spare-parts/purchase-suggestions/labor-rates/{rate_id}",
        json={"hourly_rate": 60},
    )
    assert resp_update.status_code == 200

    # 成本报表（月份非法 → 422）
    resp_report = await client.get(
        "/api/v1/equipment/maintenance/work-orders/cost-report"
    )
    assert resp_report.status_code == 200
    assert "totals" in resp_report.json()["data"]
    resp_bad = await client.get(
        "/api/v1/equipment/maintenance/work-orders/cost-report",
        params={"month": "2026-1"},
    )
    assert resp_bad.status_code == 422


async def test_consume_materials_decimal_price_regression(
    db_session: AsyncSession, c_user: User
) -> None:
    """回归：备件单价为 Decimal（Numeric 列真实类型）时领料不再 500。

    事故：存量实现 float += Decimal*Decimal 抛 TypeError，接口 500；
    真实数据库单测此前用 float mock 未暴露。
    """
    from decimal import Decimal

    from app.modules.equipment.service import consume_materials

    part = SparePart(
        code=f"SP-DEC-{_hex()}",
        name="Decimal单价备件",
        workshop_code="201-1",
        unit="个",
        unit_price=Decimal("12.50"),  # 模拟真实 Numeric 列返回的 Decimal
    )
    db_session.add(part)
    await db_session.flush()
    db_session.add(
        SparePartStock(spare_part_id=part.id, current_qty=10, safety_qty=2)
    )
    await db_session.flush()

    eq = await _make_equipment(db_session, f"EQ-DEC-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=c_user.id,
    )

    txs = await consume_materials(
        db_session,
        wo.id,
        [
            {
                "spare_part_id": part.id,
                "quantity": 2,
            }
        ],
    )
    assert len(txs) == 1
    wo_cost = (
        await db_session.execute(
            _sel(WorkOrder).where(WorkOrder.id == wo.id)
        )
    ).scalars().one()
    assert float(wo_cost.spare_parts_cost) == 25.0  # 12.50 × 2
