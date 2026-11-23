"""方案B/C 服务层深分支：健康评分/预警/病历、知识库后台任务、费率与成本、
采购建议流转、月报边界、工单通知兜底与公共契约."""

import uuid as uuid_mod
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    EquipmentHealthSnapshot,
    EquipmentMonthlyReport,
    EquipmentRole,
    Location,
    RepairKnowledgeCase,
    RepairProfile,
    SparePart,
    SparePartPurchaseSuggestion,
    SparePartStock,
    WorkOrder,
)
from app.modules.equipment.models.maintenance_config import MaintenanceConfig
from app.modules.equipment.schemas import (
    WorkOrderComplete,
    WorkOrderCreate,
    WorkOrderVerify,
)
from app.modules.equipment.service import (
    assign_work_order,
    complete_work_order,
    create_work_order,
    start_work_order,
    transfer_work_order,
    verify_work_order,
)
from app.platform.identity.models import User


def _hex() -> str:
    return uuid_mod.uuid4().hex[:8]


@pytest.fixture
async def s_user(db_session: AsyncSession) -> User:
    user = User(name="分支用户", employee_no=f"EMP-S-{_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_equipment(
    db: AsyncSession, no: str, workshop: str = "201-1"
) -> Equipment:
    category = EquipmentCategory(name="泵类S", code=f"PS-{_hex()}")
    db.add(category)
    await db.flush()
    location = Location(name="泵房S", code=f"LS-{_hex()}")
    db.add(location)
    await db.flush()
    eq = Equipment(
        equipment_no=no,
        name=f"反应釜S-{no}",
        location_id=location.id,
        status="在用",
        workshop_code=workshop,
    )
    db.add(eq)
    await db.flush()
    db.add(
        EquipmentCategoryLink(equipment_id=eq.id, category_id=category.id)
    )
    await db.flush()
    return eq


# ==================== 健康评分（纯函数）与权重配置 ====================


def test_score_penalty_tiers_and_weight_override() -> None:
    from app.modules.equipment.service.health import (
        HealthMetrics,
        compute_health_score,
    )

    perfect = compute_health_score(HealthMetrics())
    assert perfect.score == 100.0 and perfect.grade == "G"

    mttr_tiers = [
        (None, 0.0),
        (30, 0.0),
        (120, 30.0),
        (300, 60.0),
        (600, 100.0),
    ]
    for mttr, penalty in mttr_tiers:
        result = compute_health_score(HealthMetrics(mttr_min_90d=mttr))
        assert result.metrics.penalties["mttr"] == penalty, mttr

    repeat = compute_health_score(HealthMetrics(max_repeat_fault_90d=5))
    assert repeat.metrics.penalties["repeat"] == 75.0

    heavy = compute_health_score(
        HealthMetrics(
            fault_count_90d=5,
            mttr_min_90d=600,
            overdue_maintenance_count=2,
            overdue_calibration_count=1,
            max_repeat_fault_90d=4,
        )
    )
    assert heavy.grade == "R"
    assert heavy.score == 10.0  # 100 - (35+20+25+5+5)

    # 权重覆盖：只保留故障维度 → 其他罚分不影响
    only_fault = compute_health_score(
        HealthMetrics(mttr_min_90d=600, overdue_maintenance_count=3),
        weights={"fault": 1.0, "mttr": 0.0, "maintenance": 0.0},
    )
    assert only_fault.score == 100.0
    # 未知权重键被忽略
    assert compute_health_score(
        HealthMetrics(), weights={"nonexistent": 5.0}
    ).score == 100.0


async def test_get_score_weights_config_paths(
    db_session: AsyncSession,
) -> None:
    from app.modules.equipment.service.health import (
        DEFAULT_WEIGHTS,
        get_score_weights,
    )

    assert await get_score_weights(db_session) == DEFAULT_WEIGHTS

    async def _with_value(value: str):
        await db_session.execute(
            MaintenanceConfig.__table__.delete().where(
                MaintenanceConfig.config_key == "health_score_weights"
            )
        )
        db_session.add(
            MaintenanceConfig(
                config_key="health_score_weights", config_value=value
            )
        )
        await db_session.flush()

    await _with_value("not-json")
    assert await get_score_weights(db_session) == DEFAULT_WEIGHTS

    await _with_value('["array"]')
    assert await get_score_weights(db_session) == DEFAULT_WEIGHTS

    await _with_value('{"fault": 0.5, "mttr": "bad", "unknown": 1}')
    weights = await get_score_weights(db_session)
    assert weights["fault"] == 0.5
    # 非数值键被过滤，不回填默认（由调用方与默认权重合并）
    assert "mttr" not in weights


# ==================== 快照幂等与预警 ====================


async def test_snapshot_rerun_updates_existing_rows(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.service.health import generate_daily_snapshots

    eq = await _make_equipment(db_session, f"EQ-S1-{_hex()}")
    day = date(2026, 10, 15)
    first = await generate_daily_snapshots(db_session, snapshot_date=day)
    assert first["total"] >= 1
    second = await generate_daily_snapshots(db_session, snapshot_date=day)
    assert second["total"] == first["total"]

    rows = (
        (
            await db_session.execute(
                select(EquipmentHealthSnapshot).where(
                    EquipmentHealthSnapshot.equipment_id == eq.id,
                    EquipmentHealthSnapshot.snapshot_date == day,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1  # 同日重跑覆盖，不重复


async def test_health_alerts_jump_and_streak(
    db_session: AsyncSession,
) -> None:
    from app.modules.equipment.service.health import (
        HealthMetrics,
        _run_health_alerts,  # noqa: SLF001
        compute_health_score,
    )

    eq = await _make_equipment(db_session, f"EQ-S2-{_hex()}")
    result = compute_health_score(
        HealthMetrics(
            fault_count_90d=5, mttr_min_90d=600, overdue_maintenance_count=2
        )
    )
    assert result.grade == "R"
    today = date(2026, 10, 20)

    # 昨日绿档 → 今日红档：跳变告警（后台通知由 conftest 统一禁用）
    db_session.add(
        EquipmentHealthSnapshot(
            equipment_id=eq.id,
            snapshot_date=today - timedelta(days=1),
            score=95,
            grade="G",
        )
    )
    await db_session.flush()
    alerts = await _run_health_alerts(db_session, today, [(eq, result)])
    assert alerts == 1

    # 昨日+前日均红：连续红档告警（换一台设备避免同日快照冲突）
    eq2 = await _make_equipment(db_session, f"EQ-S2B-{_hex()}")
    for i in (1, 2):
        db_session.add(
            EquipmentHealthSnapshot(
                equipment_id=eq2.id,
                snapshot_date=today - timedelta(days=i),
                score=40,
                grade="R",
            )
        )
    await db_session.flush()
    alerts = await _run_health_alerts(db_session, today, [(eq2, result)])
    assert alerts == 1

    # 绿档设备不触发任何告警
    ok_eq = await _make_equipment(db_session, f"EQ-S3-{_hex()}")
    ok_score = compute_health_score(HealthMetrics())
    alerts = await _run_health_alerts(db_session, today, [(ok_eq, ok_score)])
    assert alerts == 0


async def test_repeat_fault_inspection_and_guards(
    db_session: AsyncSession, s_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.equipment.service.work_order as wo_mod
    from app.modules.equipment.service.health import (
        HealthMetrics,
        HealthScore,
        _create_repeat_fault_inspection,  # noqa: SLF001
        )

    eq = await _make_equipment(db_session, f"EQ-S4-{_hex()}")
    metrics = HealthMetrics(
        fault_count_90d=3, max_repeat_fault_90d=3, mttr_min_90d=600
    )
    result = HealthScore(
        score=10.0, grade="R", metrics=metrics
    )
    assert await _create_repeat_fault_inspection(db_session, eq, result)

    created = (
        (
            await db_session.execute(
                select(WorkOrder).where(
                    WorkOrder.equipment_id == eq.id,
                    WorkOrder.fault_description.like("【健康预警】%"),
                )
            )
        )
        .scalars()
        .first()
    )
    assert created is not None
    assert created.order_type == "日常维护"

    # 已有未关闭专项检查单 → 防重跳过
    assert not await _create_repeat_fault_inspection(db_session, eq, result)

    # 关闭已有单后：建单被业务规则拒绝 / 系统异常，均吞掉不外抛
    created.status = "已关闭"
    await db_session.flush()

    async def _reject(db, create, reporter_id):
        raise AppException(message="被拒绝")

    async def _boom(db, create, reporter_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(wo_mod, "create_work_order", _reject)
    assert await _create_repeat_fault_inspection(db_session, eq, result) is True

    monkeypatch.setattr(wo_mod, "create_work_order", _boom)
    assert await _create_repeat_fault_inspection(db_session, eq, result) is True


async def test_notify_grade_jump_paths(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.equipment.service.work_order_feishu as wof
    from app.modules.equipment.service.health import (
        HealthMetrics,
        _notify_grade_jump,  # noqa: SLF001
        compute_health_score,
    )

    eq = await _make_equipment(db_session, f"EQ-S5-{_hex()}")
    result = compute_health_score(HealthMetrics(fault_count_90d=4))

    sent: list[dict] = []

    async def _chat_none(code):
        return None

    async def _send_ok(chat_id, card):
        sent.append({"chat_id": chat_id, "card": card})

    import app.modules.equipment.feishu.repair_card as repair_card_mod

    monkeypatch.setattr(wof, "resolve_repair_chat_id", _chat_none)
    await _notify_grade_jump(eq, result)
    assert not sent

    async def _chat_ok(code):
        return "oc_123"

    monkeypatch.setattr(wof, "resolve_repair_chat_id", _chat_ok)
    monkeypatch.setattr(repair_card_mod, "send_card_to_chat", _send_ok)
    await _notify_grade_jump(eq, result)
    assert sent and "健康预警" in sent[0]["card"]["header"]["title"]["content"]

    async def _send_raises(chat_id, card):
        raise RuntimeError("down")

    monkeypatch.setattr(repair_card_mod, "send_card_to_chat", _send_raises)
    await _notify_grade_jump(eq, result)  # 异常被吞


async def test_repair_profile_paths(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.service.health import (
        get_repair_profile,
        refresh_repair_profile,
    )

    # 设备不存在
    with pytest.raises(AppException):
        await get_repair_profile(db_session, uuid_mod.uuid4())
    with pytest.raises(AppException):
        await refresh_repair_profile(db_session, uuid_mod.uuid4())

    eq = await _make_equipment(db_session, f"EQ-S6-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=eq.id, order_type="故障维修", priority="中"
        ),
        reporter_id=s_user.id,
    )
    wo.actual_duration = 90
    wo.spare_parts_cost = 120.5
    await db_session.flush()

    # 无落库档案 → 瞬态只读聚合
    transient = await get_repair_profile(db_session, eq.id)
    assert transient.id is None
    assert transient.total_faults == 1
    assert transient.total_downtime_min == 90
    assert transient.total_spare_cost == 120.5
    assert transient.mtbf_days is None or transient.mtbf_days >= 1

    # 落库档案优先返回
    saved = RepairProfile(equipment_id=eq.id, total_orders=9)
    db_session.add(saved)
    await db_session.flush()
    cached = await get_repair_profile(db_session, eq.id)
    assert cached.id == saved.id

    refreshed = await refresh_repair_profile(db_session, eq.id)
    assert refreshed.id == saved.id  # 幂等复用同一行
    assert refreshed.total_orders == 1


# ==================== 知识库后台任务 ====================


async def test_similarity_edge_inputs() -> None:
    from app.modules.equipment.service.knowledge import (
        _char_bigrams,  # noqa: SLF001
        similarity_score,
    )

    assert _char_bigrams("a") == {"a"}
    assert _char_bigrams("") == set()
    assert similarity_score("泄漏", "") == 0.0
    assert similarity_score("", "泄漏") == 0.0


class _KnowledgeDbCtx:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __getattr__(self, name):
        return getattr(self._db, name)

    async def commit(self):
        pass


async def _draft_case(db: AsyncSession, eq: Equipment) -> RepairKnowledgeCase:
    case = RepairKnowledgeCase(
        equipment_id=eq.id,
        fault_description="电机异响",
        repair_summary="更换轴承并润滑",
        status="draft",
        equipment_name=eq.name,
        equipment_no=eq.equipment_no,
    )
    db.add(case)
    await db.flush()
    return case


async def test_extract_key_steps_branches(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.core.database as core_db
    from app.core.llm import LLMError
    from app.modules.equipment.service.knowledge import extract_key_steps

    monkeypatch.setattr(
        core_db,
        "async_session_factory",
        lambda: _KnowledgeDbCtx(db_session),
    )

    # 案例不存在 / 非 draft → 直接返回
    await extract_key_steps(uuid_mod.uuid4())
    eq = await _make_equipment(db_session, f"EQ-KB1-{_hex()}")
    verified = await _draft_case(db_session, eq)
    verified.status = "verified"
    await db_session.flush()
    await extract_key_steps(verified.id)

    # 空来源文本 → 返回
    empty = await _draft_case(db_session, eq)
    empty.repair_summary = None
    empty.fault_description = "  "
    await db_session.flush()
    await extract_key_steps(empty.id)

    steps_returned: list[object] = []

    async def _chat_ok(*args, **kwargs):
        steps_returned.append(True)
        return {"steps": ["断电挂牌", " 拆端盖 ", "", "更换轴承"]}

    monkeypatch.setattr(
        "app.core.llm.llm_client",
        SimpleNamespace(chat_json=_chat_ok),
    )
    draft = await _draft_case(db_session, eq)
    await extract_key_steps(draft.id)
    await db_session.flush()
    assert draft.key_steps == ["断电挂牌", "拆端盖", "更换轴承"]
    assert steps_returned

    async def _llm_error(*args, **kwargs):
        raise LLMError("no llm")

    monkeypatch.setattr(
        "app.core.llm.llm_client",
        SimpleNamespace(chat_json=_llm_error),
    )
    await extract_key_steps(draft.id)

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.core.llm.llm_client",
        SimpleNamespace(chat_json=_boom),
    )
    await extract_key_steps(draft.id)


async def test_send_case_confirm_card_paths(
    db_session: AsyncSession,
    s_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.database as core_db
    import app.modules.equipment.feishu.notification as notification_mod
    from app.modules.equipment.service.knowledge import (
        _send_case_confirm_card,  # noqa: SLF001
    )

    monkeypatch.setattr(
        core_db,
        "async_session_factory",
        lambda: _KnowledgeDbCtx(db_session),
    )
    sends: list[dict] = []

    async def _send(**kw):
        sends.append(kw)

    monkeypatch.setattr(notification_mod, "send_user_card", _send)

    # 案例不存在
    await _send_case_confirm_card(uuid_mod.uuid4())
    assert not sends

    # 维修人未绑定飞书 → 跳过发卡
    eq = await _make_equipment(db_session, f"EQ-KB2-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=s_user.id,
    )
    await assign_work_order(db_session, wo.id, s_user.id)
    case = await _draft_case(db_session, eq)
    case.source_work_order_id = wo.id
    await db_session.flush()
    await _send_case_confirm_card(case.id)
    assert not sends

    # 绑定飞书后发送确认卡
    s_user.feishu_union_id = f"on_{_hex()}"
    await db_session.flush()
    await _send_case_confirm_card(case.id)
    assert sends
    content = sends[-1].get("content") or ""
    assert wo.work_order_no in content or str(case.equipment_name) in content


# ==================== 费率与成本 ====================


async def test_labor_rate_crud_branches(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.service.cost import (
        create_labor_rate,
        delete_labor_rate,
        list_labor_rates,
        update_labor_rate,
    )

    # 校验分支
    with pytest.raises(AppException):
        await create_labor_rate(db_session, scope="bad", hourly_rate=10)
    with pytest.raises(AppException):
        await create_labor_rate(db_session, scope="role", hourly_rate=10)
    with pytest.raises(AppException):
        await create_labor_rate(
            db_session, scope="person", hourly_rate=10, role_id=uuid_mod.uuid4()
        )
    with pytest.raises(AppException):
        await create_labor_rate(
            db_session, scope="person", hourly_rate=-1, person_id=s_user.id
        )

    rate = await create_labor_rate(
        db_session, scope="person", hourly_rate=50, person_id=s_user.id
    )
    with pytest.raises(AppException):
        await create_labor_rate(  # 重复
            db_session, scope="person", hourly_rate=60, person_id=s_user.id
        )

    updated = await update_labor_rate(
        db_session,
        rate.id,
        hourly_rate=66,
        effective_from=date(2026, 1, 1),
        remark="调薪",
    )
    assert float(updated.hourly_rate) == 66
    with pytest.raises(AppException):
        await update_labor_rate(db_session, rate.id, hourly_rate=-5)
    with pytest.raises(AppException):
        await update_labor_rate(db_session, uuid_mod.uuid4(), hourly_rate=1)

    role = EquipmentRole(name="机修", code=f"R-{_hex()}")
    db_session.add(role)
    await db_session.flush()
    role_rate = await create_labor_rate(
        db_session, scope="role", hourly_rate=40, role_id=role.id
    )

    listed = await list_labor_rates(db_session)
    by_scope = {item["scope"]: item for item in listed}
    assert by_scope["person"]["hourly_rate"] == 66.0
    assert by_scope["role"]["role_id"] == role.id

    await delete_labor_rate(db_session, role_rate.id, operator_id=s_user.id)
    assert all(
        item["scope"] != "role" or item["role_id"] != str(role.id)
        for item in await list_labor_rates(db_session)
    )
    with pytest.raises(AppException):
        await delete_labor_rate(db_session, role_rate.id)


async def test_update_external_cost_branches(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.service.cost import update_external_cost

    with pytest.raises(AppException):
        await update_external_cost(db_session, uuid_mod.uuid4(), external_cost=1)

    eq = await _make_equipment(db_session, f"EQ-C1-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=s_user.id,
    )
    with pytest.raises(AppException):
        await update_external_cost(db_session, wo.id, external_cost=-3)

    updated = await update_external_cost(
        db_session,
        wo.id,
        external_cost=1500,
        external_vendor="外协厂A",
        operator_id=s_user.id,
    )
    assert float(updated.external_cost) == 1500
    assert updated.external_vendor == "外协厂A"

    cleared = await update_external_cost(
        db_session, wo.id, external_vendor=""
    )
    assert cleared.external_vendor is None
    assert float(cleared.external_cost) == 1500


async def test_cost_report_grouping_and_month_bounds(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.service.cost import get_cost_report

    with pytest.raises(AppException):
        await get_cost_report(db_session, month="2026-13")
    with pytest.raises(AppException):
        await get_cost_report(db_session, month="bad")

    eq = await _make_equipment(db_session, f"EQ-C2-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=s_user.id,
    )
    wo.spare_parts_cost = 100
    wo.labor_cost = 60
    wo.external_cost = 40
    await db_session.flush()

    by_equipment = await get_cost_report(db_session, month="2026-11")
    assert by_equipment["totals"]["orders"] >= 1
    assert by_equipment["group_by"] == "equipment"

    by_workshop = await get_cost_report(
        db_session, month="2026-11", group_by="workshop"
    )
    assert any(b["label"] == "201-1" for b in by_workshop["top"])

    by_fault = await get_cost_report(
        db_session, month="2026-11", group_by="fault_type"
    )
    assert any(b["label"] == "未分类" for b in by_fault["top"])

    with pytest.raises(AppException):
        await get_cost_report(db_session, group_by="unknown")

    # 12 月跨年边界
    december = await get_cost_report(db_session, month="2025-12")
    assert december["month"] == "2025-12"


# ==================== 采购建议流转 ====================


async def _part_with_suggestion(
    db: AsyncSession, *, status: str = "suggested"
) -> tuple[SparePart, SparePartPurchaseSuggestion]:
    part = SparePart(
        code=f"SP-S-{_hex()}",
        name=f"采购分支备件{_hex()}",
        workshop_code="201-1",
        unit="个",
        unit_price=12.5,
    )
    db.add(part)
    await db.flush()
    db.add(
        SparePartStock(spare_part_id=part.id, current_qty=0, safety_qty=5)
    )
    sug = SparePartPurchaseSuggestion(
        spare_part_id=part.id,
        current_qty=0,
        safety_qty=5,
        suggest_qty=10,
        status=status,
    )
    db.add(sug)
    await db.flush()
    return part, sug


async def test_submit_to_procurement_failure_branches(
    db_session: AsyncSession, s_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.procurement.public_api as procurement_api
    from app.modules.equipment.service.purchase_suggestion import (
        submit_to_procurement,
    )

    part, sug = await _part_with_suggestion(db_session)
    _, submitted_sug = await _part_with_suggestion(
        db_session, status="submitted"
    )

    async def _ok(db, items):
        return {"request_id": f"PR-{_hex()}"}

    monkeypatch.setattr(
        procurement_api, "create_equipment_purchase_request", _ok
    )

    # 不存在的建议 + 状态不允许（已提交的不可再提交）
    result = await submit_to_procurement(
        db_session, [uuid_mod.uuid4(), submitted_sug.id], s_user.id
    )
    assert result["submitted"] == 0
    reasons = {item["reason"] for item in result["failed"]}
    assert any("建议不存在" in r for r in reasons)
    assert any("仅待提交可提交" in r for r in reasons)

    # 采购契约抛业务异常 / 系统异常
    _, sug2 = await _part_with_suggestion(db_session)
    calls: list[str] = []

    async def _reject(db, items):
        calls.append("reject")
        raise AppException(message="预算冻结")

    monkeypatch.setattr(
        procurement_api, "create_equipment_purchase_request", _reject
    )
    result = await submit_to_procurement(db_session, [sug2.id], s_user.id)
    assert result["submitted"] == 0
    assert result["failed"][0]["reason"] == "预算冻结"

    async def _boom(db, items):
        raise RuntimeError("procurement down")

    monkeypatch.setattr(
        procurement_api, "create_equipment_purchase_request", _boom
    )
    _, sug3 = await _part_with_suggestion(db_session)
    result = await submit_to_procurement(db_session, [sug3.id], s_user.id)
    assert result["failed"][0]["reason"] == "采购模块调用失败"

    # 成功分支：状态推进 + 采购单号回填
    monkeypatch.setattr(
        procurement_api, "create_equipment_purchase_request", _ok
    )
    result = await submit_to_procurement(db_session, [sug.id], s_user.id)
    assert result["submitted"] == 1
    assert result["purchase_request_id"]
    assert sug.status == "submitted"
    assert sug.purchase_request_id


async def test_register_arrival_transitions(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.service.purchase_suggestion import (
        notify_low_stock_summary,
        register_arrival,
    )

    part, sug = await _part_with_suggestion(db_session)

    with pytest.raises(AppException):
        await register_arrival(db_session, sug.id, 0)
    with pytest.raises(AppException):
        await register_arrival(db_session, uuid_mod.uuid4(), 1)
    with pytest.raises(AppException):  # suggested 不可到货
        await register_arrival(db_session, sug.id, 1)

    sug.status = "submitted"
    await db_session.flush()
    partial = await register_arrival(
        db_session, sug.id, 4, user_id=s_user.id
    )
    assert partial.status == "partial"
    assert partial.arrived_qty == 4

    done = await register_arrival(db_session, sug.id, 6)
    assert done.status == "done"
    assert done.arrived_qty == 10

    stock = (
        (
            await db_session.execute(
                select(SparePartStock).where(
                    SparePartStock.spare_part_id == part.id
                )
            )
        )
        .scalars()
        .one()
    )
    assert stock.current_qty == 10

    # 汇总通知（有建议行 → 记日志分支）
    await _part_with_suggestion(db_session)
    await notify_low_stock_summary(db_session)


# ==================== 月报边界 ====================


async def test_monthly_report_boundaries(
    db_session: AsyncSession, s_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.equipment.service.monthly_report import (
        _month_bounds,  # noqa: SLF001
        generate_monthly_report,
        get_monthly_report,
        list_monthly_reports,
    )

    with pytest.raises(AppException):
        _month_bounds("not-a-month")
    with pytest.raises(AppException):
        _month_bounds("2026-13")
    assert _month_bounds("2025-12") == (date(2025, 12, 1), date(2026, 1, 1))

    async def _empty_chat(*args, **kwargs):
        return ""

    monkeypatch.setattr(
        "app.core.llm.llm_client", SimpleNamespace(chat=_empty_chat)
    )
    month = f"{datetime.now(UTC).year}-04"
    report = await generate_monthly_report(
        db_session, month, operator_id=s_user.id
    )
    assert report.created_by == s_user.id
    assert "总体情况" in report.content_md  # LLM 空返回回落模板

    fetched = await get_monthly_report(db_session, month)
    assert fetched.id == report.id
    with pytest.raises(AppException):
        await get_monthly_report(db_session, "2099-01")

    reports = await list_monthly_reports(db_session)
    assert len(reports) >= 1
    assert isinstance(reports[0], EquipmentMonthlyReport)


# ==================== 工单通知兜底与完成钩子 ====================


async def test_transfer_assignee_missing_rejected(
    db_session: AsyncSession, s_user: User
) -> None:
    eq = await _make_equipment(db_session, f"EQ-W1-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=s_user.id,
    )
    await assign_work_order(db_session, wo.id, s_user.id)
    with pytest.raises(AppException):
        await transfer_work_order(db_session, wo.id, uuid_mod.uuid4())


async def test_notify_transfer_guards(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.equipment.service.work_order as wo_mod

    # 双方都无飞书 ID → 静默返回
    await wo_mod._notify_transfer(  # noqa: SLF001
        old_union_id=None,
        new_union_id="",
        work_order_no="WO-X",
        equipment_name="设备",
        reason="",
    )

    import app.modules.equipment.feishu.notification as notification_mod

    async def _send_raises(**kw):
        raise RuntimeError("feishu down")

    monkeypatch.setattr(notification_mod, "send_user_card", _send_raises)
    await wo_mod._notify_transfer(  # noqa: SLF001 —— 发送失败仅记日志
        old_union_id="on_a",
        new_union_id="on_b",
        work_order_no="WO-Y",
        equipment_name="设备",
        reason="测试",
    )


async def test_complete_survives_cost_and_case_failures(
    db_session: AsyncSession, s_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    eq = await _make_equipment(db_session, f"EQ-W2-{_hex()}")
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(equipment_id=eq.id, order_type="故障维修"),
        reporter_id=s_user.id,
    )
    await assign_work_order(db_session, wo.id, s_user.id)
    await start_work_order(db_session, wo.id)

    import app.modules.equipment.service.cost as cost_mod
    import app.modules.equipment.service.knowledge as knowledge_mod

    async def _cost_boom(db, wo_arg):
        raise RuntimeError("cost boom")

    async def _draft_boom(db, wo_arg):
        raise RuntimeError("draft boom")

    monkeypatch.setattr(cost_mod, "apply_labor_cost", _cost_boom)
    monkeypatch.setattr(knowledge_mod, "create_case_draft", _draft_boom)

    completed = await complete_work_order(
        db_session, wo.id, WorkOrderComplete(repair_detail="修好了")
    )
    assert completed.status == "待验收"

    verified = await verify_work_order(
        db_session, wo.id, s_user.id, WorkOrderVerify(result="合格")
    )
    assert verified.verification_result == "合格"


# ==================== 公共契约：采购到货回写 ====================


async def test_public_arrival_contract(
    db_session: AsyncSession, s_user: User
) -> None:
    from app.modules.equipment.public_api import spare_part_purchase_arrived

    part, sug = await _part_with_suggestion(db_session, status="submitted")
    result = await spare_part_purchase_arrived(
        db_session,
        suggestion_id=sug.id,
        arrived_qty=10,
        operator_id=s_user.id,
    )
    assert result["suggestion_id"] == str(sug.id)
    assert result["arrived_qty"] == 10
    assert result["status"] == "done"
