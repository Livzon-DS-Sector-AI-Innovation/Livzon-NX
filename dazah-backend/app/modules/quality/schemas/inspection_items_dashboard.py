"""Schemas for 质量检验-物品管理 仪表盘与库存不足推送。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemsStockAlertItem(BaseModel):
    """库存不足物料条目。"""

    record_id: str = ""
    name: str | None = None
    specification: str | None = None
    location: str | None = None
    current_stock: str | None = None
    warning_stock: str | None = None
    unit: str | None = None


class ItemsMonthlyPoint(BaseModel):
    """月度出入库量数据点。"""

    month: int = Field(..., ge=1, le=12, description="月份 1-12")
    inbound: float = 0
    outbound: float = 0


class ItemsDashboardResponse(BaseModel):
    """物品管理仪表盘统计。"""

    configured: bool = True
    total_items: int = 0
    alert_count: int = 0
    warning_source: str = "feishu"
    low_stock_items: list[ItemsStockAlertItem] = Field(default_factory=list)
    year: int | None = None
    monthly: list[ItemsMonthlyPoint] = Field(default_factory=list)
    last_sync_time: str | None = None


class PushLowStockResult(BaseModel):
    """库存不足一键推送结果。"""

    status: str = "sent"
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    item_count: int = 0
    message: str | None = None
