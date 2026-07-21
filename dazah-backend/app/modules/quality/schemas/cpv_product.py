"""CPV Product schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProductStatus = Literal["active", "inactive"]


class CpvProductCreate(BaseModel):
    """创建产品请求"""

    name: str = Field(..., min_length=1, max_length=200, description="产品名称")
    specification: str | None = Field(default=None, max_length=200, description="规格")
    process_version: str | None = Field(default=None, max_length=50, description="工艺版本")
    status: ProductStatus = Field(default="active", description="状态")
    description: str | None = Field(default=None, description="备注描述")


class CpvProductUpdate(BaseModel):
    """更新产品请求"""

    name: str | None = Field(default=None, min_length=1, max_length=200, description="产品名称")
    specification: str | None = Field(default=None, max_length=200, description="规格")
    process_version: str | None = Field(default=None, max_length=50, description="工艺版本")
    status: ProductStatus | None = Field(default=None, description="状态")
    description: str | None = Field(default=None, description="备注描述")


class CpvProductResponse(BaseModel):
    """产品响应"""

    id: uuid.UUID
    name: str
    specification: str | None
    process_version: str | None
    status: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None

    model_config = {"from_attributes": True}


class CpvProductListResponse(CpvProductResponse):
    """产品列表响应（带统计）"""

    cpp_parameter_count: int = 0
    cqa_parameter_count: int = 0
    cpp_batch_count: int = 0
    cqa_batch_count: int = 0
    avg_value: float | None = None
    cpk_value: float | None = None
    abnormal_batch_count: int = 0
