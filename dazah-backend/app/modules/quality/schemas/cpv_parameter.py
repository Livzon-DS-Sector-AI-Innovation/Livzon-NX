"""CPV Parameter schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ParameterType = Literal["CPP", "CQA"]


class CpvParameterCreate(BaseModel):
    """创建参数请求"""

    parameter_type: ParameterType = Field(..., description="参数类型")
    name: str = Field(..., min_length=1, max_length=200, description="参数名称")
    code: str | None = Field(default=None, max_length=100, description="参数代码")
    unit: str | None = Field(default=None, max_length=50, description="单位")
    lower_limit: float | None = Field(default=None, description="标准下限")
    upper_limit: float | None = Field(default=None, description="标准上限")
    control_lower: float | None = Field(default=None, description="控制下限")
    control_upper: float | None = Field(default=None, description="控制上限")
    target_value: float | None = Field(default=None, description="目标值")
    is_enabled: bool = Field(default=True, description="是否启用")
    sort_order: int = Field(default=0, description="排序")


class CpvParameterUpdate(BaseModel):
    """更新参数请求"""

    name: str | None = Field(default=None, min_length=1, max_length=200, description="参数名称")
    code: str | None = Field(default=None, max_length=100, description="参数代码")
    unit: str | None = Field(default=None, max_length=50, description="单位")
    lower_limit: float | None = Field(default=None, description="标准下限")
    upper_limit: float | None = Field(default=None, description="标准上限")
    control_lower: float | None = Field(default=None, description="控制下限")
    control_upper: float | None = Field(default=None, description="控制上限")
    target_value: float | None = Field(default=None, description="目标值")
    is_enabled: bool | None = Field(default=None, description="是否启用")
    sort_order: int | None = Field(default=None, description="排序")


class CpvParameterResponse(BaseModel):
    """参数响应"""

    id: uuid.UUID
    product_id: uuid.UUID
    parameter_type: str
    name: str
    code: str | None
    unit: str | None
    lower_limit: float | None
    upper_limit: float | None
    control_lower: float | None
    control_upper: float | None
    target_value: float | None
    is_enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
