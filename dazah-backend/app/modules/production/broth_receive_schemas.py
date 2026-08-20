"""发酵液接收记录 schemas"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BrothReceiveCreate(BaseModel):
    seq_no: int | None = Field(None, description="序号")
    received_batch: str = Field(..., description="接收批次")
    fermenter_no: str | None = Field(None, description="发酵罐号")
    fermentation_batch: str | None = Field(None, description="发酵批号")
    received_volume: str | None = Field(None, description="接收体积/重量")
    broth_od: float | None = Field(None, description="发酵液OD")
    titer_u_ml: float | None = Field(None, description="效价(u/mL)")
    titer_mg_l: float | None = Field(None, description="效价(mg/L)")
    broth_ph: float | None = Field(None, description="发酵液pH")
    temperature: float | None = Field(None, description="温度")
    mycelium_concentration: float | None = Field(None, description="菌丝浓度")
    residual_sugar: float | None = Field(None, description="残糖")
    amino_nitrogen: float | None = Field(None, description="氨基氮")
    receive_time: datetime | None = Field(None, description="进厂/接收时间")
    supplier_team: str | None = Field(None, description="供方班组")
    tank_bottom_residue: float | None = Field(None, description="罐底渣量")
    sample_no: str | None = Field(None, description="取样编号")
    sample_time: datetime | None = Field(None, description="取样时间")
    inspection_result: str | None = Field(None, description="检验结果")
    qualified: str | None = Field(None, description="合格判定")
    receive_loss: float | None = Field(None, description="接收损耗量")
    pipeline_leak_record: str | None = Field(None, description="输送管路跑冒滴漏记录")


class BrothReceiveUpdate(BaseModel):
    seq_no: int | None = Field(None, description="序号")
    received_batch: str | None = Field(None, description="接收批次")
    fermenter_no: str | None = Field(None, description="发酵罐号")
    fermentation_batch: str | None = Field(None, description="发酵批号")
    received_volume: str | None = Field(None, description="接收体积/重量")
    broth_od: float | None = Field(None, description="发酵液OD")
    titer_u_ml: float | None = Field(None, description="效价(u/mL)")
    titer_mg_l: float | None = Field(None, description="效价(mg/L)")
    broth_ph: float | None = Field(None, description="发酵液pH")
    temperature: float | None = Field(None, description="温度")
    mycelium_concentration: float | None = Field(None, description="菌丝浓度")
    residual_sugar: float | None = Field(None, description="残糖")
    amino_nitrogen: float | None = Field(None, description="氨基氮")
    receive_time: datetime | None = Field(None, description="进厂/接收时间")
    supplier_team: str | None = Field(None, description="供方班组")
    tank_bottom_residue: float | None = Field(None, description="罐底渣量")
    sample_no: str | None = Field(None, description="取样编号")
    sample_time: datetime | None = Field(None, description="取样时间")
    inspection_result: str | None = Field(None, description="检验结果")
    qualified: str | None = Field(None, description="合格判定")
    receive_loss: float | None = Field(None, description="接收损耗量")
    pipeline_leak_record: str | None = Field(None, description="输送管路跑冒滴漏记录")


class BrothReceiveResponse(BaseModel):
    id: UUID
    seq_no: int | None = None
    received_batch: str
    fermenter_no: str | None = None
    fermentation_batch: str | None = None
    received_volume: str | None = None
    broth_od: float | None = None
    titer_u_ml: float | None = None
    titer_mg_l: float | None = None
    broth_ph: float | None = None
    temperature: float | None = None
    mycelium_concentration: float | None = None
    residual_sugar: float | None = None
    amino_nitrogen: float | None = None
    receive_time: datetime | None = None
    supplier_team: str | None = None
    tank_bottom_residue: float | None = None
    sample_no: str | None = None
    sample_time: datetime | None = None
    inspection_result: str | None = None
    qualified: str | None = None
    receive_loss: float | None = None
    pipeline_leak_record: str | None = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
