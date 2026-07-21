"""Pydantic contracts for OOS/OOT management and OOT limits."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OosOotType = Literal["OOS", "OOT"]
OosOotStatus = Literal["open", "investigating", "closed"]


class OosOotEntityOut(BaseModel):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OosOotRecordBase(BaseModel):
    record_code: str = Field(min_length=1, max_length=50, description="记录编号")
    record_type: OosOotType = Field(description="记录类型")
    title: str = Field(min_length=1, max_length=200, description="事件标题")
    department: str | None = Field(default=None, max_length=100, description="责任部门")
    product_name: str | None = Field(
        default=None, max_length=200, description="产品名称"
    )
    batch_no: str | None = Field(default=None, max_length=100, description="批号")
    test_item: str | None = Field(default=None, max_length=500, description="检验项目")
    specification: str | None = Field(default=None, description="标准规定")
    test_result: str | None = Field(default=None, description="检验结果")
    discovered_date: date | None = Field(default=None, description="发现日期")
    description: str | None = Field(default=None, description="事件描述")


class CreateOosOotRecordRequest(OosOotRecordBase):
    pass


class UpdateOosOotRecordRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    product_name: str | None = Field(default=None, max_length=200)
    batch_no: str | None = Field(default=None, max_length=100)
    test_item: str | None = Field(default=None, max_length=500)
    specification: str | None = None
    test_result: str | None = None
    discovered_date: date | None = None
    description: str | None = None
    corrective_actions: str | None = None


class CloseOosOotRecordRequest(BaseModel):
    investigation_result: str = Field(min_length=1, description="调查结论")
    corrective_actions: str | None = Field(default=None, description="纠正预防措施")


class OosOotRecordOut(OosOotRecordBase, OosOotEntityOut):
    investigation_result: str | None
    corrective_actions: str | None
    status: OosOotStatus
    closed_at: datetime | None


class OotLimitProductBase(BaseModel):
    product_code: str = Field(min_length=1, max_length=100, description="产品编码")
    product_name: str = Field(min_length=1, max_length=200, description="产品名称")
    document_no: str | None = Field(
        default=None, max_length=100, description="标准文件编号"
    )
    document_version: str | None = Field(
        default=None, max_length=50, description="标准文件版本"
    )
    is_active: bool = Field(default=True, description="是否启用")
    remark: str | None = Field(default=None, description="备注")


class CreateOotLimitProductRequest(OotLimitProductBase):
    pass


class UpdateOotLimitProductRequest(BaseModel):
    product_code: str | None = Field(default=None, min_length=1, max_length=100)
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    document_no: str | None = Field(default=None, max_length=100)
    document_version: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    remark: str | None = None


class OotLimitItemBase(BaseModel):
    display_order: int = Field(default=1, ge=1, description="显示顺序")
    item_group: str | None = Field(default=None, max_length=100, description="项目分组")
    item_name: str = Field(min_length=1, max_length=500, description="项目名称")
    specification: str | None = Field(default=None, description="标准规定")
    oot_limit: str = Field(min_length=1, description="OOT限度")
    remark: str | None = Field(default=None, description="备注")


class CreateOotLimitItemRequest(OotLimitItemBase):
    pass


class UpdateOotLimitItemRequest(BaseModel):
    display_order: int | None = Field(default=None, ge=1)
    item_group: str | None = Field(default=None, max_length=100)
    item_name: str | None = Field(default=None, min_length=1, max_length=500)
    specification: str | None = None
    oot_limit: str | None = Field(default=None, min_length=1)
    remark: str | None = None


class OotLimitProductOut(OotLimitProductBase, OosOotEntityOut):
    pass


class OotLimitItemOut(OotLimitItemBase, OosOotEntityOut):
    product_id: UUID


class OosOotPageMeta(BaseModel):
    page: int
    page_size: int
    total: int


class OosOotRecordResponse(BaseModel):
    code: int
    message: str
    data: OosOotRecordOut
    meta: dict[str, object] | None = None


class OosOotRecordListResponse(BaseModel):
    code: int
    message: str
    data: list[OosOotRecordOut]
    meta: OosOotPageMeta


class OotLimitProductResponse(BaseModel):
    code: int
    message: str
    data: OotLimitProductOut
    meta: dict[str, object] | None = None


class OotLimitProductListResponse(BaseModel):
    code: int
    message: str
    data: list[OotLimitProductOut]
    meta: dict[str, object] | None = None


class OotLimitItemResponse(BaseModel):
    code: int
    message: str
    data: OotLimitItemOut
    meta: dict[str, object] | None = None


class OotLimitItemListResponse(BaseModel):
    code: int
    message: str
    data: list[OotLimitItemOut]
    meta: dict[str, object] | None = None


class OosOotFeishuSyncOut(BaseModel):
    resource_code: str
    entity_code: str
    record_id: str
    table_id: str
    synced_at: datetime


class OosOotFeishuSyncResponse(BaseModel):
    code: int
    message: str
    data: OosOotFeishuSyncOut
    meta: dict[str, object] | None = None
