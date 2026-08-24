"""OOT limit management schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OotLimitProductBase(BaseModel):
    """Shared OOT limit product fields."""

    product_code: str = Field(..., description="产品编码")
    product_name: str = Field(..., description="产品名称")
    document_title: str = Field(..., description="通知单标题")
    document_year: int | None = Field(default=None, description="年份")
    version_label: str | None = Field(default=None, description="版本标签")
    source_file_name: str | None = Field(default=None, description="源文件名")
    remark: str | None = Field(default=None, description="备注")


class CreateOotLimitProductRequest(OotLimitProductBase):
    """Create OOT limit product request."""


class UpdateOotLimitProductRequest(BaseModel):
    """Update OOT limit product request."""

    product_code: str | None = None
    product_name: str | None = None
    document_title: str | None = None
    document_year: int | None = None
    version_label: str | None = None
    source_file_name: str | None = None
    remark: str | None = None


class OotLimitProductOut(OotLimitProductBase):
    """OOT limit product output."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OotLimitItemBase(BaseModel):
    """Shared OOT limit item fields."""

    product_id: UUID = Field(..., description="产品ID")
    display_order: int = Field(..., ge=1, description="显示顺序")
    item_group: str | None = Field(default=None, description="一级项目")
    item_name: str = Field(..., description="项目名称")
    standard_value: str = Field(..., description="标准值")
    oot_limit_value: str = Field(..., description="OOT限度")
    remark: str | None = Field(default=None, description="备注")


class CreateOotLimitItemRequest(OotLimitItemBase):
    """Create OOT limit item request."""


class UpdateOotLimitItemRequest(BaseModel):
    """Update OOT limit item request."""

    product_id: UUID | None = None
    display_order: int | None = Field(default=None, ge=1)
    item_group: str | None = None
    item_name: str | None = None
    standard_value: str | None = None
    oot_limit_value: str | None = None
    remark: str | None = None


class OotLimitItemOut(OotLimitItemBase):
    """OOT limit item output."""

    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
