"""Production read-only Feishu mirror routes."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.core.response import ApiResponse
from app.core.secrets import decrypt_secret
from app.modules.production.models import (
    ProductionFeishuReadField,
    ProductionFeishuReadPageBinding,
    ProductionFeishuReadRecord,
    ProductionFeishuReadResource,
    ProductionFeishuReadSourceRoot,
    ProductionFeishuReadSyncRun,
)
from app.modules.production.repository import ProductionRepository
from app.platform.integrations.feishu.read_mirror import (
    ModuleFeishuReadMirrorService,
    ReadMirrorModels,
)
from app.platform.integrations.feishu.page_keys import validate_module_page_key
from app.core.exceptions import AppException

router = APIRouter()
MODELS = ReadMirrorModels(
    root=ProductionFeishuReadSourceRoot,
    resource=ProductionFeishuReadResource,
    field=ProductionFeishuReadField,
    record=ProductionFeishuReadRecord,
    binding=ProductionFeishuReadPageBinding,
    sync_run=ProductionFeishuReadSyncRun,
)


class SourceRootInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_type: str = Field(pattern="^(wiki|base)$")
    source_url: str = Field(min_length=1, max_length=2000)
    config_id: uuid.UUID | None = None


class BindingItem(BaseModel):
    resource_id: uuid.UUID
    tab_name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0
    is_default: bool = False
    is_enabled: bool = True
    visible_field_ids: list[str] = Field(default_factory=list)


class BindingReplace(BaseModel):
    bindings: list[BindingItem]


async def _service(db: AsyncSession, config_id: uuid.UUID | None = None) -> tuple[ModuleFeishuReadMirrorService, Any]:
    repo = ProductionRepository(db)
    config = (
        await repo.get_feishu_config_by_id(config_id)
        if config_id is not None
        else await repo.get_active_feishu_config()
    )
    if config is None or not config.app_id or not config.encrypted_app_secret:
        raise AppException(message="生产飞书应用凭据未配置", status_code=400)
    return (
        ModuleFeishuReadMirrorService(
            db,
            module_code="production",
            app_id=config.app_id,
            app_secret=decrypt_secret(config.encrypted_app_secret),
            models=MODELS,
        ),
        config,
    )


def _root_payload(item: Any) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "config_id": str(item.config_id),
        "name": item.name,
        "source_type": item.source_type,
        "source_url": item.source_url,
        "root_token": item.root_token,
        "is_active": item.is_active,
        "discovery_status": item.discovery_status,
        "last_discovered_at": item.last_discovered_at.isoformat() if item.last_discovered_at else None,
        "discovery_error": item.discovery_error,
    }


def _resource_payload(item: Any) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "source_root_id": str(item.source_root_id),
        "app_token": item.app_token,
        "table_id": item.table_id,
        "title": item.title,
        "source_path": item.source_path,
        "sync_status": item.sync_status,
        "sync_error": item.sync_error,
        "last_complete_sync_at": item.last_complete_sync_at.isoformat() if item.last_complete_sync_at else None,
    }


def _validate_page_key(page_key: str) -> None:
    validate_module_page_key(page_key, "production")


@router.get("/feishu-read/roots", response_model=ApiResponse)
async def list_read_roots(
    config_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    service, config = await _service(db, config_id)
    return ApiResponse(data=[_root_payload(item) for item in await service.list_roots(config.id)])


@router.post("/feishu-read/roots", response_model=ApiResponse)
async def create_read_root(
    payload: SourceRootInput,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    service, config = await _service(db, payload.config_id)
    item = await service.create_root(
        config_id=config.id,
        name=payload.name,
        source_type=payload.source_type,
        source_url=payload.source_url,
    )
    return ApiResponse(data=_root_payload(item))


@router.delete("/feishu-read/roots/{root_id}", response_model=ApiResponse)
async def delete_read_root(
    root_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    service, _ = await _service(db)
    await service.delete_root(root_id)
    return ApiResponse(data={"deleted": True})


@router.post("/feishu-read/roots/{root_id}/discover", response_model=ApiResponse)
async def discover_read_root(
    root_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    service, _ = await _service(db)
    return ApiResponse(data=[_resource_payload(item) for item in await service.discover_root(root_id)])


@router.get("/feishu-read/resources", response_model=ApiResponse)
async def list_read_resources(
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    service, _ = await _service(db)
    return ApiResponse(data=[_resource_payload(item) for item in await service.list_resources()])


@router.post("/feishu-read/resources/{resource_id}/sync", response_model=ApiResponse)
async def sync_read_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    service, _ = await _service(db)
    return ApiResponse(data=await service.sync_resource(resource_id))


@router.put("/feishu-read/page-bindings/{page_key:path}", response_model=ApiResponse)
async def replace_read_bindings(
    page_key: str,
    payload: BindingReplace,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    _validate_page_key(page_key)
    service, _ = await _service(db)
    return ApiResponse(data=await service.replace_bindings(page_key, [item.model_dump() for item in payload.bindings]))


@router.get("/page-data/{page_key}", response_model=ApiResponse)
async def get_read_page(
    page_key: str,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    _validate_page_key(page_key)
    service, _ = await _service(db)
    return ApiResponse(data=await service.page_data(page_key))


@router.get("/page-data/{page_key}/{binding_id}/records", response_model=ApiResponse)
async def get_read_page_records(
    page_key: str,
    binding_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    _validate_page_key(page_key)
    service, _ = await _service(db)
    return ApiResponse(data=await service.page_records(page_key=page_key, binding_id=binding_id, page=page, page_size=page_size, keyword=keyword))


@router.get("/page-data/{page_key}/{binding_id}/record/{record_id}/attachments/{field_id}/{file_token}")
async def download_read_attachment(
    page_key: str,
    binding_id: uuid.UUID,
    record_id: str,
    field_id: str,
    file_token: str,
    db: AsyncSession = Depends(get_db),
    _current_user: CurrentUser | None = Depends(get_current_user),
):
    _validate_page_key(page_key)
    service, _ = await _service(db)
    content, content_type, _disposition = await service.download_attachment(
        page_key=page_key,
        binding_id=binding_id,
        record_id=record_id,
        field_id=field_id,
        file_token=file_token,
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "no-store", "Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff"},
    )
