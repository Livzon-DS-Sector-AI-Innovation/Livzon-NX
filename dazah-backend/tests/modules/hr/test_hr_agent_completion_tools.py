from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.modules.hr import agent_query_service as queries
from app.modules.hr import agent_tools as tools
from app.platform.identity.data_scope import DepartmentScope

SCOPED_QUERIES = [
    ("list_departments", "KeywordInput", "HrAgentQueryService", "list_departments"),
    ("list_contacts", "ContactInput", "HrAgentQueryService", "list_contacts"),
    ("list_onboarding", "KeywordInput", "OnboardingService", "list_onboarding"),
    (
        "list_offboarding",
        "EmployeeRecordInput",
        "OffboardingRecordService",
        "list_records",
    ),
    (
        "list_position_transfers",
        "TransferInput",
        "PositionTransferRecordService",
        "list_records",
    ),
    ("list_contracts", "ContractInput", "HrAgentQueryService", "list_contracts"),
    (
        "list_contract_approval_results",
        "ApprovalResultInput",
        "HrAgentQueryService",
        "list_contract_approval_results",
    ),
    (
        "list_new_employee_training",
        "NewTrainingInput",
        "NewEmployeeTrainingService",
        "list_plans",
    ),
    ("list_trainers", "DepartmentInput", "TrainerService", "list_trainers"),
    (
        "list_position_training",
        "PositionTrainingInput",
        "PositionTrainingListService",
        "list_lists",
    ),
    (
        "list_training_plan_tracking",
        "TrackingInput",
        "PlanTrackingService",
        "list_records",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "model", "dependency", "method", "fields"),
    [
        (
            "list_departments",
            "KeywordInput",
            "HrAgentQueryService",
            "list_departments",
            {"name": "生产部"},
        ),
        (
            "list_offboarding",
            "EmployeeRecordInput",
            "OffboardingRecordService",
            "list_records",
            {"name": "员工"},
        ),
        (
            "list_position_transfers",
            "TransferInput",
            "PositionTransferRecordService",
            "list_records",
            {"employee_name": "员工", "effective_date": date(2026, 10, 1)},
        ),
        (
            "list_contracts",
            "ContractInput",
            "HrAgentQueryService",
            "list_contracts",
            {
                "name": "员工",
                "employee_number": "001",
                "contract_start_1": date(2026, 10, 1),
            },
        ),
        (
            "list_trainers",
            "DepartmentInput",
            "TrainerService",
            "list_trainers",
            {"name": "培训师", "approval_date": date(2026, 10, 1)},
        ),
        (
            "list_position_training",
            "PositionTrainingInput",
            "PositionTrainingListService",
            "list_lists",
            {
                "department": "生产部",
                "position": "操作员",
                "create_date": date(2026, 10, 1),
                "items": [],
            },
        ),
        (
            "list_training_plan_tracking",
            "TrackingInput",
            "PlanTrackingService",
            "list_records",
            {"department": "生产部", "track_date": date(2026, 10, 1)},
        ),
    ],
)
async def test_nonempty_responses_use_business_schemas(
    monkeypatch, handler, model, dependency, method, fields
):
    monkeypatch.setattr(
        tools,
        "resolve_user_department_scope",
        AsyncMock(return_value=DepartmentScope(is_all=True, department_names=set())),
    )
    identifier = uuid4()
    row = SimpleNamespace(
        id=identifier,
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
        updated_at=datetime(2026, 10, 1, tzinfo=UTC),
        **fields,
    )
    query = AsyncMock(return_value=([row], 1))
    monkeypatch.setattr(
        tools, dependency, lambda db: SimpleNamespace(**{method: query})
    )
    result = await getattr(tools, handler)(
        SimpleNamespace(db=object(), user=object()), getattr(tools, model)()
    )
    assert result["data"][0]["id"] == str(identifier)
    assert result["data"][0]["created_at"] == "2026-10-01T00:00:00Z"
    for key, value in fields.items():
        assert result["data"][0][key] == (
            value.isoformat() if isinstance(value, date) else value
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, set(), {"生产部"}])
@pytest.mark.parametrize(("handler", "model", "dependency", "method"), SCOPED_QUERIES)
async def test_completed_queries_preserve_scope_and_pagination(
    monkeypatch, scope, handler, model, dependency, method
):
    actor, db = object(), object()
    resolver = AsyncMock(
        return_value=DepartmentScope(
            is_all=scope is None, department_names=scope or set()
        )
    )
    monkeypatch.setattr(tools, "resolve_user_department_scope", resolver)
    query = AsyncMock(return_value=([], 12))
    constructor_args = []

    def service(*args):
        constructor_args.append(args)
        return SimpleNamespace(**{method: query})

    monkeypatch.setattr(tools, dependency, service)
    result = await getattr(tools, handler)(
        SimpleNamespace(db=db, user=actor), getattr(tools, model)(page=2, page_size=3)
    )
    assert result == {"data": [], "meta": {"page": 2, "page_size": 3, "total": 12}}
    resolver.assert_awaited_once_with(db, actor)
    assert query.await_args.kwargs["dept_alias_set"] == scope
    assert query.await_args.kwargs["page"] == 2
    assert query.await_args.kwargs["page_size"] == 3
    assert constructor_args == ([()] if dependency == "OnboardingService" else [(db,)])


@pytest.mark.asyncio
async def test_candidates_use_business_service_without_database_as_app_token(
    monkeypatch,
):
    query = AsyncMock(return_value=([{"id": "candidate", "name": "候选人"}], 1))
    monkeypatch.setattr(
        tools, "RecruitmentService", lambda: SimpleNamespace(list_candidates=query)
    )
    result = await tools.list_candidates(
        SimpleNamespace(db=object(), user=object()),
        tools.CandidateInput(job_id="job", fit_level="A"),
    )
    assert result["data"][0]["name"] == "候选人"
    assert query.await_args.kwargs["job_id"] == "job"
    assert query.await_args.kwargs["fit_level"] == "A"


@pytest.mark.asyncio
async def test_employee_training_summary_is_paginated_and_serializes_dates(monkeypatch):
    monkeypatch.setattr(
        tools,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(is_all=False, department_names={"生产部"})
        ),
    )
    identifier = uuid4()
    query = AsyncMock(
        return_value=[
            {"name": "一"},
            {"id": identifier, "date": date(2026, 10, 1)},
            {"name": "三"},
        ]
    )
    monkeypatch.setattr(
        tools,
        "EmployeeTrainingListService",
        lambda db: SimpleNamespace(list_employee_training_summary=query),
    )
    result = await tools.list_employee_training_summary(
        SimpleNamespace(db=object(), user=object()),
        tools.EmployeeTrainingInput(department="生产部", page=2, page_size=1),
    )
    assert result == {
        "data": [{"id": str(identifier), "date": "2026-10-01"}],
        "meta": {"page": 2, "page_size": 1, "total": 3},
    }
    assert query.await_args.kwargs == {
        "department": "生产部",
        "name": None,
        "date_from": None,
        "date_to": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "model"),
    [
        ("list_contacts", "ContactInput"),
        ("list_contracts", "ContractInput"),
        ("list_contract_approval_results", "ApprovalResultInput"),
        ("list_new_employee_training", "NewTrainingInput"),
        ("list_employee_training_summary", "EmployeeTrainingInput"),
        ("list_trainers", "DepartmentInput"),
        ("list_position_training", "PositionTrainingInput"),
    ],
)
async def test_department_override_rejected_before_service(monkeypatch, handler, model):
    monkeypatch.setattr(
        tools,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(is_all=False, department_names={"生产部"})
        ),
    )
    with pytest.raises(HTTPException) as error:
        await getattr(tools, handler)(
            SimpleNamespace(db=object(), user=object()),
            getattr(tools, model)(department="财务部"),
        )
    assert error.value.status_code == 403


def sql(statement):
    return str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, set(), {"生产部"}])
async def test_department_query_filters_count_and_rows_before_pagination(scope):
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=0),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
    )
    result = await queries.HrAgentQueryService(db).list_departments(
        keyword="生产", page=2, page_size=5, dept_alias_set=scope
    )
    assert result == ([], 0)
    count, rows = sql(db.scalar.await_args.args[0]), sql(db.scalars.await_args.args[0])
    for statement in (count, rows):
        assert "is_deleted IS false" in statement
        assert "ILIKE '%%生产%%'" in statement
        assert ("name IN" in statement) == (scope is not None)
        if scope == set():
            assert "1 != 1" in statement
    assert "LIMIT 5 OFFSET 5" in rows


@pytest.mark.asyncio
async def test_contacts_limit_output_to_work_fields_and_filter_authorized_rows():
    member = SimpleNamespace(
        id=uuid4(),
        name="张三",
        department="生产部",
        employee_no="001",
        job_title="操作员",
        status="1",
        mobile="private",
        email="private",
        open_id="private",
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=1),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [member])),
    )
    rows, total = await queries.HrAgentQueryService(db).list_contacts(
        keyword="张",
        department="生产部",
        status="1",
        page=2,
        page_size=5,
        dept_alias_set={"生产部"},
    )
    assert total == 1
    assert set(rows[0].model_dump()) == {
        "id",
        "name",
        "department",
        "employee_no",
        "job_title",
        "status",
    }
    assert rows[0].name == "张三"
    for statement in (
        sql(db.scalar.await_args.args[0]),
        sql(db.scalars.await_args.args[0]),
    ):
        assert "employee_no IS NOT NULL" in statement
        assert "department IN ('生产部')" in statement
        assert "status = '1'" in statement
        assert "is_deleted IS false" in statement
    assert "LIMIT 5 OFFSET 5" in sql(db.scalars.await_args.args[0])


@pytest.mark.asyncio
async def test_contract_ledger_only_includes_approved_and_synced(monkeypatch):
    query = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        queries, "ContractRepository", lambda db: SimpleNamespace(list=query)
    )
    assert await queries.HrAgentQueryService(object()).list_contracts(
        keyword=None,
        department=None,
        contract_sequence=None,
        page=1,
        page_size=20,
        dept_alias_set=set(),
    ) == ([], 0)
    assert query.await_args.kwargs["approval_statuses"] == ["approved", "synced"]
    assert query.await_args.kwargs["dept_alias_set"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [None, set(), {"生产部"}])
async def test_approval_results_read_completed_records_with_scope_and_dates(scope):
    approved = datetime(2026, 10, 5, 9, tzinfo=UTC)
    row = SimpleNamespace(
        id=uuid4(),
        employee_number="001",
        name="员工",
        dept_level1="生产部",
        approval_status="approved",
        supervisor_approved_at=approved,
        dept_approved_at=None,
        contract_end_1="2026-01-01",
        contract_end_2="2027-01-01",
    )
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=1),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [row])),
    )
    rows, total = await queries.HrAgentQueryService(db).list_contract_approval_results(
        department="生产部",
        result="approved",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 10),
        page=2,
        page_size=5,
        dept_alias_set=scope,
    )
    assert total == 1
    assert rows[0]["id"] == str(row.id)
    assert rows[0]["contract_end_date"] == "2027-01-01"
    assert rows[0]["completed_at"] == approved.isoformat()
    for statement in (
        sql(db.scalar.await_args.args[0]),
        sql(db.scalars.await_args.args[0]),
    ):
        assert "approval_status IN ('approved', 'rejected')" in statement
        assert "approval_status = 'approved'" in statement
        assert "2026-10-01 00:00:00+00:00" in statement
        assert "2026-10-10 23:59:59.999999+00:00" in statement
        assert ("dept_level2 IN" in statement) == (scope is not None)
    assert "LIMIT 5 OFFSET 5" in sql(db.scalars.await_args.args[0])
