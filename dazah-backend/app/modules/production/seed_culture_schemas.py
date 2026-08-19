"""摇瓶种子制备记录 Pydantic schemas."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SeedCultureCreate(BaseModel):
    batch_no: str = Field(..., description="摇瓶批号")
    product_name: str = Field(default="", description="产品名称")
    prepare_date: Optional[date] = Field(None, description="配制日期")
    glucose_batch: Optional[str] = Field(None, description="葡萄糖/批号")
    corn_starch_batch: Optional[str] = Field(None, description="玉米淀粉/批号")
    corn_syrup_batch: Optional[str] = Field(None, description="玉米浆/批号")
    ammonium_sulfate_batch: Optional[str] = Field(None, description="硫酸铵/批号")
    soybean_meal_batch: Optional[str] = Field(None, description="黄豆饼粉/批号")
    calcium_carbonate_batch: Optional[str] = Field(None, description="碳酸钙/批号")
    prepare_operator: Optional[str] = Field(None, description="配制操作人/复核人")
    sterilization_operator: Optional[str] = Field(None, description="种子消毒人员")
    ph_before_adjust: Optional[float] = Field(None, description="调前PH")
    ph_after_adjust: Optional[float] = Field(None, description="调后PH")
    ph_after_sterilization: Optional[float] = Field(None, description="消后PH")
    reducing_sugar: Optional[float] = Field(None, description="还原糖")
    total_sugar: Optional[float] = Field(None, description="总糖")
    amino_nitrogen: Optional[float] = Field(None, description="氨基氮")
    strain_tube_no: Optional[str] = Field(None, description="冻管菌号")
    shaker_setup_operator: Optional[str] = Field(None, description="上摇床摆东西人员")
    shaker_no: Optional[str] = Field(None, description="摇床编号")
    shaker_start_date: Optional[date] = Field(None, description="上摇床日期")
    inoculation_operator: Optional[str] = Field(None, description="接种人员/复核人")
    tool_no: Optional[str] = Field(None, description="用具编号")
    merge_time: Optional[datetime] = Field(None, description="并瓶时间")
    merge_count: Optional[int] = Field(None, description="并瓶数量(瓶)")
    merge_cycle: Optional[str] = Field(None, description="并瓶周期")
    merge_ph: Optional[float] = Field(None, description="并瓶PH")
    merge_bacteria_density: Optional[float] = Field(None, description="并瓶菌浓")
    merge_total_sugar: Optional[float] = Field(None, description="并瓶总糖")
    merge_reducing_sugar: Optional[float] = Field(None, description="并瓶还原糖")
    merge_amino_nitrogen: Optional[float] = Field(None, description="并瓶氨基氮")
    tank_setup_operator: Optional[str] = Field(None, description="进罐摆东西人员")
    cylinder_no: Optional[str] = Field(None, description="钢瓶编号")
    merge_operator: Optional[str] = Field(None, description="并瓶操作人/复核人")
    workshop_inoculation_operator: Optional[str] = Field(None, description="车间接种人员")
    tank_remarks: Optional[str] = Field(None, description="备注（罐号）")
    tank_yield: Optional[float] = Field(None, description="罐产")
    remarks: Optional[str] = Field(None, description="备注")


class SeedCultureUpdate(BaseModel):
    batch_no: Optional[str] = Field(None, description="摇瓶批号")
    product_name: Optional[str] = Field(None, description="产品名称")
    prepare_date: Optional[date] = Field(None, description="配制日期")
    glucose_batch: Optional[str] = Field(None, description="葡萄糖/批号")
    corn_starch_batch: Optional[str] = Field(None, description="玉米淀粉/批号")
    corn_syrup_batch: Optional[str] = Field(None, description="玉米浆/批号")
    ammonium_sulfate_batch: Optional[str] = Field(None, description="硫酸铵/批号")
    soybean_meal_batch: Optional[str] = Field(None, description="黄豆饼粉/批号")
    calcium_carbonate_batch: Optional[str] = Field(None, description="碳酸钙/批号")
    prepare_operator: Optional[str] = Field(None, description="配制操作人/复核人")
    sterilization_operator: Optional[str] = Field(None, description="种子消毒人员")
    ph_before_adjust: Optional[float] = Field(None, description="调前PH")
    ph_after_adjust: Optional[float] = Field(None, description="调后PH")
    ph_after_sterilization: Optional[float] = Field(None, description="消后PH")
    reducing_sugar: Optional[float] = Field(None, description="还原糖")
    total_sugar: Optional[float] = Field(None, description="总糖")
    amino_nitrogen: Optional[float] = Field(None, description="氨基氮")
    strain_tube_no: Optional[str] = Field(None, description="冻管菌号")
    shaker_setup_operator: Optional[str] = Field(None, description="上摇床摆东西人员")
    shaker_no: Optional[str] = Field(None, description="摇床编号")
    shaker_start_date: Optional[date] = Field(None, description="上摇床日期")
    inoculation_operator: Optional[str] = Field(None, description="接种人员/复核人")
    tool_no: Optional[str] = Field(None, description="用具编号")
    merge_time: Optional[datetime] = Field(None, description="并瓶时间")
    merge_count: Optional[int] = Field(None, description="并瓶数量(瓶)")
    merge_cycle: Optional[str] = Field(None, description="并瓶周期")
    merge_ph: Optional[float] = Field(None, description="并瓶PH")
    merge_bacteria_density: Optional[float] = Field(None, description="并瓶菌浓")
    merge_total_sugar: Optional[float] = Field(None, description="并瓶总糖")
    merge_reducing_sugar: Optional[float] = Field(None, description="并瓶还原糖")
    merge_amino_nitrogen: Optional[float] = Field(None, description="并瓶氨基氮")
    tank_setup_operator: Optional[str] = Field(None, description="进罐摆东西人员")
    cylinder_no: Optional[str] = Field(None, description="钢瓶编号")
    merge_operator: Optional[str] = Field(None, description="并瓶操作人/复核人")
    workshop_inoculation_operator: Optional[str] = Field(None, description="车间接种人员")
    tank_remarks: Optional[str] = Field(None, description="备注（罐号）")
    tank_yield: Optional[float] = Field(None, description="罐产")
    remarks: Optional[str] = Field(None, description="备注")


class SeedCultureResponse(BaseModel):
    id: UUID
    batch_no: str
    product_name: str
    prepare_date: Optional[date] = None
    glucose_batch: Optional[str] = None
    corn_starch_batch: Optional[str] = None
    corn_syrup_batch: Optional[str] = None
    ammonium_sulfate_batch: Optional[str] = None
    soybean_meal_batch: Optional[str] = None
    calcium_carbonate_batch: Optional[str] = None
    prepare_operator: Optional[str] = None
    sterilization_operator: Optional[str] = None
    ph_before_adjust: Optional[float] = None
    ph_after_adjust: Optional[float] = None
    ph_after_sterilization: Optional[float] = None
    reducing_sugar: Optional[float] = None
    total_sugar: Optional[float] = None
    amino_nitrogen: Optional[float] = None
    strain_tube_no: Optional[str] = None
    shaker_setup_operator: Optional[str] = None
    shaker_no: Optional[str] = None
    shaker_start_date: Optional[date] = None
    inoculation_operator: Optional[str] = None
    tool_no: Optional[str] = None
    merge_time: Optional[datetime] = None
    merge_count: Optional[int] = None
    merge_cycle: Optional[str] = None
    merge_ph: Optional[float] = None
    merge_bacteria_density: Optional[float] = None
    merge_total_sugar: Optional[float] = None
    merge_reducing_sugar: Optional[float] = None
    merge_amino_nitrogen: Optional[float] = None
    tank_setup_operator: Optional[str] = None
    cylinder_no: Optional[str] = None
    merge_operator: Optional[str] = None
    workshop_inoculation_operator: Optional[str] = None
    tank_remarks: Optional[str] = None
    tank_yield: Optional[float] = None
    remarks: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
