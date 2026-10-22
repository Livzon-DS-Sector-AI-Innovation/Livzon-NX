"""灭火器 / 消防栓点检的请求 / 响应模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

EquipmentType = Literal["extinguisher", "hydrant"]
InspectionItemResult = Literal["ok", "fail"]
InspectionSource = Literal["scan", "web"]
MonthStatus = Literal["inspected", "uninspected"]


class FireEquipmentItem(BaseModel):
    """一台消防器材（镜像投影行）。"""

    id: UUID
    equipment_type: str
    equipment_type_label: str
    equipment_no: str
    department: str
    location: str
    tab_name: str
    table_id: str
    record_id: str
    fields: dict[str, Any] = Field(default_factory=dict)
    last_inspected_at: datetime | None = None
    last_inspection_result: str | None = None
    month_status: str
    expiry_date: date | None = None
    expiry_days_left: int | None = None
    expiry_status: str | None = None
    last_synced_at: datetime | None = None


class FireEquipmentColumn(BaseModel):
    """台账页的动态列（与飞书多维表格字段对齐）。"""

    name: str
    kind: str


class FireEquipmentListResponse(BaseModel):
    items: list[FireEquipmentItem]
    columns: list[FireEquipmentColumn] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class FireEquipmentStats(BaseModel):
    """台账概览 + 镜像绑定/同步状态（页面顶栏一次取全）。"""

    total: int
    extinguisher_count: int
    hydrant_count: int
    inspected_this_month: int
    uninspected_this_month: int
    failed_this_month: int
    is_configured: bool = False
    writeback_enabled: bool = False
    expired_count: int = 0
    expiring_in_30_count: int = 0
    last_synced_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None


class ChecklistItem(BaseModel):
    """检查卡检查项（key 是契约，label 展示用）。"""

    key: str
    label: str


class ChecklistResponse(BaseModel):
    equipment_type: EquipmentType
    items: list[ChecklistItem] = Field(default_factory=list)


class FireInspectionItemInput(BaseModel):
    """单条检查项的提交值（label 由服务端按检查卡回填）。"""

    key: str
    result: InspectionItemResult
    remark: str | None = None


class CreateFireInspectionRequest(BaseModel):
    items: list[FireInspectionItemInput] = Field(min_length=1)
    abnormal_action: str | None = None
    inspected_at: datetime | None = None
    inspector_name: str | None = None
    source: InspectionSource = "web"


class FireInspectionRecordItem(BaseModel):
    """一条点检记录（检查项为当次快照）。"""

    id: UUID
    equipment_id: UUID
    equipment_type: str
    equipment_type_label: str
    equipment_no: str
    department: str
    location: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    result: str
    failed_items: list[dict[str, Any]] = Field(default_factory=list)
    abnormal_action: str | None = None
    inspector_name: str
    inspected_at: datetime
    source: str
    feishu_record_id: str | None = None
    created_at: datetime | None = None


class FireInspectionListResponse(BaseModel):
    items: list[FireInspectionRecordItem]
    total: int
    page: int
    page_size: int


class FireInspectionWritebackInitResponse(BaseModel):
    """一键初始化点检记录回写子表的结果。"""

    table_id: str
    table_name: str
    created: bool


class FireEquipmentDetailResponse(BaseModel):
    """扫码页 / 详情抽屉的一次性数据：器材 + 检查卡 + 最近记录。"""

    equipment: FireEquipmentItem
    checklist: list[ChecklistItem] = Field(default_factory=list)
    recent_inspections: list[FireInspectionRecordItem] = Field(
        default_factory=list
    )
