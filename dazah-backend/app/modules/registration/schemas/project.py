"""Project module aggregate schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectChildPage(BaseModel):
    """Single child page route under project module."""

    key: str = Field(..., description="页面键")
    name: str = Field(..., description="页面名称")
    path: str = Field(..., description="前端路由")


class ProjectApiEndpoint(BaseModel):
    """Single backend API endpoint metadata."""

    key: str = Field(..., description="接口键")
    name: str = Field(..., description="接口名称")
    method: str = Field(..., description="HTTP 方法")
    path: str = Field(..., description="接口路径")


class ProjectModuleOverviewItem(BaseModel):
    """Single sub-module summary under project module."""

    key: str = Field(..., description="模块键")
    name: str = Field(..., description="模块名称")
    description: str = Field(..., description="模块说明")
    path: str = Field(..., description="前端路由")
    workbook_name: str = Field(..., description="工作簿名称")
    updated_at: datetime | None = Field(None, description="最近更新时间")
    total_records: int = Field(..., description="记录总数")
    sheet_count: int = Field(..., description="子页数量")
    child_pages: list[ProjectChildPage] = Field(
        default_factory=list, description="子页面列表"
    )
    api_endpoints: list[ProjectApiEndpoint] = Field(
        default_factory=list, description="相关接口列表"
    )


class ProjectOverview(BaseModel):
    """Aggregate overview for project parent page."""

    module_name: str = Field(..., description="父级模块名称")
    path: str = Field(..., description="父级前端路由")
    modules: list[ProjectModuleOverviewItem] = Field(
        default_factory=list, description="子模块总览"
    )
