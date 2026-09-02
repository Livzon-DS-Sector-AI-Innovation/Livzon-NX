"""LLM configuration API endpoints."""

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.identity.deps import AdminUser

from .capabilities import (
    LLMCapabilities,
    detect_model_capabilities,
    probe_api_base_url,
)
from .config import LLMConfigModel
from .encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from .exceptions import LLMConfigError

router = APIRouter(prefix="/llm/configs", tags=["LLM Configuration"])


class LLMConfigCreate(BaseModel):
    """Request body for creating LLM config."""

    config_name: str = Field(..., max_length=128)
    api_base_url: str = Field(..., max_length=500)
    api_key: str = Field(..., max_length=500)
    model_name: str = Field(..., max_length=128)
    temperature: float = Field(default=0.1, ge=0, le=2)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    is_active: bool = False
    enable_thinking: bool = Field(
        default=False, description="是否开启思考模式（返回 reasoning_content）"
    )
    custom_context: str | None = Field(
        default=None, description="自定义上下文提示词（追加到系统提示词末尾）"
    )
    context_window_tokens: int = Field(
        default=200000, ge=1000, le=4000000, description="上下文窗口大小（token）"
    )
    compress_threshold: float = Field(
        default=0.8, ge=0.1, le=1.0, description="上下文压缩阈值（比例）"
    )
    stream_output: bool = Field(default=True, description="是否流式输出")
    notes: str | None = None


class LLMConfigUpdate(BaseModel):
    """Request body for updating LLM config."""

    config_name: str | None = Field(None, max_length=128)
    api_base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=500)
    model_name: str | None = Field(None, max_length=128)
    temperature: float | None = Field(None, ge=0, le=2)
    timeout_seconds: int | None = Field(None, ge=10, le=600)
    is_active: bool | None = None
    enable_thinking: bool | None = None
    custom_context: str | None = None
    context_window_tokens: int | None = Field(None, ge=1000, le=4000000)
    compress_threshold: float | None = Field(None, ge=0.1, le=1.0)
    stream_output: bool | None = None
    notes: str | None = None


class LLMConfigResponse(BaseModel):
    """Response body for LLM config (never returns raw API key)."""

    id: str
    config_name: str
    config_type: str
    capabilities: list[str]
    api_base_url: str
    api_key_masked: str
    model_name: str
    temperature: float
    timeout_seconds: int
    is_active: bool
    enable_thinking: bool
    custom_context: str | None
    context_window_tokens: int
    compress_threshold: float
    stream_output: bool
    notes: str | None
    created_at: str
    updated_at: str


class LLMCapabilityDetectionResponse(BaseModel):
    status: str = "ok"
    config_type: str
    capabilities: list[str]
    detail: str


class LLMConfigProbeRequest(BaseModel):
    """Unsaved LLM configuration connectivity test."""

    probe_type: Literal["url", "model"]
    api_base_url: str = Field(..., max_length=500)
    api_key: str = Field(..., min_length=1, max_length=500)
    model_name: str | None = Field(None, max_length=128)
    timeout_seconds: int = Field(default=120, ge=10, le=600)

    @model_validator(mode="after")
    def require_model_for_model_probe(self) -> "LLMConfigProbeRequest":
        if self.probe_type == "model" and not self.model_name:
            raise ValueError("模型连通性测试需要模型名称")
        return self


class LLMConfigProbeResponse(BaseModel):
    status: str = "ok"
    probe_type: Literal["url", "model"]
    config_type: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    detail: str


def _capability_names(config_type: str) -> list[str]:
    if config_type == "vision":
        return ["text", "document", "image"]
    return ["text", "document"]


def _detection_response(
    capabilities: LLMCapabilities,
) -> LLMCapabilityDetectionResponse:
    capability_names = _capability_names(capabilities.config_type)
    detail = (
        "已检测到文本、文档和图片理解能力"
        if capabilities.supports_vision
        else "已检测到文本和文档能力，模型不接受图片输入"
    )
    return LLMCapabilityDetectionResponse(
        config_type=capabilities.config_type,
        capabilities=capability_names,
        detail=detail,
    )


def _to_response(config: LLMConfigModel) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=str(config.id),
        config_name=config.config_name,
        config_type=config.config_type,
        capabilities=_capability_names(config.config_type),
        api_base_url=config.api_base_url,
        api_key_masked=mask_api_key(config.encrypted_api_key),
        model_name=config.model_name,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        is_active=config.is_active,
        enable_thinking=config.enable_thinking,
        custom_context=config.custom_context,
        context_window_tokens=config.context_window_tokens,
        compress_threshold=config.compress_threshold,
        stream_output=config.stream_output,
        notes=config.notes,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


async def _detect_capabilities(
    *,
    api_base_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: int,
) -> LLMCapabilities:
    try:
        return await detect_model_capabilities(
            api_base_url=api_base_url,
            api_key=api_key,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
        )
    except LLMConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _probe_url(*, api_base_url: str, api_key: str, timeout_seconds: int) -> None:
    try:
        await probe_api_base_url(
            api_base_url=api_base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    except LLMConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _deactivate_other_configs(
    db: AsyncSession, *, exclude_id: uuid.UUID | None = None
) -> None:
    query = update(LLMConfigModel).where(LLMConfigModel.is_deleted.is_(False))
    if exclude_id is not None:
        query = query.where(LLMConfigModel.id != exclude_id)
    await db.execute(query.values(is_active=False))


@router.get("", response_model=list[LLMConfigResponse])
async def list_configs(
    config_type: str | None = Query(None, pattern="^(text|vision)$"),
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> Any:
    """List all LLM configurations."""
    query = select(LLMConfigModel).where(LLMConfigModel.is_deleted.is_(False))

    if config_type:
        query = query.where(LLMConfigModel.config_type == config_type)

    query = query.order_by(LLMConfigModel.created_at.desc())

    result = await db.execute(query)
    configs = result.scalars().all()

    return [_to_response(config) for config in configs]


@router.post("", response_model=LLMConfigResponse, status_code=201)
async def create_config(
    data: LLMConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> Any:
    """Create a new LLM configuration (admin only)."""
    capabilities = await _detect_capabilities(
        api_base_url=data.api_base_url,
        api_key=data.api_key,
        model_name=data.model_name,
        timeout_seconds=data.timeout_seconds,
    )
    if data.is_active:
        await _deactivate_other_configs(db)

    config = LLMConfigModel(
        config_name=data.config_name,
        config_type=capabilities.config_type,
        api_base_url=data.api_base_url,
        encrypted_api_key=encrypt_api_key(data.api_key),
        model_name=data.model_name,
        temperature=data.temperature,
        timeout_seconds=data.timeout_seconds,
        is_active=data.is_active,
        enable_thinking=data.enable_thinking,
        custom_context=data.custom_context,
        context_window_tokens=data.context_window_tokens,
        compress_threshold=data.compress_threshold,
        stream_output=data.stream_output,
        notes=data.notes,
        created_by=current_user.id if current_user else None,
        updated_by=current_user.id if current_user else None,
    )

    db.add(config)
    await db.flush()
    return _to_response(config)


@router.get("/{config_id}", response_model=LLMConfigResponse)
async def get_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> Any:
    """Get a specific LLM configuration."""
    result = await db.execute(
        select(LLMConfigModel).where(
            LLMConfigModel.id == uuid.UUID(config_id),
            LLMConfigModel.is_deleted.is_(False),
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    return _to_response(config)


@router.put("/{config_id}", response_model=LLMConfigResponse)
async def update_config(
    config_id: str,
    data: LLMConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> Any:
    """Update an LLM configuration (admin only)."""
    result = await db.execute(
        select(LLMConfigModel).where(
            LLMConfigModel.id == uuid.UUID(config_id),
            LLMConfigModel.is_deleted.is_(False),
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    update_data = data.model_dump(exclude_unset=True)
    candidate_api_key = str(update_data.get("api_key") or "")
    if not candidate_api_key:
        candidate_api_key = decrypt_api_key(config.encrypted_api_key)
    capabilities = await _detect_capabilities(
        api_base_url=str(update_data.get("api_base_url") or config.api_base_url),
        api_key=candidate_api_key,
        model_name=str(update_data.get("model_name") or config.model_name),
        timeout_seconds=int(
            update_data.get("timeout_seconds") or config.timeout_seconds
        ),
    )
    update_data["config_type"] = capabilities.config_type

    if data.is_active is True:
        await _deactivate_other_configs(db, exclude_id=config.id)

    # Encrypt API key if provided
    if "api_key" in update_data:
        update_data["encrypted_api_key"] = encrypt_api_key(update_data.pop("api_key"))

    for field, value in update_data.items():
        setattr(config, field, value)

    config.updated_by = current_user.id if current_user else None

    await db.flush()
    result = await db.execute(
        select(LLMConfigModel)
        .where(
            LLMConfigModel.id == config.id,
            LLMConfigModel.is_deleted.is_(False),
        )
        .execution_options(populate_existing=True)
    )
    refreshed_config = result.scalar_one()
    return _to_response(refreshed_config)


@router.delete("/{config_id}", status_code=204)
async def delete_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> None:
    """Soft delete an LLM configuration (admin only)."""
    result = await db.execute(
        select(LLMConfigModel).where(
            LLMConfigModel.id == uuid.UUID(config_id),
            LLMConfigModel.is_deleted.is_(False),
        )
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.is_deleted = True
    config.updated_by = current_user.id if current_user else None
    await db.flush()


async def _detect_saved_config(
    db: AsyncSession, config: LLMConfigModel
) -> LLMCapabilityDetectionResponse:
    capabilities = await _detect_capabilities(
        api_base_url=config.api_base_url,
        api_key=decrypt_api_key(config.encrypted_api_key),
        model_name=config.model_name,
        timeout_seconds=config.timeout_seconds,
    )
    if config.config_type != capabilities.config_type:
        config.config_type = capabilities.config_type
        await db.flush()
    return _detection_response(capabilities)


@router.post("/{config_id}/test", response_model=LLMCapabilityDetectionResponse)
async def test_saved_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> Any:
    result = await db.execute(
        select(LLMConfigModel).where(
            LLMConfigModel.id == uuid.UUID(config_id),
            LLMConfigModel.is_deleted.is_(False),
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")
    return await _detect_saved_config(db, config)


@router.post("/probe", response_model=LLMConfigProbeResponse)
async def probe_config(
    data: LLMConfigProbeRequest,
    current_user: AdminUser = None,
) -> Any:
    """Test an unsaved API URL or model without persisting its credential."""
    if data.probe_type == "url":
        await _probe_url(
            api_base_url=data.api_base_url,
            api_key=data.api_key,
            timeout_seconds=data.timeout_seconds,
        )
        return LLMConfigProbeResponse(
            probe_type="url",
            detail="API URL 与密钥连通正常",
        )

    capabilities = await _detect_capabilities(
        api_base_url=data.api_base_url,
        api_key=data.api_key,
        model_name=data.model_name or "",
        timeout_seconds=data.timeout_seconds,
    )
    detection = _detection_response(capabilities)
    return LLMConfigProbeResponse(
        probe_type="model",
        config_type=detection.config_type,
        capabilities=detection.capabilities,
        detail=f"模型连通正常；{detection.detail}",
    )


@router.post("/test", response_model=LLMCapabilityDetectionResponse)
async def test_connection(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
) -> Any:
    """Detect the active model's text and vision capabilities."""
    result = await db.execute(
        select(LLMConfigModel)
        .where(
            LLMConfigModel.is_active.is_(True),
            LLMConfigModel.is_deleted.is_(False),
        )
        .order_by(LLMConfigModel.updated_at.desc())
        .limit(1)
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="没有已激活的 LLM 配置")
    return await _detect_saved_config(db, config)
