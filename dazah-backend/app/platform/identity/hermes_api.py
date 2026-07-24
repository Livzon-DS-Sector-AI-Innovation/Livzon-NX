"""Internal Hermes control-plane APIs.

These endpoints are service-authenticated and intentionally carry metadata
only: no Feishu document bodies, tokens, or credentials are accepted.
"""

from __future__ import annotations

import hmac
import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.platform.audit.models import AuditLog
from app.platform.identity.models import User, UserModuleGrant

router = APIRouter(prefix="/internal/feishu", tags=["Hermes 飞书内部接口"])
logger = logging.getLogger(__name__)


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


async def build_access_snapshot(
    db: AsyncSession, settings: Settings
) -> dict[str, Any]:
    users = list(
        (
            await db.execute(
                select(User).where(User.is_deleted.is_(False)).order_by(User.id.asc())
            )
        )
        .scalars()
        .all()
    )
    grants = list(
        (
            await db.execute(
                select(UserModuleGrant).where(
                    UserModuleGrant.is_deleted.is_(False),
                    UserModuleGrant.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    grants_by_user: dict[str, list[UserModuleGrant]] = {}
    for grant in grants:
        grants_by_user.setdefault(str(grant.user_id), []).append(grant)
    items: list[dict[str, Any]] = []
    for user in users:
        user_grants = grants_by_user.get(str(user.id), [])
        permissions = {
            permission
            for grant in user_grants
            for permission in (grant.permissions or [])
            if permission.startswith("feishu.")
        }
        if user.role in {"admin", "system_admin"}:
            permissions.update(
                {"feishu.workspace.read_any", "feishu.workspace.write_any"}
            )
        items.append(
            {
                "local_user_id": str(user.id),
                "display_name": user.name,
                "user_id": user.feishu_user_id,
                "open_id": user.feishu_open_id,
                "union_id": user.feishu_union_id,
                "active": user.status == "active",
                "modules": sorted({grant.module_code for grant in user_grants}),
                "scopes": sorted(permissions),
                "grant_version": user.grant_version,
            }
        )
    return {
        "version": time.time_ns(),
        "generated_at": datetime.now(UTC).isoformat(),
        "users": items,
        "allowed_groups": [
            item.strip()
            for item in settings.LIVZON_FEISHU_ALLOWED_GROUPS.split(",")
            if item.strip()
        ],
    }


async def push_access_snapshot_to_hermes(db: AsyncSession) -> bool:
    settings = get_settings()
    if not settings.HERMES_INTERNAL_URL or not settings.HERMES_INTERNAL_TOKEN:
        return False
    snapshot = await build_access_snapshot(db, settings)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.put(
                f"{settings.HERMES_INTERNAL_URL.rstrip('/')}/internal/feishu/access-snapshot",
                headers={
                    "Authorization": f"Bearer {settings.HERMES_INTERNAL_TOKEN}"
                },
                json=snapshot,
            )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning(
            "Hermes access snapshot push failed: %s", type(exc).__name__
        )
        return False


@router.get("/access-snapshot", dependencies=[Depends(_require_internal)])
async def get_access_snapshot(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return await build_access_snapshot(db, settings)


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
