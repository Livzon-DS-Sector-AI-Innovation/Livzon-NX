from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.procurement import agent_tools as tools
from app.modules.procurement.material_source import MaterialSourceNotConfiguredError


@pytest.mark.asyncio
async def test_material_catalog_forwards_filters_without_exposing_source_config(
    monkeypatch,
):
    query = AsyncMock(return_value=([], 13, object()))
    monkeypatch.setattr(tools, "list_material_catalog", query)
    db = object()
    data = tools.MaterialCatalogInput(
        keyword="糖", material_code="M001", page=2, page_size=5
    )
    result = await tools.list_material_catalog_records(SimpleNamespace(db=db), data)
    assert result == {"data": [], "meta": {"page": 2, "page_size": 5, "total": 13}}
    query.assert_awaited_once_with(db, **data.model_dump())
    query.side_effect = MaterialSourceNotConfiguredError("物料数据源尚未配置")
    with pytest.raises(HTTPException) as error:
        await tools.list_material_catalog_records(SimpleNamespace(db=db), data)
    assert error.value.status_code == 404
    assert error.value.detail == "物料数据源尚未配置"


@pytest.mark.asyncio
async def test_contract_summary_is_paginated_read(monkeypatch):
    query = AsyncMock(return_value=([], 2))
    monkeypatch.setattr(tools, "list_contract_records", query)
    data = tools.ContractRecordsInput(keyword="供应", page_size=5)
    db = object()
    result = await tools.list_contract_record_summaries(SimpleNamespace(db=db), data)
    query.assert_awaited_once_with(db, **data.model_dump())
    assert result == {"data": [], "meta": {"page": 1, "page_size": 5, "total": 2}}
