"""作业安全监护人名单的请求 / 响应模型（含 Excel 导入预览与结果）。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GuardianRosterBase(BaseModel):
    person_name: str = Field(min_length=1, max_length=100, description="监护人姓名")
    workshop: str = Field(min_length=1, max_length=100, description="车间/部门")
    phone: str | None = Field(default=None, max_length=32)
    position: str | None = Field(default=None, max_length=100)
    score: int | None = Field(default=None, ge=0, le=1000)
    exam_name: str | None = Field(default=None, max_length=100)
    exam_date: date | None = None
    remark: str | None = Field(default=None, max_length=200)


class GuardianRosterCreate(GuardianRosterBase):
    pass


class GuardianRosterUpdate(BaseModel):
    person_name: str | None = Field(default=None, min_length=1, max_length=100)
    workshop: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    position: str | None = Field(default=None, max_length=100)
    score: int | None = Field(default=None, ge=0, le=1000)
    exam_name: str | None = Field(default=None, max_length=100)
    exam_date: date | None = None
    remark: str | None = Field(default=None, max_length=200)


class GuardianRosterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    person_name: str
    workshop: str
    phone: str | None = None
    position: str | None = None
    score: int | None = None
    exam_name: str | None = None
    exam_date: date | None = None
    remark: str | None = None
    source_file: str | None = None
    created_at: datetime
    updated_at: datetime


class GuardianWorkshopCount(BaseModel):
    """车间分组计数（列表页车间卡片/筛选）。"""

    workshop: str
    count: int


class GuardianRosterListResponse(BaseModel):
    items: list[GuardianRosterResponse]
    total: int
    page: int
    page_size: int
    workshops: list[GuardianWorkshopCount] = Field(default_factory=list)


class GuardianImportSheetInfo(BaseModel):
    """导入预览：单个子表的解析结果。"""

    sheet: str
    row_count: int = 0
    workshops: list[str] = Field(default_factory=list)
    default_selected: bool = Field(
        default=False, description="是否默认勾选（识别为最优数据源）"
    )
    sample: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class GuardianImportPreview(BaseModel):
    sheets: list[GuardianImportSheetInfo] = Field(default_factory=list)
    duplicate_across_sheets: int = Field(
        default=0, description="跨子表重复人员合并的行数（全簿估算）"
    )
    current_total: int = Field(
        default=0, description="库内现有名单人数（导入后将被替换）"
    )
    merged_total: int = Field(
        default=0, description="合并去重后预计导入人数（全簿估算）"
    )


class GuardianImportResult(BaseModel):
    replaced: int = Field(default=0, description="本次导入替换前的库内人数")
    imported: int = Field(default=0, description="本次导入写入的人数")
    duplicates_merged: int = Field(default=0, description="文件内重复行合并数")
    skipped_sheets: list[dict[str, str]] = Field(default_factory=list)
    row_errors: list[dict[str, Any]] = Field(default_factory=list)
    archive_path: str | None = None
