"""ESG 培训报表列表日期过滤测试（服务端分页配套改动）。"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.hr.esg_repository import EsgTrainingRecordRepository
from app.modules.hr.esg_service import EsgTrainingRecordService
from app.modules.hr.schemas import EsgListFilters


@pytest.mark.asyncio
async def test_esg_repo_list_by_department_with_date_filter():
    """传 date_from/date_to 不报错并正常返回分页结果（过滤条件由 repository 拼装）。"""
    session = AsyncMock()
    data_result = MagicMock()
    data_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
    count_result = MagicMock()
    count_result.scalar.return_value = 2

    # repository 先执行 count 再执行 data，按调用顺序区分返回
    executed: list = []

    def fake_execute(stmt):
        executed.append(stmt)
        return count_result if len(executed) == 1 else data_result

    session.execute = AsyncMock(side_effect=fake_execute)

    repo = EsgTrainingRecordRepository(session)
    records, total = await repo.list_by_department(
        "QA",
        page=1,
        page_size=20,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    assert total == 2
    assert len(records) == 2
    # 日期过滤确实拼进了查询（SQL 包含 training_date 条件）
    calls = [str(c.args[0]) for c in session.execute.await_args_list]
    assert any("training_date" in c for c in calls)


@pytest.mark.asyncio
async def test_esg_service_passes_date_filter_to_repo():
    """service.list_by_department 透传日期过滤给 repository。"""
    session = AsyncMock()
    repo = MagicMock()
    repo.list_by_department = AsyncMock(return_value=([], 0))
    service = EsgTrainingRecordService(session)
    service.repo = repo

    await service.list_by_department(
        "QA",
        page=1,
        page_size=20,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    repo.list_by_department.assert_awaited_once_with(
        department="QA",
        page=1,
        page_size=20,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
        filters=None,
    )


@pytest.mark.asyncio
async def test_esg_repo_applies_column_filters():
    """各列筛选参数拼进查询：文本 ilike、枚举精确、数值区间。"""
    session = AsyncMock()
    data_result = MagicMock()
    data_result.scalars.return_value.all.return_value = []
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    executed: list = []

    def fake_execute(stmt):
        executed.append(stmt)
        return count_result if len(executed) == 1 else data_result

    session.execute = AsyncMock(side_effect=fake_execute)

    filters = EsgListFilters(
        training_name="GMP",
        training_method="线下",
        gender="女",
        age_min=20,
        age_max=40,
        duration_min=1,
    )
    repo = EsgTrainingRecordRepository(session)
    records, total = await repo.list_by_department(
        "QA",
        page=1,
        page_size=20,
        filters=filters,
    )

    assert total == 0
    assert records == []
    sql = str(executed[0])
    assert "LIKE" in sql.upper()  # 文本列模糊（ilike 编译为 lower/like）
    assert "training_method" in sql  # 枚举列精确
    assert ":age_1" in sql and ":duration_1" in sql  # 数值区间绑定参数


@pytest.mark.asyncio
async def test_esg_repo_ignores_empty_filters():
    """filters 全为空时不追加任何筛选条件。"""
    session = AsyncMock()
    data_result = MagicMock()
    data_result.scalars.return_value.all.return_value = []
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    executed: list = []

    def fake_execute(stmt):
        executed.append(stmt)
        return count_result if len(executed) == 1 else data_result

    session.execute = AsyncMock(side_effect=fake_execute)

    repo = EsgTrainingRecordRepository(session)
    await repo.list_by_department("QA", filters=EsgListFilters())

    sql = str(executed[0])
    assert "LIKE" not in sql.upper()
    assert ":age_" not in sql and ":duration_" not in sql


@pytest.mark.asyncio
async def test_esg_service_passes_filters_to_repo():
    """service.list_by_department 透传列筛选给 repository。"""
    session = AsyncMock()
    repo = MagicMock()
    repo.list_by_department = AsyncMock(return_value=([], 0))
    repo.filter_options = AsyncMock(return_value={})
    service = EsgTrainingRecordService(session)
    service.repo = repo

    filters = EsgListFilters(employee_name="张三")
    await service.list_by_department("QA", filters=filters)
    repo.list_by_department.assert_awaited_once_with(
        department="QA",
        page=1,
        page_size=200,
        date_from=None,
        date_to=None,
        filters=filters,
    )

    options = await service.filter_options("QA")
    assert options == {}
