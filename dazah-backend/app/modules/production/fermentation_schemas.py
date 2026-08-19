"""Fermentation record Pydantic schemas."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Create ──
class FermentationCreate(BaseModel):
    batch_no: str = Field(..., description="批号")
    product_name: str = Field(default="L-苯丙氨酸", description="产品名称")
    fermenter: str = Field(..., description="发酵罐")
    entry_date: date = Field(..., description="进罐日期")
    discharge_date: Optional[date] = Field(None, description="放罐日期")
    cycle_1: Optional[float] = Field(None, description="周期1")
    cycle_2: Optional[float] = Field(None, description="周期2")
    cycle_3: Optional[float] = Field(None, description="周期3")
    cycle_4: Optional[float] = Field(None, description="周期4")
    cycle_5: Optional[float] = Field(None, description="周期5")
    cycle_6: Optional[float] = Field(None, description="周期6")
    tank_yield: Optional[float] = Field(None, description="罐产")
    status: str = Field(default="in_progress", description="状态")
    remarks: Optional[str] = Field(None, description="备注")
    attachment: Optional[str] = Field(None, description="附件")


# ── Update ──
class FermentationUpdate(BaseModel):
    batch_no: Optional[str] = Field(None, description="批号")
    fermenter: Optional[str] = Field(None, description="发酵罐")
    entry_date: Optional[date] = Field(None, description="进罐日期")
    discharge_date: Optional[date] = Field(None, description="放罐日期")
    cycle_1: Optional[float] = Field(None, description="周期1")
    cycle_2: Optional[float] = Field(None, description="周期2")
    cycle_3: Optional[float] = Field(None, description="周期3")
    cycle_4: Optional[float] = Field(None, description="周期4")
    cycle_5: Optional[float] = Field(None, description="周期5")
    cycle_6: Optional[float] = Field(None, description="周期6")
    tank_yield: Optional[float] = Field(None, description="罐产")
    status: Optional[str] = Field(None, description="状态")
    remarks: Optional[str] = Field(None, description="备注")
    attachment: Optional[str] = Field(None, description="附件")


# ── Response ──
class FermentationResponse(BaseModel):
    id: UUID
    batch_no: str
    product_name: str
    fermenter: str
    entry_date: date
    discharge_date: Optional[date] = None
    cycle_1: Optional[float] = None
    cycle_2: Optional[float] = None
    cycle_3: Optional[float] = None
    cycle_4: Optional[float] = None
    cycle_5: Optional[float] = None
    cycle_6: Optional[float] = None
    tank_yield: Optional[float] = None
    status: str
    remarks: Optional[str] = None
    attachment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Status Update ──
class FermentationStatusUpdate(BaseModel):
    status: str = Field(..., description="新状态")
