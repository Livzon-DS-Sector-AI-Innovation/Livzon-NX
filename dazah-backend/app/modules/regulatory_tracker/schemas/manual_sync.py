"""Manual sync response schemas for regulatory tracker."""

from __future__ import annotations

from pydantic import BaseModel


class TrackerManualSyncTotalsRead(BaseModel):
    checked: int
    accepted: int
    inserted: int
    updated: int
    unchanged: int
    rejected: int


class TrackerManualSyncAnalysisRead(BaseModel):
    analyzed: int
    failed: int
    skipped: int


class TrackerManualSyncSiteResultRead(BaseModel):
    site_code: str
    site_name: str
    totals: TrackerManualSyncTotalsRead
    rejection_reasons: dict[str, int]
    error: str | None = None


class TrackerManualSyncBootstrapRead(BaseModel):
    created_sources: int
    created_channels: int
    site_count: int
    sites: list[str]


class TrackerManualSyncResultRead(BaseModel):
    bootstrap: TrackerManualSyncBootstrapRead
    totals: TrackerManualSyncTotalsRead
    sites: list[TrackerManualSyncSiteResultRead]
    analysis: TrackerManualSyncAnalysisRead


class TrackerManualSyncResponse(BaseModel):
    code: int
    message: str
    data: TrackerManualSyncResultRead
