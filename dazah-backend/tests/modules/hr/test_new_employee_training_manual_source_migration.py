"""手动新增新员工培训计划（离岗复训）测试。

测试范围（对应《手动新增新员工（离岗复训）功能规格说明》Testing Decisions）：
- 无档案员工：按前端传入值创建，employee_id 为稳定虚拟 UUID。
  deadline = hire_date + 30 天
- 档案唯一命中：档案 department/position/hire_date 覆盖前端值，employee_id 为档案 id
- 档案多命中：不覆盖，按前端值创建
- 同名同部门已有计划：返回现有计划，不重复创建
- 培训岗位命中清单：items 非空；未命中：items 为空
- training_position 未传时按映射解析默认值
- 未登录提交：401

外部依赖（DB / 员工档案 / 岗位清单）全部 mock。
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.core.exceptions import AppException
from app.modules.hr.new_employee_training_api import manual_add_plan
from app.modules.hr.new_employee_training_service import NewEmployeeTrainingService


def _make_emp(
    emp_id, name="张三", dept="201车间", position="操作工", hire_date="2026-08-01"
):
    """构造员工档案 mock 对象。"""
    emp = MagicMock()
    emp.id = emp_id
    emp.name = name
    emp.department = dept
    emp.sub_department = None
    emp.position = position
    emp.employee_number = "E1001"
    emp.hire_date = date.fromisoformat(hire_date)
    return emp


def _make_service() -> NewEmployeeTrainingService:
    """构造全 mock 的 service：repo 链式返回 None / 空列表。"""
    session = MagicMock()
    # 部门归一会查培训部门列表；这里让查询返回空。
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    svc = NewEmployeeTrainingService(session)
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock()
    svc.repo.get_by_name_and_department = AsyncMock(return_value=None)
    # 岗位培训清单：默认未命中（items 为空）
    svc.repo.list_position_training_lists_by_dept_and_position = AsyncMock(
        return_value=[]
    )
    svc.repo.list_position_training_lists_by_dept = AsyncMock(return_value=[])
    svc.repo.list_ledgers_by_employee_name = AsyncMock(return_value=[])
    svc.mapping_repo = MagicMock()
    # 培训岗位映射解析：默认不解析（由各用例显式覆盖）
    svc._resolve_training_position = AsyncMock(return_value=None)
    return svc


# ── 无档案员工 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_plan_no_archive_uses_virtual_uuid():
    """无档案员工：按传入值创建，employee_id 为 uuid5 稳定虚拟 ID。"""
    svc = _make_service()
    # 档案查询返回空
    emp_repo = MagicMock()
    emp_repo.list_employees = AsyncMock(return_value=([], 0))
    emp_repo.get_by_id = AsyncMock(return_value=None)
    with patch("app.modules.hr.repository.EmployeeRepository", return_value=emp_repo):
        await svc.create_manual_plan(
            name="李四",
            department="201车间",
            position="操作工",
            hire_date=date(2026, 8, 1),
            user_id=None,
            sub_department=None,
            training_position="操作工岗",
            employee_id=None,
        )
    svc.repo.create.assert_awaited_once()
    created = svc.repo.create.await_args.args[0]
    assert created.employee_id == uuid5(NAMESPACE_URL, "manual:李四:201车间")
    assert created.employee_name == "李四"
    assert created.hire_date == date(2026, 8, 1)
    # deadline = 入职 + 30 天
    assert created.deadline_date == date(2026, 8, 31)


# ── 档案唯一命中 ────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_plan_archive_unique_overrides_fields():
    """档案唯一命中：部门/岗位/入职日期以档案为准覆盖前端值。"""
    svc = _make_service()
    emp = _make_emp("11111111-1111-1111-1111-111111111111", hire_date="2020-05-10")
    emp_repo = MagicMock()
    emp_repo.list_employees = AsyncMock(return_value=([emp], 1))
    emp_repo.get_by_id = AsyncMock(return_value=emp)
    with patch("app.modules.hr.repository.EmployeeRepository", return_value=emp_repo):
        await svc.create_manual_plan(
            name="张三",
            department="错误部门",
            position="错误岗位",
            hire_date=date(2026, 1, 1),  # 前端传入错误日期，应被档案覆盖
            user_id=None,
            training_position=None,
            employee_id=None,
        )
    created = svc.repo.create.await_args.args[0]
    assert created.employee_id == emp.id
    assert created.department == "201车间"
    assert created.position == "操作工"
    # 入职日期强制以档案为准
    assert created.hire_date == date(2020, 5, 10)
    assert created.deadline_date == date(2020, 6, 9)


@pytest.mark.asyncio
async def test_manual_plan_archive_unique_resolves_default_position():
    """档案唯一命中且未传培训岗位时，从映射解析默认值。"""
    svc = _make_service()
    svc._resolve_training_position = AsyncMock(return_value="解析出的岗位")
    emp = _make_emp("22222222-2222-2222-2222-222222222222")
    emp_repo = MagicMock()
    emp_repo.list_employees = AsyncMock(return_value=([emp], 1))
    emp_repo.get_by_id = AsyncMock(return_value=emp)
    with patch("app.modules.hr.repository.EmployeeRepository", return_value=emp_repo):
        await svc.create_manual_plan(
            name="张三",
            department="201车间",
            position="操作工",
            hire_date=date(2026, 8, 1),
            user_id=None,
            employee_id=None,
        )
    created = svc.repo.create.await_args.args[0]
    assert created.training_position == "解析出的岗位"


# ── 档案多命中 / 无命中 ─────────────────────────────


@pytest.mark.asyncio
async def test_manual_plan_archive_multiple_keeps_input():
    """档案多个同名命中：不自动覆盖，按前端传入值创建。"""
    svc = _make_service()
    emp_a = _make_emp(
        "33333333-3333-3333-3333-333333333333", dept="201车间", hire_date="2020-01-01"
    )
    emp_b = _make_emp(
        "44444444-4444-4444-4444-444444444444", dept="201二车间", hire_date="2021-01-01"
    )
    emp_repo = MagicMock()
    emp_repo.list_employees = AsyncMock(return_value=([emp_a, emp_b], 2))
    emp_repo.get_by_id = AsyncMock(return_value=None)
    with patch("app.modules.hr.repository.EmployeeRepository", return_value=emp_repo):
        await svc.create_manual_plan(
            name="张三",
            department="手动部门",
            position="手动岗位",
            hire_date=date(2026, 8, 1),
            user_id=None,
            training_position="手动培训岗位",
            employee_id=None,
        )
    created = svc.repo.create.await_args.args[0]
    assert created.department == "手动部门"
    assert created.position == "手动岗位"
    assert created.hire_date == date(2026, 8, 1)
    assert created.training_position == "手动培训岗位"
    # 多命中不覆盖 → 虚拟 UUID（非档案 id）
    assert created.employee_id == uuid5(NAMESPACE_URL, "manual:张三:手动部门")


# ── 查重 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_plan_duplicate_returns_existing():
    """同名同部门已有未删除计划：返回现有计划，不重复创建。"""
    svc = _make_service()
    existing = MagicMock()
    svc.repo.get_by_name_and_department = AsyncMock(return_value=existing)
    emp_repo = MagicMock()
    emp_repo.list_employees = AsyncMock(return_value=([], 0))
    with patch("app.modules.hr.repository.EmployeeRepository", return_value=emp_repo):
        plan = await svc.create_manual_plan(
            name="张三",
            department="201车间",
            position="操作工",
            hire_date=date(2026, 8, 1),
            user_id=None,
            employee_id=None,
        )
    assert plan is existing
    svc.repo.create.assert_not_awaited()


# ── API：未登录 401 ─────────────────────────────────


@pytest.mark.asyncio
async def test_manual_add_plan_requires_login():
    """未登录提交手动新增应返回 401。"""
    from app.modules.hr.schemas import NewEmployeeTrainingManualAdd

    body = NewEmployeeTrainingManualAdd(
        name="张三",
        department="201车间",
        position="操作工",
        hire_date=date(2026, 8, 1),
    )
    with pytest.raises(AppException) as exc_info:
        await manual_add_plan(body, current_user=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@patch("app.modules.hr.new_employee_training_api._require_user")
async def test_manual_add_plan_success(mock_require):
    """登录后提交成功，返回计划响应。"""
    from app.modules.hr.schemas import NewEmployeeTrainingManualAdd

    mock_require.return_value = "user-1"
    body = NewEmployeeTrainingManualAdd(
        name="张三",
        department="201车间",
        position="操作工",
        hire_date=date(2026, 8, 1),
    )
    service = MagicMock()
    plan = MagicMock()
    plan.id = "plan-1"
    service.create_manual_plan = AsyncMock(return_value=plan)
    service.get_plan = AsyncMock(return_value={"id": "plan-1", "items": []})
    resp = await manual_add_plan(body, service=service, current_user=MagicMock())
    import json

    payload = json.loads(resp.body)["data"]
    assert payload["id"] == "plan-1"
    # 未命中清单 → 提示可手动添加教材
    assert "手动添加教材" in json.loads(resp.body)["message"]


# ── Bug 修复：添加参训人员部门过滤（手动新增员工不可见） ──


# 201 家族映射数据（与 seed_training_dept_mappings.py 一致）
_201_MAPPINGS = [
    {
        "source_name": "201二车间",
        "target_name": "201二车间（MC）",
        "match_level": "both",
        "mapping_type": "special",
        "priority": 10,
    },
    {
        "source_name": "201二车间（霉酚酸）",
        "target_name": "201二车间（MC）",
        "match_level": "both",
        "mapping_type": "special",
        "priority": 10,
    },
    {
        "source_name": "201二车间（MC）",
        "target_name": "201二车间（MC）",
        "match_level": "both",
        "mapping_type": "special",
        "priority": 10,
    },
    {
        "source_name": "201二车间（多拉）",
        "target_name": "201二车间（DR）",
        "match_level": "both",
        "mapping_type": "special",
        "priority": 10,
    },
    {
        "source_name": "201二车间（DR）",
        "target_name": "201二车间（DR）",
        "match_level": "both",
        "mapping_type": "special",
        "priority": 10,
    },
    {
        "source_name": "201三车间",
        "target_name": "201二车间（MC）",
        "match_level": "both",
        "mapping_type": "special",
        "priority": 10,
    },
]


def _patch_resolver_mappings(monkeypatch, extra: list[dict] | None = None):
    """monkeypatch _load_mappings 返回测试用映射数据。"""
    import app.modules.hr.training_dept_resolver as _resolver_mod

    mappings = list(_201_MAPPINGS)
    if extra:
        mappings.extend(extra)

    async def fake_load(_session):
        return mappings

    monkeypatch.setattr(_resolver_mod, "_load_mappings", fake_load)
    _resolver_mod.invalidate_training_dept_mapping_cache()


@pytest.mark.asyncio
async def test_training_dept_aliases_of_201_first_workshop(monkeypatch):
    """201一车间 无映射时别名集合为自身（含自身）。"""
    from app.modules.hr.training_dept_resolver import training_dept_aliases_of

    _patch_resolver_mappings(monkeypatch)
    aliases = await training_dept_aliases_of(MagicMock(), "201一车间")
    assert aliases == ["201一车间"]


@pytest.mark.asyncio
async def test_training_dept_aliases_of_201_second_mc_expands(monkeypatch):
    """201二车间（MC）展开全部别名：裸名/霉酚酸/201三车间。"""
    from app.modules.hr.training_dept_resolver import training_dept_aliases_of

    _patch_resolver_mappings(monkeypatch)
    aliases = await training_dept_aliases_of(MagicMock(), "201二车间（MC）")
    assert "201二车间" in aliases
    assert "201二车间（霉酚酸）" in aliases
    assert "201三车间" in aliases


@pytest.mark.asyncio
async def test_available_trainees_filter_201_first_workshop(monkeypatch):
    """201一车间 计划：过滤条件包含 201一车间（命中手动新增与
    档案 sub_department=201一车间），不包含 201二车间 别名。"""
    from app.modules.hr.new_employee_training_repository import (
        NewEmployeeTrainingRepository,
    )

    _patch_resolver_mappings(monkeypatch)
    repo = NewEmployeeTrainingRepository(MagicMock())
    captured = {}

    async def fake_execute(stmt, *args, **kwargs):
        captured["stmt"] = stmt
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        return result_mock

    repo.session.execute = fake_execute
    await repo.list_available_trainees(department="201一车间")
    sql = str(captured["stmt"].compile(compile_kwargs={"literal_binds": True}))
    # 过滤条件应命中 201一车间（含 department 与 sub_department 两个字段）
    assert "department IN ('201一车间')" in sql
    assert "sub_department IN ('201一车间')" in sql
    # 不应混入 201二车间 别名
    assert "201二车间" not in sql


@pytest.mark.asyncio
async def test_available_trainees_filter_201_second_mc(monkeypatch):
    """201二车间（MC）计划：过滤条件展开全部别名（裸名/霉酚酸/201三车间），
    不包含 201一车间。"""
    from app.modules.hr.new_employee_training_repository import (
        NewEmployeeTrainingRepository,
    )

    _patch_resolver_mappings(monkeypatch)
    repo = NewEmployeeTrainingRepository(MagicMock())
    captured = {}

    async def fake_execute(stmt, *args, **kwargs):
        captured["stmt"] = stmt
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        return result_mock

    repo.session.execute = fake_execute
    await repo.list_available_trainees(department="201二车间（MC）")
    sql = str(captured["stmt"].compile(compile_kwargs={"literal_binds": True}))
    assert "201二车间（MC）" in sql
    assert "201二车间" in sql
    assert "201二车间（霉酚酸）" in sql
    assert "201三车间" in sql
    assert "201一车间" not in sql
