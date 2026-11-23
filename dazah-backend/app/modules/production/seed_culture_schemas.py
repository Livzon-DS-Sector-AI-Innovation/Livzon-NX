"""摇瓶种子制备记录 Pydantic schemas."""

import json
import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def coerce_person_refs(value: object) -> object:
    """兼容历史文本（"张三,李四"）与 to_jsonb 迁移产生的 JSON 字符串。"""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            return parsed
        return [
            {"name": part.strip()}
            for part in re.split(r"[,，、]", stripped)
            if part.strip()
        ]
    return value


class PersonRef(BaseModel):
    """人员引用：飞书成员（open_id + 姓名 + 头像），兼容仅姓名的手工录入。"""

    name: str = Field(default="", description="姓名")
    open_id: str | None = Field(None, description="飞书 open_id")
    avatar_url: str | None = Field(None, description="头像 URL")

    @field_validator("name", mode="before")
    @classmethod
    def _coerce_name(cls: Any, value: Any) -> Any:
        return str(value) if value is not None else ""


class SeedCultureCreate(BaseModel):
    batch_no: str = Field(..., description="摇瓶批号")
    product_name: str = Field(default="", description="产品名称")
    prepare_date: date | None = Field(None, description="配制日期")
    glucose_batch: str | None = Field(None, description="葡萄糖/批号")
    corn_starch_batch: str | None = Field(None, description="玉米淀粉/批号")
    corn_syrup_batch: str | None = Field(None, description="玉米浆/批号")
    ammonium_sulfate_batch: str | None = Field(None, description="硫酸铵/批号")
    soybean_meal_batch: str | None = Field(None, description="黄豆饼粉/批号")
    calcium_carbonate_batch: str | None = Field(None, description="碳酸钙/批号")
    prepare_operator: list[PersonRef] | None = Field(
        None, description="配制操作人/复核人"
    )
    sterilization_operator: list[PersonRef] | None = Field(
        None, description="种子消毒人员"
    )
    ph_before_adjust: float | None = Field(None, description="调前PH")
    ph_after_adjust: float | None = Field(None, description="调后PH")
    ph_after_sterilization: float | None = Field(None, description="消后PH")
    reducing_sugar: float | None = Field(None, description="还原糖")
    total_sugar: float | None = Field(None, description="总糖")
    amino_nitrogen: float | None = Field(None, description="氨基氮")
    strain_tube_no: str | None = Field(None, description="冻管菌号")
    shaker_setup_operator: list[PersonRef] | None = Field(
        None, description="上摇床摆东西人员"
    )
    shaker_no: str | None = Field(None, description="摇床编号")
    shaker_start_date: date | None = Field(None, description="上摇床日期")
    inoculation_operator: list[PersonRef] | None = Field(
        None, description="接种人员/复核人"
    )
    tool_no: str | None = Field(None, description="用具编号")
    merge_time: datetime | None = Field(None, description="并瓶时间")
    merge_count: int | None = Field(None, description="并瓶数量(瓶)")
    merge_cycle: str | None = Field(None, description="并瓶周期")
    merge_ph: float | None = Field(None, description="并瓶PH")
    merge_bacteria_density: float | None = Field(None, description="并瓶菌浓")
    merge_total_sugar: float | None = Field(None, description="并瓶总糖")
    merge_reducing_sugar: float | None = Field(None, description="并瓶还原糖")
    merge_amino_nitrogen: float | None = Field(None, description="并瓶氨基氮")
    tank_setup_operator: list[PersonRef] | None = Field(
        None, description="进罐摆东西人员"
    )
    cylinder_no: str | None = Field(None, description="钢瓶编号")
    merge_operator: list[PersonRef] | None = Field(
        None, description="并瓶操作人/复核人"
    )
    workshop_inoculation_operator: list[PersonRef] | None = Field(
        None, description="车间接种人员"
    )
    tank_remarks: str | None = Field(None, description="备注（罐号）")
    tank_yield: float | None = Field(None, description="罐产")
    remarks: str | None = Field(None, description="备注")

    @field_validator(
        "prepare_operator",
        "sterilization_operator",
        "shaker_setup_operator",
        "inoculation_operator",
        "tank_setup_operator",
        "merge_operator",
        "workshop_inoculation_operator",
        mode="before",
    )
    @classmethod
    def _coerce_person_refs(cls, value: object) -> object:
        return coerce_person_refs(value)


class SeedCultureUpdate(BaseModel):
    batch_no: str | None = Field(None, description="摇瓶批号")
    product_name: str | None = Field(None, description="产品名称")
    prepare_date: date | None = Field(None, description="配制日期")
    glucose_batch: str | None = Field(None, description="葡萄糖/批号")
    corn_starch_batch: str | None = Field(None, description="玉米淀粉/批号")
    corn_syrup_batch: str | None = Field(None, description="玉米浆/批号")
    ammonium_sulfate_batch: str | None = Field(None, description="硫酸铵/批号")
    soybean_meal_batch: str | None = Field(None, description="黄豆饼粉/批号")
    calcium_carbonate_batch: str | None = Field(None, description="碳酸钙/批号")
    prepare_operator: list[PersonRef] | None = Field(
        None, description="配制操作人/复核人"
    )
    sterilization_operator: list[PersonRef] | None = Field(
        None, description="种子消毒人员"
    )
    ph_before_adjust: float | None = Field(None, description="调前PH")
    ph_after_adjust: float | None = Field(None, description="调后PH")
    ph_after_sterilization: float | None = Field(None, description="消后PH")
    reducing_sugar: float | None = Field(None, description="还原糖")
    total_sugar: float | None = Field(None, description="总糖")
    amino_nitrogen: float | None = Field(None, description="氨基氮")
    strain_tube_no: str | None = Field(None, description="冻管菌号")
    shaker_setup_operator: list[PersonRef] | None = Field(
        None, description="上摇床摆东西人员"
    )
    shaker_no: str | None = Field(None, description="摇床编号")
    shaker_start_date: date | None = Field(None, description="上摇床日期")
    inoculation_operator: list[PersonRef] | None = Field(
        None, description="接种人员/复核人"
    )
    tool_no: str | None = Field(None, description="用具编号")
    merge_time: datetime | None = Field(None, description="并瓶时间")
    merge_count: int | None = Field(None, description="并瓶数量(瓶)")
    merge_cycle: str | None = Field(None, description="并瓶周期")
    merge_ph: float | None = Field(None, description="并瓶PH")
    merge_bacteria_density: float | None = Field(None, description="并瓶菌浓")
    merge_total_sugar: float | None = Field(None, description="并瓶总糖")
    merge_reducing_sugar: float | None = Field(None, description="并瓶还原糖")
    merge_amino_nitrogen: float | None = Field(None, description="并瓶氨基氮")
    tank_setup_operator: list[PersonRef] | None = Field(
        None, description="进罐摆东西人员"
    )
    cylinder_no: str | None = Field(None, description="钢瓶编号")
    merge_operator: list[PersonRef] | None = Field(
        None, description="并瓶操作人/复核人"
    )
    workshop_inoculation_operator: list[PersonRef] | None = Field(
        None, description="车间接种人员"
    )
    tank_remarks: str | None = Field(None, description="备注（罐号）")
    tank_yield: float | None = Field(None, description="罐产")
    remarks: str | None = Field(None, description="备注")

    @field_validator(
        "prepare_operator",
        "sterilization_operator",
        "shaker_setup_operator",
        "inoculation_operator",
        "tank_setup_operator",
        "merge_operator",
        "workshop_inoculation_operator",
        mode="before",
    )
    @classmethod
    def _coerce_person_refs(cls, value: object) -> object:
        return coerce_person_refs(value)


class SeedCultureResponse(BaseModel):
    id: UUID
    batch_no: str
    product_name: str
    prepare_date: date | None = None
    glucose_batch: str | None = None
    corn_starch_batch: str | None = None
    corn_syrup_batch: str | None = None
    ammonium_sulfate_batch: str | None = None
    soybean_meal_batch: str | None = None
    calcium_carbonate_batch: str | None = None
    prepare_operator: list[PersonRef] | None = None
    sterilization_operator: list[PersonRef] | None = None
    ph_before_adjust: float | None = None
    ph_after_adjust: float | None = None
    ph_after_sterilization: float | None = None
    reducing_sugar: float | None = None
    total_sugar: float | None = None
    amino_nitrogen: float | None = None
    strain_tube_no: str | None = None
    shaker_setup_operator: list[PersonRef] | None = None
    shaker_no: str | None = None
    shaker_start_date: date | None = None
    inoculation_operator: list[PersonRef] | None = None
    tool_no: str | None = None
    merge_time: datetime | None = None
    merge_count: int | None = None
    merge_cycle: str | None = None
    merge_ph: float | None = None
    merge_bacteria_density: float | None = None
    merge_total_sugar: float | None = None
    merge_reducing_sugar: float | None = None
    merge_amino_nitrogen: float | None = None
    tank_setup_operator: list[PersonRef] | None = None
    cylinder_no: str | None = None
    merge_operator: list[PersonRef] | None = None
    workshop_inoculation_operator: list[PersonRef] | None = None
    tank_remarks: str | None = None
    tank_yield: float | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator(
        "prepare_operator",
        "sterilization_operator",
        "shaker_setup_operator",
        "inoculation_operator",
        "tank_setup_operator",
        "merge_operator",
        "workshop_inoculation_operator",
        mode="before",
    )
    @classmethod
    def _coerce_person_refs(cls, value: object) -> object:
        return coerce_person_refs(value)


class PersonMonthlyDetail(BaseModel):
    date: str = Field(..., description="参与日期（配置日期）")
    batch_no: str = Field(..., description="摇瓶批号")
    role: str = Field(
        ..., description="环节（配制/消毒/摇床摆放/接种/并瓶/进罐/车间接种）"
    )


class PersonMonthlyRow(BaseModel):
    key: str = Field(..., description="人员唯一键（open_id 或 name:姓名）")
    name: str = Field(default="", description="姓名")
    open_id: str | None = Field(None, description="飞书 open_id")
    avatar_url: str | None = Field(None, description="头像 URL")
    total_batches: int = Field(default=0, description="当月参与批次总数")
    role_counts: dict[str, int] = Field(
        default_factory=dict,
        description="各环节次数（配制/消毒/摇床摆放/接种/并瓶/进罐/车间接种）",
    )
    details: list[PersonMonthlyDetail] = Field(
        default_factory=list, description="明细：日期+批号+环节"
    )
