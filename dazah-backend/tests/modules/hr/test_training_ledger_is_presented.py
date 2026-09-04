"""培训台账 is_presented（是否呈现）全链测试。

覆盖：
- repository.list_all_for_employee_list 过滤 is_presented=False 的记录
- TrainingLedgerUpdate 可切换 is_presented 并持久化
- 部门台账导出常量/导入别名包含"是否呈现"（api.py 三常量联动）
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.api import (
    _DEPT_LEDGER_FIELDS,
    _DEPT_LEDGER_HEADER_ALIASES,
    _DEPT_LEDGER_HEADERS,
    _attach_ledger_attendance,
    _map_headers_by_alias,
)
from app.modules.hr.models import TrainingLedger
from app.modules.hr.repository import TrainingLedgerRepository
from app.modules.hr.schemas import TrainingLedgerUpdate
from app.modules.hr.service import TrainingLedgerService


def _ledger(subject: str, presented: bool) -> TrainingLedger:
    return TrainingLedger(
        employee_number=f"SPEC-IP-{uuid4().hex[:8]}",
        training_date=date(2026, 8, 1),
        training_datetime=date(2026, 8, 1).isoformat(),
        training_subject=subject,
        teaching_dept="SPEC测试车间",
        involved_depts="SPEC测试车间",
        trainees="测呈现",
        ledger_department="SPEC测试车间",
        source_type="manual",
        is_presented=presented,
    )


async def test_employee_training_list_filters_unpresented(
    db_session: AsyncSession,
) -> None:
    repo = TrainingLedgerRepository(db_session)
    shown = _ledger("呈现的培训", True)
    hidden = _ledger("不呈现的培训", False)
    db_session.add_all([shown, hidden])
    await db_session.flush()

    rows = await repo.list_all_for_employee_list()
    by_subject = {r.training_subject: r for r in rows}
    assert by_subject.get("呈现的培训") is not None
    assert by_subject.get("不呈现的培训") is None


async def test_update_toggles_is_presented(db_session: AsyncSession) -> None:
    service = TrainingLedgerService(db_session)
    record = _ledger("待切换的培训", True)
    db_session.add(record)
    await db_session.flush()

    updated = await service.update_record(
        record.id, TrainingLedgerUpdate(is_presented=False)
    )
    assert updated.is_presented is False


def test_dept_ledger_export_constants_include_presented() -> None:
    assert "是否呈现" in _DEPT_LEDGER_HEADERS
    assert "is_presented" in _DEPT_LEDGER_FIELDS
    assert len(_DEPT_LEDGER_HEADERS) == len(_DEPT_LEDGER_FIELDS)
    assert _DEPT_LEDGER_HEADER_ALIASES["是否呈现"] == "is_presented"


def test_import_alias_resolves_presented_header() -> None:
    mapping = _map_headers_by_alias(["是否呈现", "培训日期"])
    assert mapping["0"] == "is_presented"
    assert mapping["1"] == "training_date"


def test_training_content_schema_accepts_long_text() -> None:
    """培训内容已解除 4096 上限：超长内容新建/更新 schema 均不再被拒。"""
    from app.modules.hr.schemas import TrainingLedgerCreate

    long_content = "培训内容详情。" * 1200  # 7200 字符 > 4096
    created = TrainingLedgerCreate(
        training_content=long_content,
        ledger_department="质量部",
        source_type="manual",
    )
    assert created.training_content == long_content
    updated = TrainingLedgerUpdate(training_content=long_content)
    assert updated.training_content == long_content


@pytest.mark.asyncio
async def test_attach_ledger_attendance_session_names_then_trainees_fallback() -> None:
    """参训人员统计：有会话按真实名单数；无会话按培训对象分隔计数；不可数则为 None。"""
    sid_with_names = uuid4()
    sid_without_names = uuid4()
    records = [
        TrainingLedger(session_id=sid_with_names, trainees="忽略"),
        TrainingLedger(session_id=sid_without_names, trainees=""),
        TrainingLedger(session_id=None, trainees="张三、李四、王五"),
        TrainingLedger(session_id=None, trainees="生产部全体员工"),
        TrainingLedger(session_id=None, trainees=None),
    ]

    class _Result:
        def all(self) -> list[tuple[object, object]]:
            return [
                (sid_with_names, ["张三", "李四", "王五"]),
                (sid_without_names, None),
            ]

    db = SimpleNamespace(execute=AsyncMock(return_value=_Result()))
    await _attach_ledger_attendance(db, records)  # type: ignore[arg-type]

    assert records[0].attendance_count == 3  # 会话名单 3 人
    assert records[1].attendance_count is None  # 会话无名单
    assert records[2].attendance_count == 3  # 培训对象顿号分隔 3 段
    assert records[3].attendance_count is None  # 无分隔符的描述文本不可数
    assert records[4].attendance_count is None

