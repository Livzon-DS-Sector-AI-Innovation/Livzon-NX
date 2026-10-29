"""Workshop schemas."""

import re
from datetime import datetime

from pydantic import BaseModel, Field

# 与设备模块各接口车间参数一致的代码格式（api WORKSHOP_QUERY 同源）
WORKSHOP_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,8}[a-z0-9]$")


class WorkshopSummary(BaseModel):
    """车间摘要（工作台车间块与飞书配置页清单数据源）"""

    code: str = Field(description="车间代码（如 101-1 / dlz）")
    name: str = Field(description="车间显示名（如 101一车间）")
    is_enabled: bool = Field(description="是否启用")


class WorkshopAdminSummary(BaseModel):
    """车间管理页条目（含停用车间的完整清单）"""

    code: str = Field(description="车间代码（创建后不可改）")
    name: str = Field(description="车间显示名")
    is_enabled: bool = Field(description="是否启用")
    created_at: datetime = Field(description="登记时间")


class WorkshopCreateRequest(BaseModel):
    """新增车间请求"""

    code: str = Field(
        ...,
        min_length=2,
        max_length=10,
        pattern=WORKSHOP_CODE_PATTERN.pattern,
        description=(
            "车间代码：2~10 位小写字母/数字，可带 -序号（如 204 / 204-1 / dlz），"
            "创建后不可改"
        ),
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="车间显示名（如 204一车间 / 动力站）",
    )


class WorkshopUpdateRequest(BaseModel):
    """更新车间请求（改名/启停；代码不可改）"""

    name: str | None = Field(
        default=None, min_length=1, max_length=50, description="车间显示名"
    )
    is_enabled: bool | None = Field(default=None, description="启用/停用")
