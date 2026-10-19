"""页面飞书多维表格镜像的请求 / 响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── 配置 ──


class PageFeishuSubTable(BaseModel):
    """附加子表页签（主绑定是第一个页签，本结构描述其余页签）。"""

    table_id: str
    tab_name: str
    hidden_field_names: list[str] = Field(default_factory=list)


class PageFeishuConfigItem(BaseModel):
    """一个镜像页的表格绑定（未配置时也返回，便于设置页展示全部可配页面）。"""

    page_key: str
    page_name: str
    route_path: str
    app_token: str | None = None
    table_id: str | None = None
    view_id: str | None = None
    hidden_field_names: list[str] = Field(default_factory=list)
    workshop_aliases: dict[str, str] = Field(default_factory=dict)
    sub_tables: list[PageFeishuSubTable] = Field(default_factory=list)
    is_enabled: bool = True
    is_configured: bool = False
    is_mirrored: bool = True
    last_synced_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    last_sync_record_count: int | None = None
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: datetime | None = None
    last_test_field_count: int | None = None
    last_test_record_count: int | None = None


class PageFeishuConfigListResponse(BaseModel):
    items: list[PageFeishuConfigItem]


class UpdatePageFeishuConfigRequest(BaseModel):
    app_token: str | None = None
    table_id: str | None = None
    view_id: str | None = None
    hidden_field_names: list[str] | None = None
    workshop_aliases: dict[str, str] | None = None
    sub_tables: list[PageFeishuSubTable] | None = None
    is_enabled: bool | None = None
    is_mirrored: bool | None = None


class PageFeishuFieldSummary(BaseModel):
    name: str
    kind: str
    editable: bool


class PageFeishuConfigTestResult(BaseModel):
    success: bool
    message: str
    checked_at: datetime
    field_count: int = 0
    record_count: int = 0
    fields: list[PageFeishuFieldSummary] = Field(default_factory=list)


class ResolvePageFeishuUrlRequest(BaseModel):
    url: str = Field(min_length=1)


class ResolvedFeishuTable(BaseModel):
    table_id: str
    table_name: str


class ResolvedPageFeishuUrl(BaseModel):
    app_token: str
    table_id: str | None = None
    view_id: str | None = None
    is_wiki: bool = False
    tables: list[ResolvedFeishuTable] = Field(default_factory=list)


# ── 数据 ──


class PageTableColumn(BaseModel):
    field_id: str
    name: str
    type: int
    kind: str
    is_primary: bool
    options: list[str] = Field(default_factory=list)
    editable: bool


class PageTableRecord(BaseModel):
    record_id: str
    fields: dict[str, Any] = Field(default_factory=dict)


class PageTableRecordCondition(BaseModel):
    """查询表单的多条件筛选单元（JSON 数组传入，字段间 AND）。

    ``op``：日期字段支持 ``gte``/``lte``（ISO 文本比较，构成时间范围）；
    ``neq`` 表示「不等于且含未填写」（到期下钻：关闭状态 ≠ 已关闭）；
    其余按 ``eq`` 语义处理。
    """

    field: str = Field(min_length=1)
    value: str = Field(min_length=1)
    op: str = Field(default="eq", pattern="^(eq|neq|gte|lte)$")


class PageTableRecordsResponse(BaseModel):
    page_key: str
    page_name: str
    columns: list[PageTableColumn] = Field(default_factory=list)
    records: list[PageTableRecord] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    truncated: bool = False


class PageTableStatBucket(BaseModel):
    key: str
    count: int


class PageTableStatGroup(BaseModel):
    field: str
    kind: str
    mode: str
    buckets: list[PageTableStatBucket] = Field(default_factory=list)


class PageTableDueSummary(BaseModel):
    """未关闭记录按「目标完成日期」的到期分布（仪表盘到期卡片）。"""

    overdue: int = 0
    within_7: int = 0
    within_15: int = 0
    within_30: int = 0


class PageTableStatsResponse(BaseModel):
    page_key: str
    page_name: str
    total: int = 0
    groups: list[PageTableStatGroup] = Field(default_factory=list)
    due_summary: PageTableDueSummary | None = None


class PageTableFieldValueCount(BaseModel):
    """字段可选值（用于筛选下拉框的选项与计数）。"""

    value: str
    count: int


class PageTableFieldValuesResponse(BaseModel):
    page_key: str
    field: str
    table_id: str
    values: list[PageTableFieldValueCount] = Field(default_factory=list)


class PageTableTab(BaseModel):
    """多页签页面的一个子表页签。"""

    table_id: str
    tab_name: str
    is_primary: bool = False
    record_count: int = 0


class PageTableTabListResponse(BaseModel):
    page_key: str
    page_name: str
    tabs: list[PageTableTab] = Field(default_factory=list)


class UpdatePageTableRecordRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class PageTableAttachmentItem(BaseModel):
    file_token: str
    name: str
    size: int | None = None
    type: str = ""


class PageTableAttachmentUploadResponse(BaseModel):
    record_id: str
    field_name: str
    attachments: list[PageTableAttachmentItem] = Field(default_factory=list)
