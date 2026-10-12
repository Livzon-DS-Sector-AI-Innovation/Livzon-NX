from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.regulatory_tracker import public_api


@pytest.mark.asyncio
async def test_document_public_query_preserves_filters_pagination_and_safe_fields(
    monkeypatch,
):
    doc = SimpleNamespace(
        id=uuid4(),
        title="原料药指南",
        publish_date=date(2026, 10, 10),
        is_new=True,
        source_site_name="CDE",
        summary_text="原始摘要",
        ai_summary="已有摘要",
        raw_data={"private": "must not return"},
    )
    query = AsyncMock(return_value=([doc], 21))
    monkeypatch.setattr(public_api.repository, "get_documents_with_filters", query)
    data = public_api.RegulatoryDocumentQuery(
        keyword="原料药",
        source_site="CDE",
        is_new=True,
        publish_date_from="2026-10-01",
        publish_date_to="2026-10-10",
        capture_date_from="2026-10-01",
        capture_date_to="2026-10-10",
        classification="指南",
        status_text="现行",
        page=2,
        page_size=10,
    )
    db = object()
    result = await public_api.list_regulatory_documents(db, data)
    query.assert_awaited_once_with(db=db, **data.model_dump())
    assert result.total == 21 and result.total_pages == 3
    assert result.page == 2 and result.page_size == 10
    payload = result.model_dump(mode="json")
    assert payload["items"][0]["publish_date"] == "2026-10-10"
    assert payload["items"][0]["summary_text"] == "原始摘要"
    assert payload["items"][0]["ai_summary"] == "已有摘要"
    assert "raw_data" not in payload["items"][0]
    query.return_value = ([], 0)
    empty = await public_api.list_regulatory_documents(
        db, public_api.RegulatoryDocumentQuery()
    )
    assert empty.items == [] and empty.total_pages == 0


@pytest.mark.parametrize(
    "invalid",
    [
        {"page_size": 101},
        {"page": 0},
        {"force": True},
        {"publish_date_from": "2026-10-10", "publish_date_to": "2026-10-01"},
        {"capture_date_from": "2026-10-10", "capture_date_to": "2026-10-01"},
    ],
)
def test_document_public_query_rejects_unbounded_refresh_and_reversed_dates(invalid):
    with pytest.raises(ValidationError):
        public_api.RegulatoryDocumentQuery.model_validate(invalid)
