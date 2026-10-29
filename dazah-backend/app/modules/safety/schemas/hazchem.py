"""危化品与 MSDS 的请求 / 响应模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HazardousChemicalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="化学品名称")
    alias: str = Field(default="", max_length=200, description="别名/商品名")
    cas_no: str = Field(default="", max_length=60, description="CAS 号")
    category: str = Field(
        default="other",
        max_length=40,
        description="危险性类别: explosive/flammable_gas/oxidizing_gas/"
        "flammable_liquid/flammable_solid/self_reactive/oxidizing_liquid/"
        "organic_peroxide/toxic/corrosive/other",
    )
    hazard_statements: str = Field(
        default="", max_length=8000, description="危险性概述"
    )
    storage_requirements: str = Field(
        default="", max_length=8000, description="储存要求"
    )
    remark: str = Field(default="", max_length=8000, description="备注")


class HazardousChemicalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    alias: str | None = Field(default=None, max_length=200)
    cas_no: str | None = Field(default=None, max_length=60)
    category: str | None = Field(default=None, max_length=40)
    hazard_statements: str | None = Field(default=None, max_length=8000)
    storage_requirements: str | None = Field(default=None, max_length=8000)
    remark: str | None = Field(default=None, max_length=8000)


class HazardousChemicalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    alias: str
    cas_no: str
    category: str
    hazard_statements: str
    storage_requirements: str
    msds_file_path: str
    msds_file_name: str
    remark: str
    created_at: datetime
    updated_at: datetime


class HazardousChemicalListResponse(BaseModel):
    items: list[HazardousChemicalResponse]
    total: int
    page: int
    page_size: int


class ChemicalInventoryCreate(BaseModel):
    chemical_id: UUID = Field(description="危化品")
    workshop: str = Field(min_length=1, max_length=100, description="车间/库房")
    quantity: float = Field(ge=0, description="当前存量")
    upper_limit: float | None = Field(default=None, ge=0, description="存量上限")
    unit: str = Field(default="kg", max_length=30, description="单位")
    remark: str = Field(default="", max_length=8000, description="备注")


class ChemicalInventoryUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    upper_limit: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=30)
    remark: str | None = Field(default=None, max_length=8000)


class ChemicalInventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chemical_id: UUID
    chemical_name: str = ""
    category: str = ""
    workshop: str
    quantity: float
    upper_limit: float | None = None
    over_limit: bool = False
    over_pct: float | None = Field(
        default=None, description="超储幅度（%），未超储为 None"
    )
    unit: str
    remark: str
    updated_at: datetime


class ChemicalInventoryListResponse(BaseModel):
    items: list[ChemicalInventoryResponse]
    total: int
    page: int
    page_size: int


class ChemicalInventoryStatsResponse(BaseModel):
    total_entries: int
    over_limit_count: int
    limited_count: int
    by_category: dict[str, int] = Field(default_factory=dict)


class HazchemStatsResponse(BaseModel):
    chemicals_total: int
    msds_uploaded: int
    inventory: ChemicalInventoryStatsResponse


# ── MSDS 多附件 ──


class ChemicalMsdsFileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chemical_id: UUID
    file_name: str
    content_type: str
    size_bytes: int
    created_at: datetime
    created_by: UUID | None = None


class ChemicalMsdsFileListResponse(BaseModel):
    items: list[ChemicalMsdsFileItem]


class MsdsExtractionSuggestion(BaseModel):
    """MSDS 附件 AI 识别出的档案字段建议值（人工确认后才写入档案）。

    各字段为「识别到则填、未识别为 None」；不覆盖档案必填项 name 之外的
    任何空值以外的语义由前端确认弹窗决定。
    """

    name: str | None = Field(default=None, max_length=200)
    alias: str | None = Field(default=None, max_length=200)
    cas_no: str | None = Field(default=None, max_length=60)
    category: str | None = Field(default=None, max_length=40)
    category_label: str = Field(default="", description="危险性类别中文名")
    hazard_statements: str | None = Field(default=None, max_length=8000)
    storage_requirements: str | None = Field(default=None, max_length=8000)
    remark: str | None = Field(default=None, max_length=8000)


class ChemicalMsdsUploadResponse(BaseModel):
    """上传 MSDS 成功后的响应：附件 + 更新后的档案 + AI 识别建议。"""

    file: ChemicalMsdsFileItem
    chemical: HazardousChemicalResponse
    ai_suggestion: MsdsExtractionSuggestion | None = None
    ai_error: str | None = Field(
        default=None, description="AI 识别未执行/失败的原因（附件已保存成功）"
    )
