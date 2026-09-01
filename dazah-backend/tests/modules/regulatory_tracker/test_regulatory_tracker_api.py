from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker.api import routes


def test_regulatory_tracker_router_exposes_read_and_analysis_operations() -> None:
    paths = {
        route.path for route in routes.router.routes if isinstance(route, APIRoute)
    }

    assert "/regulatory-tracker/summary" in paths
    assert "/regulatory-documents" in paths
    assert "/regulatory-documents/{doc_id}/read" in paths
    assert "/regulatory-documents/analyze" in paths
    assert "/sync-jobs" in paths


@pytest.mark.asyncio
async def test_list_documents_serializes_pagination_and_document_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    document = SimpleNamespace(
        id=document_id,
        source_id=uuid4(),
        channel_id=uuid4(),
        document_id="NMPA-001",
        title="药品注册管理办法",
        publish_date=None,
        status_text="有效",
        classification="法规",
        original_url="https://example.invalid/regulation",
        is_new=True,
        is_read=False,
        first_found_at=None,
        last_checked_at=None,
        created_at=None,
        ai_summary=None,
        ai_key_points=None,
        ai_relevance_score=None,
        ai_analyzed_at=None,
        ai_analysis_status="pending",
    )

    async def fake_get_documents(
        *args: object, **kwargs: object
    ) -> tuple[list[object], int]:
        assert kwargs["page"] == 2
        assert kwargs["page_size"] == 10
        return [document], 21

    repo = cast(object, getattr(routes, "repo"))
    monkeypatch.setattr(repo, "get_documents_with_filters", fake_get_documents)

    result = await routes.list_documents(
        keyword=None,
        source_site=None,
        publish_date_from=None,
        publish_date_to=None,
        capture_date_from=None,
        capture_date_to=None,
        status_text=None,
        classification=None,
        is_new=None,
        page=2,
        page_size=10,
        db=cast(AsyncSession, object()),
    )

    assert result.data.total == 21
    assert result.data.total_pages == 3
    assert result.data.items[0].id == document_id
    assert result.data.items[0].title == "药品注册管理办法"
