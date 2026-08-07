"""Internal Hermes control-plane APIs.

These endpoints are service-authenticated and intentionally carry metadata
only: no Feishu document bodies, tokens, or credentials are accepted.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.platform.audit.models import AuditLog
from app.platform.identity.models import User
from app.platform.identity.repository import (
    ExternalIdentityBindingRepository,
    ExternalIdentityConflictError,
    FeishuConfigRepository,
)

router = APIRouter(prefix="/internal/feishu", tags=["Hermes 飞书内部接口"])


def _require_internal(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.HERMES_INTERNAL_TOKEN
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid internal service token"
        )


class ExternalIdentityResolveRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    app_fingerprint: str = Field(min_length=1, max_length=255)
    external_user_id: str | None = Field(default=None, max_length=128)
    external_open_id: str | None = Field(default=None, max_length=128)
    external_union_id: str | None = Field(default=None, max_length=128)
    chat_id: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_identifier(self) -> ExternalIdentityResolveRequest:
        if not any(
            (self.external_user_id, self.external_open_id, self.external_union_id)
        ):
            raise ValueError("Feishu identity identifier is required")
        return self


@router.post("/identity/resolve", dependencies=[Depends(_require_internal)])
async def resolve_external_identity(
    payload: ExternalIdentityResolveRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    config = await FeishuConfigRepository().get_active(db)
    if config is None or config.app_id != payload.app_fingerprint:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Feishu application is not the active Hermes Gateway application",
        )
    try:
        binding = await ExternalIdentityBindingRepository().resolve(
            db,
            tenant_id=payload.tenant_id,
            platform="feishu",
            app_fingerprint=payload.app_fingerprint,
            external_user_id=payload.external_user_id,
            external_open_id=payload.external_open_id,
            external_union_id=payload.external_union_id,
        )
    except ExternalIdentityConflictError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Feishu identity identifiers are inconsistent",
        ) from exc
    if binding is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Feishu identity is not bound")
    user = await db.get(User, binding.local_user_id)
    if user is None or user.is_deleted or user.status != "active":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Bound local user is not active",
        )
    configured_groups = config.allowed_group_chat_ids or []
    allowed_groups = {
        item.strip()
        for item in (
            configured_groups
            or settings.LIVZON_FEISHU_ALLOWED_GROUPS.split(",")
        )
        if item.strip()
    }
    if payload.chat_id and payload.chat_id not in allowed_groups:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Feishu group is not admitted for Livzon Agent",
        )
    binding.last_seen_at = datetime.now(UTC)
    await db.flush()
    return {
        "subject": {
            # The binding tenant identifies the external Feishu application
            # namespace. Agent authorization must use the local user's tenant.
            "tenant_id": user.tenant_key or "default",
            "user_id": str(user.id),
            "display_name": user.name,
            "source": "feishu",
            "external_binding_id": str(binding.id),
        }
    }


class HermesAuditEvent(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    user_id: str | None = Field(default=None, max_length=128)
    resource_fingerprint: str | None = Field(default=None, max_length=512)
    capability: str = Field(min_length=1, max_length=100)
    risk: str = Field(min_length=1, max_length=32)
    confirmation: str | None = Field(default=None, max_length=32)
    result: str | None = Field(default=None, max_length=32)
    duration_ms: int | None = Field(default=None, ge=0)
    feishu_log_id: str | None = Field(default=None, max_length=128)
    impact_count: int | None = Field(default=None, ge=0)
    trace_id: str | None = Field(default=None, max_length=64)
    run_id: str | None = Field(default=None, max_length=64)


@router.post("/audit", dependencies=[Depends(_require_internal)], status_code=202)
async def ingest_audit_event(
    payload: HermesAuditEvent,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    existing = await db.scalar(
        select(AuditLog.id).where(
            AuditLog.request_id == payload.id,
            AuditLog.path == "/internal/feishu/audit",
        )
    )
    if existing is not None:
        return {"status": "accepted", "id": payload.id}
    db.add(
        AuditLog(
            request_id=payload.id,
            method="HERMES",
            path="/internal/feishu/audit",
            status_code=202,
            duration_ms=payload.duration_ms,
            resource_type="feishu_resource",
            action=payload.capability[:50],
            extra=payload.model_dump(exclude_none=True),
        )
    )
    await db.flush()
    return {"status": "accepted", "id": payload.id}


class ResourceChangeEvent(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    resource_fingerprint: str = Field(min_length=1, max_length=512)
    capability: str = Field(min_length=1, max_length=100)
    feishu_log_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=64)
    run_id: str | None = Field(default=None, max_length=64)


@router.post(
    "/resource-changes",
    dependencies=[Depends(_require_internal)],
    status_code=202,
)
async def ingest_resource_change(
    payload: ResourceChangeEvent,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    # Persist a metadata-only invalidation marker. Existing Feishu event
    # synchronization and reconciliation remain the authoritative data paths.
    existing = await db.scalar(
        select(AuditLog.id).where(
            AuditLog.request_id == payload.id,
            AuditLog.path == "/internal/feishu/resource-changes",
        )
    )
    if existing is not None:
        return {"status": "accepted", "id": payload.id}
    db.add(
        AuditLog(
            request_id=payload.id,
            method="HERMES",
            path="/internal/feishu/resource-changes",
            status_code=202,
            resource_type="feishu_resource_change",
            action="incremental_sync_requested",
            extra=payload.model_dump(exclude_none=True),
        )
    )
    await db.flush()
    return {"status": "accepted", "id": payload.id}
