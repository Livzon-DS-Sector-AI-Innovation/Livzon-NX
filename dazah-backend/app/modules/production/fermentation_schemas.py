"""Fermentation record Pydantic schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Create ──
class FermentationCreate(BaseModel):
    batch_no: str = Field(..., description="批号")
    product_name: str = Field(default="L-苯丙氨酸", description="产品名称")
    fermenter: str = Field(..., description="发酵罐")
    entry_date: date = Field(..., description="进罐日期")
    discharge_date: date | None = Field(None, description="放罐日期")
    cycle_1: float | None = Field(None, description="周期1")
    cycle_2: float | None = Field(None, description="周期2")
    cycle_3: float | None = Field(None, description="周期3")
    cycle_4: float | None = Field(None, description="周期4")
    cycle_5: float | None = Field(None, description="周期5")
    cycle_6: float | None = Field(None, description="周期6")
    tank_yield: float | None = Field(None, description="罐产")
    status: str = Field(default="in_progress", description="状态")
    remarks: str | None = Field(None, description="备注")
    attachment: str | None = Field(None, description="附件")


# ── Update ──
class FermentationUpdate(BaseModel):
    batch_no: str | None = Field(None, description="批号")
    fermenter: str | None = Field(None, description="发酵罐")
    entry_date: date | None = Field(None, description="进罐日期")
    discharge_date: date | None = Field(None, description="放罐日期")
    cycle_1: float | None = Field(None, description="周期1")
    cycle_2: float | None = Field(None, description="周期2")
    cycle_3: float | None = Field(None, description="周期3")
    cycle_4: float | None = Field(None, description="周期4")
    cycle_5: float | None = Field(None, description="周期5")
    cycle_6: float | None = Field(None, description="周期6")
    tank_yield: float | None = Field(None, description="罐产")
    status: str | None = Field(None, description="状态")
    remarks: str | None = Field(None, description="备注")
    attachment: str | None = Field(None, description="附件")


# ── Response ──
class FermentationResponse(BaseModel):
    id: UUID
    batch_no: str
    product_name: str
    fermenter: str
    entry_date: date
    discharge_date: date | None = None
    cycle_1: float | None = None
    cycle_2: float | None = None
    cycle_3: float | None = None
    cycle_4: float | None = None
    cycle_5: float | None = None
    cycle_6: float | None = None
    tank_yield: float | None = None
    status: str
    remarks: str | None = None
    attachment: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Status Update ──
class FermentationStatusUpdate(BaseModel):
    status: str = Field(..., description="新状态")
