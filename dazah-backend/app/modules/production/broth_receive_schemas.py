"""发酵液接收记录 schemas"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class BrothReceiveCreate(BaseModel):
    seq_no: Optional[int] = Field(None, description="序号")
    received_batch: str = Field(..., description="接收批次")
    fermenter_no: Optional[str] = Field(None, description="发酵罐号")
    fermentation_batch: Optional[str] = Field(None, description="发酵批号")
    received_volume: Optional[str] = Field(None, description="接收体积/重量")
    broth_od: Optional[float] = Field(None, description="发酵液OD")
    titer_u_ml: Optional[float] = Field(None, description="效价(u/mL)")
    titer_mg_l: Optional[float] = Field(None, description="效价(mg/L)")
    broth_ph: Optional[float] = Field(None, description="发酵液pH")
    temperature: Optional[float] = Field(None, description="温度")
    mycelium_concentration: Optional[float] = Field(None, description="菌丝浓度")
    residual_sugar: Optional[float] = Field(None, description="残糖")
    amino_nitrogen: Optional[float] = Field(None, description="氨基氮")
    receive_time: Optional[datetime] = Field(None, description="进厂/接收时间")
    supplier_team: Optional[str] = Field(None, description="供方班组")
    tank_bottom_residue: Optional[float] = Field(None, description="罐底渣量")
    sample_no: Optional[str] = Field(None, description="取样编号")
    sample_time: Optional[datetime] = Field(None, description="取样时间")
    inspection_result: Optional[str] = Field(None, description="检验结果")
    qualified: Optional[str] = Field(None, description="合格判定")
    receive_loss: Optional[float] = Field(None, description="接收损耗量")
    pipeline_leak_record: Optional[str] = Field(None, description="输送管路跑冒滴漏记录")


class BrothReceiveUpdate(BaseModel):
    seq_no: Optional[int] = Field(None, description="序号")
    received_batch: Optional[str] = Field(None, description="接收批次")
    fermenter_no: Optional[str] = Field(None, description="发酵罐号")
    fermentation_batch: Optional[str] = Field(None, description="发酵批号")
    received_volume: Optional[str] = Field(None, description="接收体积/重量")
    broth_od: Optional[float] = Field(None, description="发酵液OD")
    titer_u_ml: Optional[float] = Field(None, description="效价(u/mL)")
    titer_mg_l: Optional[float] = Field(None, description="效价(mg/L)")
    broth_ph: Optional[float] = Field(None, description="发酵液pH")
    temperature: Optional[float] = Field(None, description="温度")
    mycelium_concentration: Optional[float] = Field(None, description="菌丝浓度")
    residual_sugar: Optional[float] = Field(None, description="残糖")
    amino_nitrogen: Optional[float] = Field(None, description="氨基氮")
    receive_time: Optional[datetime] = Field(None, description="进厂/接收时间")
    supplier_team: Optional[str] = Field(None, description="供方班组")
    tank_bottom_residue: Optional[float] = Field(None, description="罐底渣量")
    sample_no: Optional[str] = Field(None, description="取样编号")
    sample_time: Optional[datetime] = Field(None, description="取样时间")
    inspection_result: Optional[str] = Field(None, description="检验结果")
    qualified: Optional[str] = Field(None, description="合格判定")
    receive_loss: Optional[float] = Field(None, description="接收损耗量")
    pipeline_leak_record: Optional[str] = Field(None, description="输送管路跑冒滴漏记录")


class BrothReceiveResponse(BaseModel):
    id: UUID
    seq_no: Optional[int] = None
    received_batch: str
    fermenter_no: Optional[str] = None
    fermentation_batch: Optional[str] = None
    received_volume: Optional[str] = None
    broth_od: Optional[float] = None
    titer_u_ml: Optional[float] = None
    titer_mg_l: Optional[float] = None
    broth_ph: Optional[float] = None
    temperature: Optional[float] = None
    mycelium_concentration: Optional[float] = None
    residual_sugar: Optional[float] = None
    amino_nitrogen: Optional[float] = None
    receive_time: Optional[datetime] = None
    supplier_team: Optional[str] = None
    tank_bottom_residue: Optional[float] = None
    sample_no: Optional[str] = None
    sample_time: Optional[datetime] = None
    inspection_result: Optional[str] = None
    qualified: Optional[str] = None
    receive_loss: Optional[float] = None
    pipeline_leak_record: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
