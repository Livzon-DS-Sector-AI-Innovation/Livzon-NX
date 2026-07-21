"""Schemas for quality Feishu sync status and conflicts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class QualityPullSyncResult(BaseModel):
    entity_code: str | None = None
    entity_label: str | None = None
    synced: int = 0
    failed: int = 0
    conflicts: int = 0


class QualitySyncConflictItem(BaseModel):
    entity_type: Literal[
        "deviation",
        "capa",
        "deviation_investigation_push_record",
        "capa_plan_track",
    ]
    entity_label: str
    entity_id: uuid.UUID
    record_code: str
    record_title: str | None = None
    route_path: str
    feishu_base_table_id: str | None = None
    feishu_base_record_id: str | None = None
    feishu_sync_status: str
    feishu_last_sync_error: str | None = None
    feishu_last_sync_direction: str | None = None
    feishu_synced_at: datetime | None = None
    feishu_source_updated_at: datetime | None = None
    updated_at: datetime
    created_at: datetime
