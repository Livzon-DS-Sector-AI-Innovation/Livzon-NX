"""Compatibility wrapper around the registry-based tracker sync flow."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.models import DataChannel, DataSource
from app.modules.regulatory_tracker.services.ai_analysis_service import (
    analyze_documents_by_ids,
    analyze_new_documents,
)
from app.modules.regulatory_tracker.services.site_target_service import (
    build_site_target_summary,
    ensure_default_site_targets,
)
from app.modules.regulatory_tracker.services.tracker_sync_service import (
    TrackerSyncService,
)

logger = logging.getLogger(__name__)


def _resolve_analysis_limit(sync_result: dict[str, Any]) -> int:
    totals = sync_result.get("totals") or {}
    accepted = int(totals.get("accepted") or 0)
    inserted = int(totals.get("inserted") or 0)
    updated = int(totals.get("updated") or 0)
    return max(accepted, inserted + updated, 0)


async def run_all_sites(
    db: AsyncSession,
    *,
    recent_days: int = 2,
    analyze: bool = True,
) -> dict[str, Any]:
    """Run the registry-based sync flow for all registered sites.

    ``analyze=False`` 时只抓取入库、不做内嵌 AI 分析（供 00:10 夜间抓取任务
    使用，分析由 02:00 独立任务统一执行）；手动触发保持默认
    ``analyze=True`` 的抓取+分析语义。
    """
    service = TrackerSyncService(db, recent_days=recent_days)
    bootstrap_result = await ensure_default_site_targets(db)
    sync_result = await service.run_all_sites(
        site_targets=bootstrap_result.site_targets
    )
    changed_document_ids = sync_result.get("changed_document_ids") or []
    analysis_result = {"analyzed": 0, "failed": 0, "skipped": 0}
    if analyze:
        analysis_limit = _resolve_analysis_limit(sync_result)
        if changed_document_ids:
            analysis_result = await analyze_documents_by_ids(
                db,
                [
                    uuid.UUID(document_id)
                    for document_id in changed_document_ids[:50]
                    if document_id
                ],
            )
        elif analysis_limit > 0:
            analysis_result = await analyze_new_documents(
                db, limit=min(max(analysis_limit, 1), 50)
            )
    await db.commit()
    return {
        **sync_result,
        "bootstrap": build_site_target_summary(bootstrap_result),
        "analysis": analysis_result,
    }


async def run_sync_job(
    db: AsyncSession,
    source: DataSource,
    channel: DataChannel,
    job_type: str,
    start_page: int = 1,
    end_page: int | None = None,
    headless: bool = True,
) -> dict[str, Any]:
    """Execute a sync job while keeping the legacy entrypoint stable.

    The page-related parameters are kept for backwards compatibility and are
    currently not used by the registry-based ingestion flow.
    """
    del start_page, end_page, headless

    job = await repo.create_sync_job(
        db,
        {
            "source_id": source.id,
            "channel_id": channel.id,
            "job_type": job_type,
            "status": "running",
            "started_at": datetime.now(UTC),
        },
    )

    error_message: str | None = None
    status = "success"
    totals = {
        "checked": 0,
        "accepted": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }

    try:
        site_code = source.code.lower()
        service = TrackerSyncService(db)
        site_result = await service.run_site(
            site_code,
            source=source,
            channel=channel,
        )
        totals = site_result["totals"]
        error_message = site_result.get("error")
        changed_document_ids = site_result.get("changed_document_ids") or []
        analysis_limit = max(
            int(totals.get("accepted") or 0), int(totals.get("inserted") or 0)
        )
        if changed_document_ids:
            analysis_result = await analyze_documents_by_ids(
                db,
                [
                    uuid.UUID(document_id)
                    for document_id in changed_document_ids[:20]
                    if document_id
                ],
            )
        else:
            analysis_result = (
                await analyze_new_documents(db, limit=min(max(analysis_limit, 1), 20))
                if analysis_limit > 0
                else {"analyzed": 0, "failed": 0, "skipped": 0}
            )
        if error_message:
            status = "failed"
    except Exception as exc:
        logger.exception(
            "同步任务异常: source=%s channel=%s", source.code, channel.code
        )
        status = "failed"
        error_message = str(exc)
        analysis_result = {"analyzed": 0, "failed": 0, "skipped": 0}

    await repo.update_sync_job(
        db,
        job.id,
        {
            "status": status,
            "finished_at": datetime.now(UTC),
            "checked_count": totals["checked"],
            "new_count": totals["inserted"],
            "updated_count": totals["updated"],
            "error_message": error_message,
        },
    )
    await db.commit()

    return {
        "job_id": str(job.id),
        "status": status,
        "checked": totals["checked"],
        "accepted": totals["accepted"],
        "inserted": totals["inserted"],
        "updated": totals["updated"],
        "unchanged": totals["unchanged"],
        "rejected": totals["rejected"],
        "new": totals["inserted"],
        "failed": 1 if error_message else 0,
        "error": error_message,
        "analysis": analysis_result,
    }
