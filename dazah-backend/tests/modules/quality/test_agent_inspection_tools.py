from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.modules.quality import agent_tools as tools
from app.modules.quality.service import inspection
from app.platform.identity.data_scope import (
    DepartmentScope,
    current_page_actor,
    current_page_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "resource"),
    [
        ("list_lab_items", "lab_items"),
        ("list_lab_instruments", "lab_instruments"),
        ("list_finished_product_inspections", "finished_product_inspections"),
        ("list_solid_material_inspections", "solid_material_inspections"),
        ("list_liquid_material_inspections", "liquid_material_inspections"),
    ],
)
async def test_inspection_tools_forward_exact_resource_and_paging(
    monkeypatch, handler, resource
):
    query = AsyncMock(return_value=([], 6))
    monkeypatch.setattr(inspection, "list_resource_records", query)
    db = object()
    result = await getattr(tools, handler)(
        SimpleNamespace(db=db),
        tools.InspectionResourceListInput(keyword="检验", page=2, page_size=3),
    )
    query.assert_awaited_once_with(db, resource, keyword="检验", page=2, page_size=3)
    assert result == {"items": [], "total": 6, "page": 2, "page_size": 3}


@pytest.mark.asyncio
async def test_instrument_service_passes_department_clause_to_repository(monkeypatch):
    query = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(inspection.repository, "list_records", query)
    monkeypatch.setattr(
        inspection,
        "resolve_user_department_scope",
        AsyncMock(
            return_value=DepartmentScope(is_all=False, department_names={"QC"}),
        ),
    )
    page_token = current_page_key.set(
        "quality:inspection:inspection-instruments:inspection-instruments-equipment"
    )
    actor_token = current_page_actor.set(SimpleNamespace(id="actor", role="user"))
    try:
        result = await inspection.list_resource_records(
            object(),
            "lab_instruments",
            keyword=None,
            page=1,
            page_size=10,
        )
        assert result == ([], 0)
        clause = query.await_args.kwargs["scope_clause"]
        compiled = clause.compile(dialect=postgresql.dialect())
        assert "department" in str(compiled)
        assert ["QC"] in compiled.params.values()
    finally:
        current_page_key.reset(page_token)
        current_page_actor.reset(actor_token)


@pytest.mark.asyncio
async def test_instrument_page_without_actor_is_denied():
    token = current_page_key.set(
        "quality:inspection:inspection-instruments:inspection-instruments-equipment"
    )
    actor = current_page_actor.set(None)
    try:
        with pytest.raises(HTTPException) as error:
            await inspection.list_resource_records(
                object(),
                "lab_instruments",
                keyword=None,
                page=1,
                page_size=10,
            )
        assert error.value.status_code == 403
    finally:
        current_page_key.reset(token)
        current_page_actor.reset(actor)


@pytest.mark.asyncio
async def test_instrument_repository_applies_scope_to_count_and_rows():
    from app.modules.quality.models import LabInstrument
    from app.platform.identity.data_scope import department_in_clause

    clause = department_in_clause(
        LabInstrument.department,
        DepartmentScope(is_all=False, department_names={"QC"}),
    )
    execute = AsyncMock(
        side_effect=[
            SimpleNamespace(scalar_one=lambda: 1),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])),
        ]
    )
    result = await inspection.repository.list_records(
        SimpleNamespace(execute=execute),
        LabInstrument,
        search_fields=("name",),
        filters={},
        keyword=None,
        page=2,
        page_size=10,
        scope_clause=clause,
    )
    assert result == ([], 1)
    for call in execute.await_args_list:
        compiled = call.args[0].compile(dialect=postgresql.dialect())
        assert "department" in str(compiled)
        assert ["QC"] in compiled.params.values()
    compiled_rows = (
        execute.await_args_list[1].args[0].compile(dialect=postgresql.dialect())
    )
    assert "LIMIT" in str(compiled_rows) and "OFFSET" in str(compiled_rows)
