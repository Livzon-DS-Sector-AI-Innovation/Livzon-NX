from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundException
from app.modules.production import agent_tools as tools


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "model", "dependency", "method", "extra", "expected"),
    [
        (
            "list_batches",
            "BatchListInput",
            "ProductionService",
            "get_batches",
            {"batch_no": "B-2026"},
            {"batch_no": "B-2026", "skip": 5, "limit": 5},
        ),
        (
            "list_plans",
            "PlanListInput",
            "ProductionService",
            "get_plans",
            {"product_name": "多拉"},
            {"product_name": "多拉", "skip": 5, "limit": 5},
        ),
        (
            "list_pressure_records",
            "PressureListInput",
            "PressureService",
            "list_records",
            {"area": "A"},
            {"area": "A", "page": 2, "page_size": 5},
        ),
        (
            "list_label_verifications",
            "LabelListInput",
            "LabelVerificationService",
            "list_verifications",
            {"batch_number": "B-2026"},
            {"batch_number": "B-2026", "page": 2, "page_size": 5},
        ),
    ],
)
async def test_queries_forward_filters_and_pagination(
    monkeypatch,
    handler,
    model,
    dependency,
    method,
    extra,
    expected,
):
    query = AsyncMock(return_value=([], 12))
    service = SimpleNamespace(**{method: query})
    db = object()

    def constructor(session):
        assert session is db
        return service

    monkeypatch.setattr(tools, dependency, constructor)
    data = getattr(tools, model)(page=2, page_size=5, **extra)
    result = await getattr(tools, handler)(SimpleNamespace(db=db), data)
    assert result == {"data": [], "meta": {"page": 2, "page_size": 5, "total": 12}}
    assert query.await_count == 1
    for key, value in expected.items():
        assert query.await_args.kwargs[key] == value


@pytest.mark.asyncio
async def test_missing_or_inaccessible_batch_is_not_exposed(monkeypatch):
    query = AsyncMock(return_value=None)
    monkeypatch.setattr(
        tools, "ProductionService", lambda db: SimpleNamespace(get_batch=query)
    )
    batch_id = uuid4()
    with pytest.raises(NotFoundException):
        await tools.get_batch(
            SimpleNamespace(db=object()), tools.BatchIdInput(batch_id=batch_id)
        )
    query.assert_awaited_once_with(batch_id)


@pytest.mark.asyncio
async def test_batch_detail_serializes_uuid_and_dates(monkeypatch):
    batch_id = uuid4()
    now = datetime(2026, 10, 10, tzinfo=UTC)
    row = tools.BatchResponse(
        id=batch_id,
        batch_no="B-2026",
        product_code="P001",
        status="in_progress",
        created_at=now,
        updated_at=now,
    )
    query = AsyncMock(return_value=row)
    monkeypatch.setattr(
        tools, "ProductionService", lambda db: SimpleNamespace(get_batch=query)
    )
    result = await tools.get_batch(
        SimpleNamespace(db=object()),
        tools.BatchIdInput(batch_id=batch_id),
    )
    assert result["id"] == str(batch_id)
    assert result["created_at"] == "2026-10-10T00:00:00Z"
    assert result["status"] == "in_progress"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "input_type", "dependency", "method", "filters"),
    [
        (
            "list_sales_plan_details",
            "SalesPlanInput",
            "ProductionService",
            "get_sales_plan_details",
            {"product_name": "多拉菌素", "month": "2026-10"},
        ),
        (
            "list_nonconforming_events",
            "NceInput",
            "NCEService",
            "list_records",
            {"event_type": "停电", "workshop": "102-1"},
        ),
        (
            "list_shift_logs",
            "ShiftLogInput",
            "ShiftLogService",
            "list_records",
            {"shift": "night", "date_from": "2026-10-01"},
        ),
        (
            "list_shift_handovers",
            "HandoverInput",
            "ShiftHandoverService",
            "list_records",
            {"position": "操作员", "date_to": "2026-10-10"},
        ),
    ],
)
async def test_completion_tools_use_matching_service_and_bounded_query(
    monkeypatch,
    handler,
    input_type,
    dependency,
    method,
    filters,
):
    query = AsyncMock(return_value=([], 15))
    monkeypatch.setattr(
        tools, dependency, lambda db: SimpleNamespace(**{method: query})
    )
    data = getattr(tools, input_type)(page=2, page_size=5, **filters)
    result = await getattr(tools, handler)(SimpleNamespace(db=object()), data)
    assert result == {"data": [], "meta": {"page": 2, "page_size": 5, "total": 15}}
    for key, value in filters.items():
        assert query.await_args.kwargs[key] == value
    assert query.await_args.kwargs["page_size"] == 5


def test_ipc_summary_validates_actual_values_and_declares_no_persistence():
    from app.modules.production.ipc_schemas import IpcAnalysisInput
    from app.modules.production.ipc_service import IpcAnalysisService

    data = IpcAnalysisInput(
        samples=[
            {
                "stage": "seed",
                "tank": "A",
                "sampling_time": "2026-10-10T08:00:00Z",
                "ph": 6.5,
                "residual_sugar": 2,
            },
            {
                "stage": "fermentation",
                "tank": "A",
                "sampling_time": "2026-10-10T09:00:00Z",
                "ph": 7,
                "residual_sugar": 0,
            },
            {
                "stage": "fermentation",
                "tank": "B",
                "sampling_time": "2026-10-10T09:00:00Z",
            },
        ]
    )
    result = IpcAnalysisService.summarize(data)
    assert result.sample_count == 3
    assert result.seed_count == 1 and result.fermentation_count == 2
    assert result.tank_count == 2
    assert (result.ph_min, result.ph_max) == (6.5, 7)
    assert (result.residual_sugar_min, result.residual_sugar_max) == (0, 2)
    assert result.persisted is False and result.source == "user_supplied"
    result = IpcAnalysisService.summarize(IpcAnalysisInput(samples=[data.samples[2]]))
    assert result.ph_min is None and result.residual_sugar_min is None


@pytest.mark.parametrize(
    "invalid",
    [{"ph": 15}, {"ph": float("nan")}, {"residual_sugar": -1}, {"stage": "release"}],
)
def test_invalid_ipc_samples_are_rejected(invalid):
    from pydantic import ValidationError

    from app.modules.production.ipc_schemas import IpcAnalysisInput

    sample = {"stage": "seed", "tank": "A", "sampling_time": "2026-10-10T08:00:00Z"}
    with pytest.raises(ValidationError):
        IpcAnalysisInput(samples=[{**sample, **invalid}])


@pytest.mark.asyncio
async def test_sales_repository_preserves_filter_scope_and_pagination():
    from sqlalchemy.dialects import postgresql

    from app.modules.production.repository import ProductionRepository

    count = AsyncMock(return_value=7)
    query = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    result = await ProductionRepository(
        SimpleNamespace(scalar=count, scalars=query)
    ).get_sales_plan_details(
        page=2,
        page_size=5,
        product_name="多拉菌素",
        month="2026-10",
    )
    assert result == ([], 7)
    for mock in (count, query):
        compiled = mock.await_args.args[0].compile(dialect=postgresql.dialect())
        assert "is_deleted IS false" in str(compiled)
        assert "多拉菌素" in compiled.params.values()
        assert "2026-10" in compiled.params.values()
    compiled = query.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "LIMIT" in str(compiled) and "OFFSET" in str(compiled)


def test_production_tool_bindings_identify_unintegrated_scheduling_page():
    from app.modules.agent.tool_registration import ensure_agent_tools_registered
    from app.modules.agent.tools import tool_registry
    from app.platform.identity.page_policy import PAGES_BY_MODULE

    ensure_agent_tools_registered()
    specs = [s for s in tool_registry.list() if s.module == "production"]
    assert len(specs) == 10
    covered = {key for spec in specs for key in spec.page_keys}
    pages = {page.page_key for page in PAGES_BY_MODULE["production"]}
    assert covered <= pages
    assert pages - covered == {"production:plan:auto-scheduling"}
    assert all(not spec.write and not spec.human_decision_required for spec in specs)
