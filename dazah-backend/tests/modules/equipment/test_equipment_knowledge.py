"""维修知识案例（草稿/确认/三层检索）与月度报告测试。"""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.equipment.models import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    FailureAction,
    FailureCause,
    FailureSymptom,
    Location,
    RepairKnowledgeCase,
)
from app.modules.equipment.schemas import WorkOrderCreate
from app.modules.equipment.service import (
    create_work_order,
    dismiss_case,
    list_cases,
    mark_case_used,
    search_similar_cases,
    verify_case,
)
from app.modules.equipment.service.knowledge import (
    create_case_draft,
    similarity_score,
)
from app.platform.identity.models import User


def _uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


@pytest.fixture
async def knowledge_user(db_session: AsyncSession) -> User:
    user = User(name="知识库测试用户", employee_no=f"EMP-K-{_uuid_hex()}")
    db_session.add(user)
    await db_session.flush()
    return user


async def _setup_equipment(
    db_session: AsyncSession, no: str, category_code: str = "PUMP"
) -> tuple[Equipment, EquipmentCategory]:
    category = (
        (
            await db_session.execute(
                select(EquipmentCategory).where(
                    EquipmentCategory.code == category_code
                )
            )
        )
        .scalars()
        .first()
    )
    if category is None:
        category = EquipmentCategory(name="泵类", code=category_code)
        db_session.add(category)
        await db_session.flush()
    location = Location(name="一楼泵房", code=f"LC-{no}")
    db_session.add(location)
    await db_session.flush()
    eq = Equipment(
        equipment_no=no,
        name=f"离心泵-{no}",
        location_id=location.id,
        status="在用",
        workshop_code="201-1",
    )
    db_session.add(eq)
    await db_session.flush()
    db_session.add(
        EquipmentCategoryLink(equipment_id=eq.id, category_id=category.id)
    )
    await db_session.flush()
    return eq, category



async def _verified_case(
    db_session: AsyncSession,
    eq: Equipment | None,
    category: EquipmentCategory | None,
    *,
    symptom: str = "LEAK",
    description: str = "密封处泄漏",
    action: str = "更换机械密封",
) -> RepairKnowledgeCase:
    case = RepairKnowledgeCase(
        equipment_id=eq.id if eq else None,
        equipment_category_id=category.id if category else None,
        symptom_code=symptom,
        symptom_name="泄漏",
        cause_code="SEAL-AGING",
        cause_name="密封老化",
        action_code="REPLACE-SEAL",
        action_name=action,
        fault_description=description,
        repair_summary=action,
        status="verified",
        equipment_name=eq.name if eq else None,
        equipment_no=eq.equipment_no if eq else None,
    )
    db_session.add(case)
    await db_session.flush()
    return case


# ==================== 相似度与检索 ====================


def test_similarity_score_identical_and_disjoint() -> None:
    assert similarity_score("密封泄漏", "密封泄漏") == 1.0
    assert similarity_score("密封泄漏", "电机过热") == 0.0
    mid = similarity_score("密封处泄漏严重", "密封泄漏")
    assert 0.0 < mid < 1.0


async def test_search_layers_equipment_first(
    db_session: AsyncSession,
) -> None:
    """三层检索：本设备案例排在同分类与全局案例之前。"""
    eq_a, cat = await _setup_equipment(db_session, "EQ-K-0001")
    eq_b, _ = await _setup_equipment(db_session, "EQ-K-0002")
    _, cat_other = await _setup_equipment(
        db_session, "EQ-K-0003", category_code="MOTOR"
    )

    same_equipment = await _verified_case(
        db_session, eq_a, cat, description="密封处泄漏"
    )
    same_category = await _verified_case(
        db_session, eq_b, cat, description="密封处泄漏"
    )
    global_case = await _verified_case(
        db_session, None, cat_other, description="密封处泄漏"
    )
    assert same_equipment.id != same_category.id != global_case.id

    hits = await search_similar_cases(
        db_session, query="密封处泄漏", equipment_id=eq_a.id, top=3
    )
    assert len(hits) == 3
    assert hits[0]["id"] == same_equipment.id
    assert hits[1]["id"] == same_category.id
    assert hits[2]["id"] == global_case.id


async def test_search_symptom_code_bonus(db_session: AsyncSession) -> None:
    eq, cat = await _setup_equipment(db_session, "EQ-K-0010")
    hit = await _verified_case(
        db_session, eq, cat, description="密封处泄漏"
    )
    hits = await search_similar_cases(
        db_session,
        query="完全无关的描述",
        equipment_id=eq.id,
        symptom_code="LEAK",
        top=3,
    )
    assert hits and hits[0]["id"] == hit.id


async def test_search_empty_returns_empty(db_session: AsyncSession) -> None:
    hits = await search_similar_cases(db_session, query="不存在的故障")
    assert hits == []


# ==================== 草稿生成与确认流转 ====================


async def test_draft_created_on_fault_order(
    db_session: AsyncSession, knowledge_user: User
) -> None:
    """故障维修工单生成草稿；非故障工单不生成。"""
    eq, _ = await _setup_equipment(db_session, "EQ-K-0020")
    symptom = FailureSymptom(code="VIB", name="振动")
    cause = FailureCause(code="ALIGN", name="对中不良")
    action = FailureAction(code="REALIGN", name="重新对中")
    db_session.add_all([symptom, cause, action])
    await db_session.flush()

    wo = await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=eq.id, order_type="故障维修", priority="中"
        ),
        reporter_id=knowledge_user.id,
    )
    wo.fault_symptom_id = symptom.id
    wo.fault_cause_id = cause.id
    wo.fault_action_id = action.id
    wo.repair_detail = "重新对中并紧固地脚螺栓"
    await db_session.flush()

    case = await create_case_draft(db_session, wo)
    assert case is not None
    assert case.status == "draft"
    assert case.symptom_code == "VIB"
    assert case.cause_code == "ALIGN"
    assert case.action_code == "REALIGN"
    assert case.equipment_category_id is not None

    # 同一工单幂等：不重复生成
    again = await create_case_draft(db_session, wo)
    assert again is None

    # 非故障维修不生成（换一台在用设备，避开同设备开放工单占用限制）
    eq2, _ = await _setup_equipment(db_session, "EQ-K-0020-B")
    wo2 = await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=eq2.id, order_type="计划维护", priority="低"
        ),
        reporter_id=knowledge_user.id,
    )
    assert await create_case_draft(db_session, wo2) is None


async def test_draft_duplicate_verified_skipped(
    db_session: AsyncSession, knowledge_user: User
) -> None:
    """同设备同现象同原因已入库 → 不再生成草稿。"""
    eq, cat = await _setup_equipment(db_session, "EQ-K-0021")
    existing = await _verified_case(db_session, eq, cat)
    existing.equipment_id = eq.id
    await db_session.flush()

    symptom = FailureSymptom(code="LEAK", name="泄漏")
    cause = FailureCause(code="SEAL-AGING", name="密封老化")
    db_session.add_all([symptom, cause])
    await db_session.flush()

    wo = await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=eq.id, order_type="故障维修", priority="中"
        ),
        reporter_id=knowledge_user.id,
    )
    wo.fault_symptom_id = symptom.id
    wo.fault_cause_id = cause.id
    await db_session.flush()

    assert await create_case_draft(db_session, wo) is None


async def test_verify_and_dismiss_transitions(
    db_session: AsyncSession, knowledge_user: User
) -> None:
    eq, cat = await _setup_equipment(db_session, "EQ-K-0022")
    existing = await _verified_case(db_session, eq, cat)
    existing.status = "draft"
    await db_session.flush()

    verified = await verify_case(db_session, existing.id, knowledge_user.id)
    assert verified.status == "verified"
    assert verified.verified_by == knowledge_user.id

    # 已入库再确认 → 业务异常
    with pytest.raises(AppException):
        await verify_case(db_session, existing.id, knowledge_user.id)

    # 重新置草稿后忽略
    verified.status = "draft"
    await db_session.flush()
    dismissed = await dismiss_case(db_session, verified.id, knowledge_user.id)
    assert dismissed.status == "dismissed"
    with pytest.raises(AppException):
        await dismiss_case(db_session, dismissed.id, knowledge_user.id)


async def test_list_cases_and_use_count(
    db_session: AsyncSession,
) -> None:
    eq, cat = await _setup_equipment(db_session, "EQ-K-0023")
    case = await _verified_case(db_session, eq, cat)

    cases, total = await list_cases(db_session, status="verified")
    assert total >= 1
    assert any(c.id == case.id for c in cases)

    await mark_case_used(db_session, case.id)
    assert case.use_count == 1


# ==================== 月度报告 ====================


async def test_monthly_report_fallback_without_llm(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 失败时报告仍生成（模板回落文本）。"""
    from types import SimpleNamespace as _NS

    from app.core.llm import LLMError
    from app.modules.equipment.service import (
        generate_monthly_report,
        get_monthly_report,
    )

    class _FailChat:
        async def chat(self, *a: object, **k: object) -> str:
            raise LLMError("no llm config")

    # 不触碰 llm 单例（anyio 测试间 teardown 交错会跨模块泄漏）
    monkeypatch.setattr("app.core.llm.llm_client", _NS(chat=_FailChat().chat))

    month = f"{datetime.now(UTC).year}-01"
    report = await generate_monthly_report(db_session, month)
    assert report.report_month == month
    assert report.content_md is not None
    assert "总体情况" in report.content_md
    assert report.metrics["month"] == month

    fetched = await get_monthly_report(db_session, month)
    assert fetched.id == report.id

    # 幂等：重生成覆盖同一行
    again = await generate_monthly_report(db_session, month)
    assert again.id == report.id


async def test_monthly_report_llm_narrative(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace as _NS

    from app.modules.equipment.service import generate_monthly_report

    async def _ok_chat(*args: object, **kwargs: object) -> str:
        return "## 总体情况\n\n本月运行平稳。"

    monkeypatch.setattr("app.core.llm.llm_client", _NS(chat=_ok_chat))

    month = f"{datetime.now(UTC).year}-02"
    report = await generate_monthly_report(db_session, month)
    assert "本月运行平稳" in (report.content_md or "")


def test_previous_month_rollover() -> None:
    from app.modules.equipment.service.monthly_report import previous_month

    assert previous_month(date(2026, 11, 1)) == "2026-10"
    assert previous_month(date(2026, 1, 15)) == "2025-12"


async def test_monthly_aggregate_no_lazy_load(
    db_session: AsyncSession, knowledge_user: User
) -> None:
    """回归：月度聚合访问工单关系不得触发异步懒加载。

    事故背景：调度器任务在新会话加载工单后访问 o.equipment，
    未显式 selectinload 时抛 MissingGreenlet 导致任务反复失败。
    expire_all 模拟调度器的新会话状态。
    """
    eq, _ = await _setup_equipment(db_session, "EQ-K-0030")
    eq_name = eq.name
    wo = await create_work_order(
        db_session,
        WorkOrderCreate(
            equipment_id=eq.id, order_type="故障维修", priority="中"
        ),
        reporter_id=knowledge_user.id,
    )
    assert wo.work_order_no
    await db_session.flush()
    db_session.expire_all()

    from app.modules.equipment.service.monthly_report import (
        aggregate_monthly_metrics,
    )

    month = datetime.now(UTC).strftime("%Y-%m")
    metrics = await aggregate_monthly_metrics(db_session, month)
    assert metrics["fault_orders"] >= 1
    assert any(
        item["name"] == eq_name for item in metrics["top_fault_equipment"]
    )
