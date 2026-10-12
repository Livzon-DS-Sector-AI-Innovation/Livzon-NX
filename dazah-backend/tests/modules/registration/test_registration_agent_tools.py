from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.core.exceptions import ForbiddenException
from app.modules.registration import agent_tools as tools


class Record(BaseModel):
    name: str


class Sheet(BaseModel):
    sheet_key: str
    records: list[Record]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "dependency", "field"),
    [
        ("list_project_ledger", "ProjectLedgerWorkbookService", "records"),
        ("list_declaration_progress", "DeclarationProgressWorkbookService", "records"),
        ("list_certificates", "CertificateWorkbookService", "rows"),
    ],
)
async def test_sheet_queries_bound_response_and_preserve_service_authorization(
    monkeypatch,
    handler,
    dependency,
    field,
):
    # The business service owns row permissions; the adapter only pages its response.
    detail = Sheet(
        sheet_key="domestic-associated-review",
        records=[Record(name="A"), Record(name="B")],
    )
    if field == "rows":

        class CertificateSheet(BaseModel):
            rows: list[Record]

        detail = CertificateSheet(rows=detail.records)
    query = AsyncMock(return_value=detail)
    monkeypatch.setattr(
        tools, dependency, lambda db: SimpleNamespace(get_sheet_detail=query)
    )
    data = tools.SheetInput(sheet_key="domestic-associated-review", page=2, page_size=1)
    result = await getattr(tools, handler)(SimpleNamespace(db=object()), data)
    assert result[field] == [{"name": "B"}]
    assert result["meta"] == {"page": 2, "page_size": 1, "total": 2}
    query.assert_awaited_once_with(data.sheet_key)
    query.side_effect = ForbiddenException("无权访问子表")
    with pytest.raises(ForbiddenException):
        await getattr(tools, handler)(SimpleNamespace(db=object()), data)


@pytest.mark.asyncio
async def test_fee_query_does_not_return_unbounded_records(monkeypatch):
    query = AsyncMock(return_value=[Record(name=str(i)) for i in range(4)])
    monkeypatch.setattr(
        tools, "RegistrationFeeService", lambda db: SimpleNamespace(list_entries=query)
    )
    result = await tools.list_fees(
        SimpleNamespace(db=object()),
        tools.FeeListInput(year=2026, page_size=2),
    )
    assert result["data"] == [{"name": "0"}, {"name": "1"}]
    assert result["meta"]["total"] == 4
    assert query.await_args.kwargs["year"] == 2026
    assert "page" not in query.await_args.kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "input_type", "dependency", "method", "filters", "paged_service"),
    [
        (
            "list_authorization_letters",
            "AuthorizationListInput",
            "AuthorizationLetterService",
            "list_letters",
            {"product_name": "多拉菌素", "preparation_unit": "制剂公司"},
            True,
        ),
        (
            "list_inspection_contacts",
            "InspectionContactInput",
            "RegistrationFeeService",
            "list_inspection_contacts",
            {"keyword": "外检"},
            False,
        ),
        (
            "list_knowledge_articles",
            "KnowledgeListInput",
            "RegistrationKnowledgeService",
            "list_articles",
            {"country": "中国", "tags": "注册", "is_published": True},
            False,
        ),
    ],
)
async def test_completion_queries_forward_filters_and_bound_results(
    monkeypatch, handler, input_type, dependency, method, filters, paged_service
):
    records = [Record(name="A"), Record(name="B"), Record(name="C")]
    query = AsyncMock(return_value=([records[1]], 3) if paged_service else records)
    monkeypatch.setattr(
        tools, dependency, lambda db: SimpleNamespace(**{method: query})
    )
    data = getattr(tools, input_type)(page=2, page_size=1, **filters)
    result = await getattr(tools, handler)(SimpleNamespace(db=object()), data)
    assert result == {
        "data": [{"name": "B"}],
        "meta": {"page": 2, "page_size": 1, "total": 3},
    }
    for key, value in filters.items():
        assert query.await_args.kwargs[key] == value
    if paged_service:
        assert query.await_args.kwargs["page"] == 2
        assert query.await_args.kwargs["page_size"] == 1
    else:
        assert "page" not in query.await_args.kwargs
    query.side_effect = ForbiddenException("无查询权限")
    with pytest.raises(ForbiddenException):
        await getattr(tools, handler)(SimpleNamespace(db=object()), data)


@pytest.mark.asyncio
async def test_regulation_query_uses_owning_module_public_api(monkeypatch):
    from app.modules.regulatory_tracker.schemas.tracker_page import (
        TrackerLedgerPageRead,
    )

    result = TrackerLedgerPageRead(
        items=[], total=0, page=2, page_size=10, total_pages=0
    )
    query = AsyncMock(return_value=result)
    monkeypatch.setattr(tools, "list_regulatory_documents", query)
    db = object()
    data = tools.RegulatoryDocumentQuery(keyword="原料药", page=2, page_size=10)
    payload = await tools.list_registration_regulatory_documents(
        SimpleNamespace(db=db), data
    )
    query.assert_awaited_once_with(db, data)
    assert payload == result.model_dump(mode="json")


def test_registration_bindings_cover_all_business_pages():
    from app.modules.agent.tool_registration import ensure_agent_tools_registered
    from app.modules.agent.tools import tool_registry
    from app.platform.identity.page_policy import PAGES_BY_MODULE

    ensure_agent_tools_registered()
    specs = [s for s in tool_registry.list() if s.module == "registration"]
    expected = {
        p.page_key
        for p in PAGES_BY_MODULE["registration"]
        if "settings" not in p.page_key
    }
    assert len(specs) == 9
    assert len(expected) == 20
    assert {key for spec in specs for key in spec.page_keys} == expected
    assert all(not spec.write for spec in specs)
