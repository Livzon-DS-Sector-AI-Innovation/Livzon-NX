"""Backfill existing regulatory tracker summaries to Chinese display text."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord
from app.modules.regulatory_tracker.models.regulatory_document import RegulatoryDocument
from app.modules.regulatory_tracker.services.content_summary_service import (
    fetch_detail_payload,
    generate_short_summary,
)
from app.modules.regulatory_tracker.services.tracker_sync_service import (
    TrackerSyncService,
)


async def backfill_document_summaries(
    db: AsyncSession,
    *,
    limit: int = 200,
    source_site_codes: Sequence[str] | None = None,
) -> dict[str, int]:
    """Backfill existing summary_text values using detail-page content."""
    effective_site_codes = tuple(
        source_site_codes or ("fda", "ema", "edqm", "eurlex", "ich", "who")
    )
    query = select(RegulatoryDocument).where(
        RegulatoryDocument.is_deleted == False,  # noqa: E712
        RegulatoryDocument.source_site_code.in_(effective_site_codes),
    )

    query = query.order_by(
        RegulatoryDocument.publish_date.desc().nullslast(),
        RegulatoryDocument.created_at.desc(),
    ).limit(limit)

    result = await db.execute(query)
    documents = list(result.scalars().all())

    stats = {
        "checked": len(documents),
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
    }

    for document in documents:
        raw_data = dict(document.raw_data or {})
        if not raw_data.get("detail_content") and document.source_url:
            detail_payload = await fetch_detail_payload(
                document.source_url,
                fallback_title=document.title,
            )
            if detail_payload:
                raw_data.update(detail_payload)

        derived_summary = await generate_short_summary(
            title=document.title,
            raw_data=raw_data,
            existing_summary=document.summary_text,
        )
        if not derived_summary:
            derived_summary = TrackerSyncService._derive_summary_text(
                CrawledRegulationRecord(
                    source_site=document.source_site_code or "",
                    document_id=document.document_id,
                    title=document.title,
                    original_url=document.source_url or document.original_url or "",
                    publish_date=document.publish_date,
                    effective_date=document.effective_date,
                    version=document.version_text,
                    summary=document.summary_text,
                    raw_data=raw_data,
                ),
                raw_data,
                document.source_site_name or document.source_site_code or "",
            )

        update_data: dict[str, Any] = {}
        if derived_summary and derived_summary != document.summary_text:
            update_data["summary_text"] = derived_summary
        if raw_data != (document.raw_data or {}):
            update_data["raw_data"] = raw_data

        if update_data:
            payload = {
                "title": document.title,
                "publish_date": document.publish_date,
                "status_text": document.status_text,
                "classification": document.classification,
                "source_site_code": document.source_site_code,
                "source_site_name": document.source_site_name,
                "source_url": document.source_url,
                "version_text": document.version_text,
                "effective_date": document.effective_date,
                "summary_text": update_data.get("summary_text", document.summary_text),
                "filter_status": document.filter_status,
                "filter_reason": document.filter_reason,
                "original_url": document.original_url,
                "raw_data": raw_data,
            }
            update_data["content_hash"] = repo.build_document_content_hash(payload)
            await repo.update_document(db, document.id, update_data)
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

    await db.commit()
    return stats
