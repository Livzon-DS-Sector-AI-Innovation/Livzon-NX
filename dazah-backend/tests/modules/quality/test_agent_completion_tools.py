from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy.dialects import postgresql

from app.core.exceptions import ForbiddenException
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.modules.quality import agent_tools as tools
from app.modules.quality.service import agent_queries
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_data_scope,
)
from app.platform.identity.page_policy import PAGES_BY_MODULE, api_binding_for_route

CASES = [
    ("list_documents", "DocumentListInput", "agent_queries", "list_documents", (), {}),
    (
        "list_deviation_reports",
        "PageInput",
        "quality_feishu_pages",
        "list_report_records",
        (),
        {},
    ),
    (
        "list_deviation_investigations",
        "InvestigationListInput",
        "quality_feishu_pages",
        "list_investigation_push_records",
        (),
        {"deviation_code": "PC-001"},
    ),
    (
        "list_historical_deviations",
        "InspectionResourceListInput",
        "historical_deviation",
        "get_historical_deviation_list",
        (),
        {},
    ),
    (
        "list_deviation_workbench_reports",
        "WorkbenchListInput",
        "deviation_workbench",
        "list_workbench_reports",
        (),
        {"date_from": "2026-10-01"},
    ),
    (
        "list_lab_item_inbounds",
        "InspectionResourceListInput",
        "inspection_items_mirror",
        "list_items_mirror",
        ("qc_items_inbound",),
        {},
    ),
    (
        "list_lab_item_outbounds",
        "InspectionResourceListInput",
        "inspection_items_mirror",
        "list_items_mirror",
        ("qc_items_outbound",),
        {},
    ),
    (
        "list_oos_oot_reports",
        "InspectionResourceListInput",
        "quality_feishu_pages_oos_oot",
        "list_oos_oot_report_records",
        (),
        {},
    ),
    (
        "list_oos_oot_investigations",
        "OosInvestigationListInput",
        "quality_feishu_pages_oos_oot",
        "list_oos_oot_investigation_push_records",
        (),
        {"oos_oot_code": "OOT-001"},
    ),
    (
        "list_oot_ledger",
        "InspectionResourceListInput",
        "quality_feishu_pages_oos_oot",
        "list_oot_ledger_records",
        (),
        {},
    ),
    (
        "list_oot_limit_products",
        "InspectionResourceListInput",
        "agent_queries",
        "list_oot_limit_products",
        (),
        {},
    ),
    (
        "list_product_departments",
        "InspectionResourceListInput",
        "quality_feishu_pages_oos_oot",
        "list_product_department_records",
        (),
        {},
    ),
    (
        "list_finished_product_anomalies",
        "AnomalyListInput",
        "inspection_feishu_crud",
        "list_bitable_feishu_records",
        ("finished_product_anomaly_2027",),
        {"year": 2027},
    ),
    (
        "list_qc_validations",
        "QcValidationListInput",
        "inspection_feishu_crud",
        "list_bitable_feishu_records",
        ("validation_qc_2028",),
        {"year": 2028},
    ),
    (
        "list_validation_reviews",
        "ReviewListInput",
        "agent_queries",
        "list_validation_reviews",
        (),
        {"status": "completed"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "input_type", "dependency", "method", "args", "filters"), CASES
)
async def test_completion_query_uses_own_service_bounded_filters_and_serialization(
    monkeypatch, handler, input_type, dependency, method, args, filters
):
    class Row(BaseModel):
        name: str

    expected = {"items": [Row(name="已有记录")], "total": 1, "page": 2, "page_size": 5}
    query = AsyncMock(return_value=expected)
    monkeypatch.setattr(getattr(tools, dependency), method, query)
    data = getattr(tools, input_type)(page=2, page_size=5, **filters)
    db = object()
    result = await getattr(tools, handler)(SimpleNamespace(db=db), data)
    # The three scoped services already return JSON-safe dictionaries.
    if dependency == "agent_queries":
        assert result == expected
    else:
        assert result["items"] == [{"name": "已有记录"}]
    assert result["total"] == 1 and result["page_size"] == 5
    assert query.await_args.args == (db, *args)
    for key, value in filters.items():
        if key != "year":
            assert query.await_args.kwargs[key] == value
    assert query.await_args.kwargs["page"] == 2
    assert query.await_args.kwargs["page_size"] == 5
    assert "year" not in query.await_args.kwargs
    query.side_effect = ForbiddenException("无权查询")
    with pytest.raises(ForbiddenException):
        await getattr(tools, handler)(SimpleNamespace(db=db), data)


def test_completion_tools_match_reviewed_contract_and_cover_every_business_page():
    ensure_agent_tools_registered()
    document_spec = tool_registry.require("quality.list_documents")
    assert document_spec.public_dict()["result_kind"] == "knowledge_index"
    assert "不包含SOP正文" in document_spec.public_dict()["output_hint"]
    for operation in (
        "quality.get_deviation_statistics", "quality.get_capa_statistics",
        "quality.get_change_statistics", "quality.get_validation_statistics",
        "quality.get_cpv_statistics",
    ):
        assert tool_registry.require(operation).result_kind == "statistics"
    for handler, *_ in CASES:
        spec = tool_registry.require(f"quality.{handler}")
        assert not spec.write and not spec.human_decision_required
        assert spec.risk_level == "low"
        binding = api_binding_for_route("GET", f"/api/v1{spec.path}")
        assert binding is not None and spec.page_keys == binding.page_keys
        with pytest.raises(ValidationError):
            spec.input_model.model_validate({"page_size": 101})
    specs = [spec for spec in tool_registry.list() if spec.module == "quality"]
    expected = {
        p.page_key for p in PAGES_BY_MODULE["quality"] if "settings" not in p.page_key
    }
    assert len(specs) == 89 and len(expected) == 59
    assert {key for spec in specs for key in spec.page_keys} == expected


@pytest.mark.parametrize(
    ("input_type", "params"),
    [
        ("AnomalyListInput", {"year": 2029}),
        ("QcValidationListInput", {"year": 2025}),
        ("ReviewListInput", {"status": "approved"}),
        ("WorkbenchListInput", {"date_from": "not-a-date"}),
    ],
)
def test_invalid_completion_filters_are_rejected(input_type, params):
    with pytest.raises(ValidationError):
        getattr(tools, input_type).model_validate(params)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [
        DepartmentScope(is_all=True),
        DepartmentScope(is_all=False),
        DepartmentScope(is_all=False, department_names={"QC"}),
    ],
)
async def test_document_scope_is_never_widened_by_department_filter(monkeypatch, scope):
    dept_id, selected_id = uuid4(), uuid4()
    execute = AsyncMock(
        return_value=SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [dept_id])
        )
    )
    query = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        agent_queries, "resolve_user_department_scope", AsyncMock(return_value=scope)
    )
    monkeypatch.setattr(
        agent_queries.document_catalog_crud, "list_document_entries", query
    )
    actor_token = current_page_actor.set(SimpleNamespace(id=uuid4()))
    try:
        result = await agent_queries.list_documents(
            SimpleNamespace(execute=execute),
            department_id=selected_id,
            keyword=None,
            page=2,
            page_size=5,
        )
        assert result["items"] == []
        assert query.await_args.kwargs["department_id"] == selected_id
        assert query.await_args.kwargs["scope_dept_ids"] == (
            None if scope.is_all else [str(dept_id)] if scope.department_names else []
        )
        if scope.department_names:
            sql = execute.await_args.args[0].compile(dialect=postgresql.dialect())
            assert ["QC"] in sql.params.values()
            assert "is_deleted IS false" in str(sql)
        else:
            execute.assert_not_awaited()
    finally:
        current_page_actor.reset(actor_token)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("permissions", "scope_type", "all_visible"),
    [
        ([], "all", False),
        (["quality:validation_qa:write"], "all", True),
        (["quality:write"], "all", True),
        (["*"], "all", True),
        (["quality:validation_qa:write"], "self", False),
    ],
)
async def test_review_visibility_uses_trusted_actor_and_qa_permissions(
    monkeypatch, permissions, scope_type, all_visible
):
    actor = SimpleNamespace(id=uuid4())
    query = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        agent_queries, "resolve_user_permissions", AsyncMock(return_value=permissions)
    )
    monkeypatch.setattr(agent_queries.validation_review, "list_review_records", query)
    actor_token = current_page_actor.set(actor)
    scope_token = current_page_data_scope.set({"scope_type": scope_type})
    try:
        result = await agent_queries.list_validation_reviews(
            object(),
            keyword=None,
            status="completed",
            review_mode=None,
            page=1,
            page_size=5,
        )
        assert result["items"] == []
        assert query.await_args.kwargs["user_id"] == actor.id
        assert query.await_args.kwargs["all_visible"] is all_visible
    finally:
        current_page_data_scope.reset(scope_token)
        current_page_actor.reset(actor_token)


@pytest.mark.asyncio
async def test_scoped_reads_fail_closed_without_trusted_actor():
    token = current_page_actor.set(None)
    try:
        with pytest.raises(ForbiddenException):
            await agent_queries.list_documents(
                object(), department_id=None, keyword=None, page=1, page_size=5
            )
        with pytest.raises(ForbiddenException):
            await agent_queries.list_validation_reviews(
                object(),
                keyword=None,
                status=None,
                review_mode=None,
                page=1,
                page_size=5,
            )
    finally:
        current_page_actor.reset(token)


@pytest.mark.asyncio
async def test_oot_product_query_bounds_soft_deleted_records_and_literal_keyword():
    scalar = AsyncMock(return_value=0)
    scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
    result = await agent_queries.list_oot_limit_products(
        SimpleNamespace(scalar=scalar, scalars=scalars),
        keyword="产品%_",
        page=2,
        page_size=5,
    )
    assert result == {"items": [], "total": 0, "page": 2, "page_size": 5}
    for query in (scalar, scalars):
        compiled = query.await_args.args[0].compile(dialect=postgresql.dialect())
        assert "is_deleted IS false" in str(compiled)
        assert "%产品\\%\\_%" in compiled.params.values()
    compiled = scalars.await_args.args[0].compile(dialect=postgresql.dialect())
    assert "LIMIT" in str(compiled) and "OFFSET" in str(compiled)


@pytest.mark.asyncio
async def test_scoped_service_results_serialize_records_and_review_file_count(
    monkeypatch,
):
    now = datetime(2026, 10, 10, tzinfo=UTC)
    record_id = uuid4()
    document = SimpleNamespace(
        id=record_id,
        department_id=uuid4(),
        name="质量手册",
        code="QA-001",
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        agent_queries,
        "resolve_user_department_scope",
        AsyncMock(return_value=DepartmentScope(is_all=True)),
    )
    monkeypatch.setattr(
        agent_queries.document_catalog_crud,
        "list_document_entries",
        AsyncMock(return_value=([document], 1)),
    )
    review = SimpleNamespace(
        id=record_id,
        title="已有验证审核",
        review_mode="vp",
        status="completed",
        model_name=None,
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        agent_queries, "resolve_user_permissions", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        agent_queries.validation_review,
        "list_review_records",
        AsyncMock(return_value=([review], 1)),
    )
    files = AsyncMock(return_value=[object(), object()])
    monkeypatch.setattr(agent_queries.validation_review, "get_review_files", files)
    db = object()
    token = current_page_actor.set(SimpleNamespace(id=uuid4()))
    try:
        result = await agent_queries.list_documents(
            db, department_id=None, keyword=None, page=1, page_size=5
        )
        assert result["items"][0]["id"] == str(record_id)
        assert result["items"][0]["created_at"] == "2026-10-10T00:00:00Z"
        result = await agent_queries.list_validation_reviews(
            db, keyword=None, status=None, review_mode=None, page=1, page_size=5
        )
        assert result["items"][0]["file_count"] == 2
        assert result["items"][0]["status"] == "completed"
        files.assert_awaited_once_with(db, record_id)
    finally:
        current_page_actor.reset(token)
    product = SimpleNamespace(
        id=record_id,
        product_code="DR",
        product_name="多拉菌素",
        document_title="OOT限度通知单",
        created_at=now,
        updated_at=now,
    )
    result = await agent_queries.list_oot_limit_products(
        SimpleNamespace(
            scalar=AsyncMock(return_value=1),
            scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [product])),
        ),
        keyword=None,
        page=1,
        page_size=5,
    )
    assert result["items"][0]["product_code"] == "DR"
    assert result["items"][0]["updated_at"] == "2026-10-10T00:00:00Z"
