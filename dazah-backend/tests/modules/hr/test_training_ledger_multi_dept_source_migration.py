"""培训台账多部门管理测试。

测试范围：
- create_record：授课部门一致（不再被篡改）、按 ledger_department 归属副本、
  多部门二级确认 pending
- delete_record：主办方（落款部门）删除 → 其他副本 owner_deleted；
  非主办方删除 → 不联动
- list_by_department：按 ledger_department 命中
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.hr.models import TrainingLedger
from app.modules.hr.schemas import TrainingLedgerCreate
from app.modules.hr.service import TrainingLedgerService


def _make_session() -> AsyncMock:
    """mock AsyncSession：查 Trainer 无结果（回退授课部门）、session.get 返回 None."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    session.get.return_value = None
    return session


def _make_service(
    session: AsyncMock,
) -> tuple[TrainingLedgerService, list[TrainingLedger]]:
    service = TrainingLedgerService(session)
    created: list[TrainingLedger] = []

    async def fake_create(record: TrainingLedger) -> TrainingLedger:
        record.id = uuid.uuid4()
        created.append(record)
        return record

    service.repo = MagicMock()
    service.repo.create = AsyncMock(side_effect=fake_create)
    return service, created


def _ledger_data(**overrides) -> TrainingLedgerCreate:
    base = dict(
        employee_number=None,
        training_date=date(2026, 8, 1),
        training_subject="GMP 培训",
        training_method="面授",
        teaching_dept="生产管理部",
        involved_depts="生产管理部、QA",
        trainees="张三、李四",
        session_id=uuid.uuid4(),
        ledger_department="生产管理部",
    )
    base.update(overrides)
    return TrainingLedgerCreate(**base)


# ── create_record：副本归属与授课部门一致 ─────────────────


@pytest.mark.asyncio
async def test_create_record_multi_dept_keeps_teaching_dept():
    """多部门培训：每涉及部门一条副本，授课部门全部一致（不被篡改），归属部门正确分配。"""
    service, created = _make_service(_make_session())
    data = _ledger_data(involved_depts="生产管理部、QA", ledger_department="生产管理部")

    await service.create_record(data)

    assert len(created) == 2
    depts = {r.ledger_department for r in created}
    assert depts == {"生产管理部", "QA"}
    # 授课部门在所有副本中一致，且 = 真实授课部门
    assert {r.teaching_dept for r in created} == {"生产管理部"}


@pytest.mark.asyncio
async def test_create_record_multi_dept_marks_pending():
    """多部门培训（涉及部门≥2）→ 所有副本 second_level_status='pending'。"""
    service, created = _make_service(_make_session())
    data = _ledger_data(involved_depts="生产管理部、QA", ledger_department="生产管理部")

    await service.create_record(data)

    assert all(r.second_level_status == "pending" for r in created)


@pytest.mark.asyncio
async def test_create_record_single_dept_no_pending():
    """单部门培训：不触发二级确认标记。"""
    service, created = _make_service(_make_session())
    data = _ledger_data(involved_depts="生产管理部", ledger_department="生产管理部")

    await service.create_record(data)

    assert len(created) == 1
    assert created[0].second_level_status is None


@pytest.mark.asyncio
async def test_create_record_frontend_pending_kept():
    """前端已判定多部门（如 201 MC/DR 拆分）传 pending → 单部门记录也保持 pending。"""
    service, created = _make_service(_make_session())
    data = _ledger_data(
        involved_depts="201二车间（MC）",
        ledger_department="201二车间（MC）",
        teaching_dept="201二车间",
        second_level_status="pending",
    )
    await service.create_record(data)

    assert len(created) == 1
    assert created[0].second_level_status == "pending"
    assert created[0].teaching_dept == "201二车间"


@pytest.mark.asyncio
async def test_create_record_no_session_no_split():
    """无 session（如 Excel 导入）：不按涉及部门拆分副本。"""
    service, created = _make_service(_make_session())
    data = _ledger_data(
        involved_depts="生产管理部、QA",
        ledger_department="生产管理部",
        session_id=None,
    )

    await service.create_record(data)

    assert len(created) == 1


# ── delete_record：主办方删除联动 ────────────────────────


def _make_delete_service(
    session_dept: str | None,
) -> tuple[TrainingLedgerService, AsyncMock]:
    service = TrainingLedgerService(_make_session())
    record = MagicMock(spec=TrainingLedger)
    record.id = uuid.uuid4()
    record.session_id = uuid.uuid4()
    record.ledger_department = "生产管理部"
    service.get_record = AsyncMock(return_value=record)
    service.repo = MagicMock()
    service.repo.soft_delete = AsyncMock()
    service.repo.mark_owner_deleted = AsyncMock()
    if session_dept is None:
        service.session.get.return_value = None
    else:
        session = MagicMock()
        session.department = session_dept
        service.session.get.return_value = session
    return service, record


@pytest.mark.asyncio
async def test_delete_record_owner_marks_others():
    """主办方（落款部门=归属部门）删除 → 同 session 其他副本标记 owner_deleted。"""
    service, record = _make_delete_service(session_dept="生产管理部")

    await service.delete_record(record.id)

    service.repo.mark_owner_deleted.assert_awaited_once_with(
        session_id=record.session_id, exclude_id=record.id
    )
    service.repo.soft_delete.assert_awaited_once_with(record)


@pytest.mark.asyncio
async def test_delete_record_non_owner_no_mark():
    """非主办方（落款部门 ≠ 归属部门）删除 → 只删自己，不触发联动标记。"""
    service, record = _make_delete_service(session_dept="QA")

    await service.delete_record(record.id)

    service.repo.mark_owner_deleted.assert_not_awaited()
    service.repo.soft_delete.assert_awaited_once_with(record)


@pytest.mark.asyncio
async def test_delete_record_without_session_no_mark():
    """无关联会话（如 Excel 导入记录）删除 → 不触发联动标记。"""
    service, record = _make_delete_service(session_dept=None)

    await service.delete_record(record.id)

    service.repo.mark_owner_deleted.assert_not_awaited()
    service.repo.soft_delete.assert_awaited_once_with(record)


# ── list_by_department：按 ledger_department 筛选 ────────


@pytest.mark.asyncio
async def test_list_by_department_returns_rows():
    """list_by_department 正常返回分页结果（筛选条件由 repository 拼装）。"""
    from app.modules.hr.repository import TrainingLedgerRepository

    session = AsyncMock()
    data_result = MagicMock()
    data_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
    count_result = MagicMock()
    count_result.scalar.return_value = 2

    async def fake_execute(stmt):
        if "count(" in str(stmt).lower() or "count" in str(stmt).lower():
            return count_result
        return data_result

    session.execute = AsyncMock(side_effect=fake_execute)

    repo = TrainingLedgerRepository(session)
    records, total = await repo.list_by_department("QA", page=1, page_size=20)

    assert len(records) == 2
    assert total == 2
