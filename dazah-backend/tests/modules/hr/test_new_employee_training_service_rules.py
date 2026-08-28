from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.hr import new_employee_training_service as module
from app.modules.hr import training_dept_resolver

SimpleNamespace: Any = _SimpleNamespace


def _service(repo: SimpleNamespace, mapping_repo: SimpleNamespace | None = None) -> Any:
    instance = module.NewEmployeeTrainingService.__new__(
        module.NewEmployeeTrainingService
    )
    instance.repo = repo
    instance.mapping_repo = mapping_repo or SimpleNamespace(
        get_mapping=AsyncMock(return_value=None)
    )
    instance.session = SimpleNamespace(add=lambda value: None, flush=AsyncMock())
    return instance


def _plan(**overrides: Any) -> Any:
    values = {
        "id": uuid4(),
        "employee_id": uuid4(),
        "employee_name": "张三",
        "employee_number": "E001",
        "department": "质量部",
        "sub_department": "QA",
        "position": "专员",
        "training_position": "QA专员",
        "hire_date": date(2026, 8, 1),
        "deadline_date": date(2026, 8, 31),
        "items": [
            {
                "id": "i1",
                "level": "部门级",
                "textbook_name": "GMP 基础",
                "textbook_code": "SMP-1",
                "assessment_method": "考试",
                "sort_order": 0,
            }
        ],
        "created_at": None,
        "updated_at": None,
        "updated_by": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normalization_completion_status_and_item_building() -> None:
    instance = _service(SimpleNamespace())
    assert module._normalize_text(None) == ""
    assert module._normalize_text("GMP 基 础") == "GMP基础"
    ledger: Any = SimpleNamespace(
        trainees="张三", training_content="GMP基础课程", training_date=date(2026, 8, 10)
    )
    assert instance._is_item_done(ledger, "GMP 基础")
    assert not instance._is_item_done(
        SimpleNamespace(trainees="", training_content="GMP"), "GMP"
    )
    items = instance._build_item_dicts(
        _plan(
            items=[
                {"textbook_name": "B", "sort_order": 2},
                {"textbook_name": "A"},
                "bad",
            ]
        )
    )
    assert [item["textbook_name"] for item in items] == ["A", "B"]
    done = instance._compute_item_done_map(
        [ledger], [{"id": "i1", "textbook_name": "GMP基础"}, {}]
    )
    assert done == {"i1": date(2026, 8, 10)}
    assert (
        instance._compute_plan_status(
            completed_count=0, total_count=0, deadline_date=None
        )
        == "待安排"
    )
    assert (
        instance._compute_plan_status(
            completed_count=1, total_count=1, deadline_date=None
        )
        == "已完成"
    )
    assert (
        instance._compute_plan_status(
            completed_count=0,
            total_count=1,
            deadline_date=date(2026, 8, 1),
            today=date(2026, 8, 2),
        )
        == "逾期"
    )


@pytest.mark.anyio
async def test_resolve_position_prefers_normalized_department_then_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping_repo: Any = SimpleNamespace(
        get_mapping=AsyncMock(
            side_effect=[None, SimpleNamespace(training_position="QA")]
        )
    )
    instance = _service(SimpleNamespace(), mapping_repo)
    monkeypatch.setattr(
        training_dept_resolver,
        "resolve_training_department",
        AsyncMock(return_value="规范质量部"),
    )
    assert await instance._resolve_training_position("质量", "QA", "专员") == "QA"
    assert mapping_repo.get_mapping.await_args_list[0].args == ("规范质量部", "专员")
    assert mapping_repo.get_mapping.await_args_list[1].args == ("质量", "专员")


@pytest.mark.anyio
async def test_build_plan_items_filters_completed_and_empty_textbooks() -> None:
    completed: Any = SimpleNamespace(
        trainees="张三", training_content="已完成GMP", training_date=date.today()
    )
    training_list: Any = SimpleNamespace(
        items=[
            SimpleNamespace(
                textbook_name="GMP",
                level="部门级",
                textbook_code="1",
                assessment_method="考",
                remarks=None,
            ),
            SimpleNamespace(
                textbook_name="安全",
                level="岗位级",
                textbook_code="2",
                assessment_method="问答",
                remarks="重点",
            ),
            SimpleNamespace(
                textbook_name="",
                level="岗位级",
                textbook_code=None,
                assessment_method=None,
                remarks=None,
            ),
        ]
    )
    repo: Any = SimpleNamespace(
        list_position_training_lists_by_dept_and_position=AsyncMock(
            return_value=[training_list]
        ),
        list_position_training_lists_by_dept=AsyncMock(return_value=[training_list]),
        list_ledgers_by_employee_name=AsyncMock(return_value=[completed]),
    )
    instance = _service(repo)
    items = await instance._build_plan_items(
        training_position="QA",
        department="质量",
        sub_department=None,
        employee_name="张三",
    )
    assert [item["textbook_name"] for item in items] == ["安全"]
    await instance._build_plan_items(
        training_position=None,
        department="质量",
        sub_department="QA",
        employee_name="张三",
    )
    repo.list_position_training_lists_by_dept.assert_awaited_once()


@pytest.mark.anyio
async def test_generate_plan_handles_missing_existing_and_new_employee() -> None:
    employee: Any = SimpleNamespace(
        id=uuid4(),
        name="张三",
        employee_number="E001",
        department="质量部",
        sub_department="QA",
        position="专员",
        hire_date=date(2026, 8, 1),
    )
    repo: Any = SimpleNamespace(
        get_employee_by_id=AsyncMock(return_value=None),
        get_by_employee_id=AsyncMock(return_value=None),
        create=AsyncMock(),
    )
    instance = _service(repo)
    with pytest.raises(NotFoundException):
        await instance.generate_plan(uuid4(), None)
    existing = _plan()
    repo.get_employee_by_id.return_value = employee
    repo.get_by_employee_id.return_value = existing
    assert await instance.generate_plan(employee.id, None) is existing
    repo.get_by_employee_id.return_value = None
    instance._resolve_training_position = AsyncMock(return_value="QA专员")
    instance._build_plan_items = AsyncMock(return_value=[{"id": "i1"}])
    created = await instance.generate_plan(employee.id, uuid4())
    assert created.deadline_date == employee.hire_date + timedelta(days=30)
    assert created.training_position == "QA专员"
    repo.create.assert_awaited_once_with(created)


@pytest.mark.anyio
async def test_response_list_get_add_update_and_delete_flows() -> None:
    ledger: Any = SimpleNamespace(
        trainees="张三", training_content="GMP基础", training_date=date(2026, 8, 10)
    )
    plan = _plan()
    repo: Any = SimpleNamespace(
        list_ledgers_by_employee_name=AsyncMock(return_value=[ledger]),
        list_plans=AsyncMock(return_value=([plan], 1)),
        get_by_id=AsyncMock(return_value=plan),
        update=AsyncMock(),
        delete=AsyncMock(),
    )
    instance = _service(repo)
    response = await instance._build_response(plan)
    assert response["status"] == "已完成"
    assert response["progress"] == 100
    rows, total = await instance.list_plans(keyword="张")
    assert total == 1 and rows[0]["employee_name"] == "张三"
    assert (await instance.get_plan(plan.id))["id"] == plan.id

    no_update: Any = SimpleNamespace(
        deadline_date=None, training_position=None, items=None
    )
    assert (await instance.update_plan(plan.id, no_update, None))["id"] == plan.id
    added = await instance.add_item(plan.id, {"textbook_name": "安全"}, uuid4())
    assert added is not None
    assert await instance.delete_plan(plan.id, uuid4()) is True
    repo.get_by_id.return_value = None
    assert await instance.get_plan(uuid4()) is None
    assert await instance.update_plan(uuid4(), no_update, None) is None
    assert await instance.add_item(uuid4(), {}, None) is None
    assert await instance.delete_plan(uuid4(), None) is False


@pytest.mark.anyio
async def test_start_training_validates_selection_and_builds_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    repo: Any = SimpleNamespace(get_by_id=AsyncMock(return_value=None))
    instance = _service(repo)
    with pytest.raises(NotFoundException):
        await instance.start_training(uuid4(), ["i1"], None)
    repo.get_by_id.return_value = plan
    with pytest.raises(AppException):
        await instance.start_training(plan.id, [], None)
    with pytest.raises(AppException):
        await instance.start_training(plan.id, ["missing"], None)
    monkeypatch.setattr(
        training_dept_resolver,
        "resolve_training_department",
        AsyncMock(return_value="规范质量部"),
    )
    captured: dict[str, object] = {}

    def add_session(value: object) -> None:
        captured["session"] = value

    async def assign_session_id() -> None:
        captured["session"].id = uuid4()  # type: ignore[attr-defined]

    instance.session = SimpleNamespace(
        add=add_session, flush=AsyncMock(side_effect=assign_session_id)
    )
    result = await instance.start_training(
        plan.id,
        ["i1"],
        uuid4(),
        additional_trainees=[
            {"name": "李四", "department": "生产部"},
            {"name": "张三", "department": "质量部"},
        ],
    )
    assert result.department == "规范质量部"
    assert result.employee_names == ["张三", "李四"]
    assert "《GMP 基础》（SMP-1）" in result.topic
    instance.session.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_stats_and_available_trainees_map_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plans = [_plan(id=uuid4()) for _ in range(4)]
    repo: Any = SimpleNamespace(
        list_plans=AsyncMock(return_value=(plans, 4)),
        list_available_trainees=AsyncMock(
            return_value=[
                {"name": "李四", "department": "质量", "sub_department": "QA"}
            ]
        ),
    )
    instance = _service(repo)
    instance._build_response = AsyncMock(
        side_effect=[
            {"status": "已完成"},
            {"status": "逾期"},
            {"status": "培训中"},
            {"status": "待安排"},
        ]
    )
    stats = await instance.get_stats()
    assert (stats.completed, stats.overdue, stats.training, stats.pending) == (
        1,
        1,
        1,
        1,
    )
    monkeypatch.setattr(
        training_dept_resolver,
        "resolve_training_department",
        AsyncMock(return_value="规范质量部"),
    )
    available = await instance.list_available_trainees(department="质量部")
    assert available == [{"name": "李四", "department": "规范质量部"}]
