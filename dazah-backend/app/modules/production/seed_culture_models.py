"""摇瓶种子制备记录 ORM model."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class SeedCulture(BaseModel):
    """摇瓶种子制备记录表"""

    __tablename__ = "seed_cultures"
    __table_args__ = (
        Index("ix_seed_cultures_batch_no", "batch_no"),
        Index("ix_seed_cultures_prepare_date", "prepare_date"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="摇瓶批号"
    )
    product_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", comment="产品名称"
    )
    prepare_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="配制日期"
    )
    glucose_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="物料A/批号"
    )
    corn_starch_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="物料B/批号"
    )
    corn_syrup_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="物料C/批号"
    )
    ammonium_sulfate_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="物料D/批号"
    )
    soybean_meal_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="物料E/批号"
    )
    calcium_carbonate_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="物料F/批号"
    )
    prepare_operator: Mapped[list[dict[str, Any]] | str | None] = mapped_column(
        "prepare_operator_people", JSONB(none_as_null=True), nullable=True
    )
    sterilization_operator: Mapped[list[dict[str, Any]] | str | None] = mapped_column(
        "sterilization_operator_people", JSONB(none_as_null=True), nullable=True
    )
    ph_before_adjust: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="调前PH"
    )
    ph_after_adjust: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="调后PH"
    )
    ph_after_sterilization: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="消后PH"
    )
    reducing_sugar: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="还原糖"
    )
    total_sugar: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总糖"
    )
    amino_nitrogen: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="氨基氮"
    )
    strain_tube_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="冻管菌号"
    )
    shaker_setup_operator: Mapped[list[dict[str, Any]] | str | None] = mapped_column(
        "shaker_setup_operator_people", JSONB(none_as_null=True), nullable=True
    )
    shaker_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="摇床编号"
    )
    shaker_start_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上摇床日期"
    )
    inoculation_operator: Mapped[list[dict[str, Any]] | str | None] = mapped_column(
        "inoculation_operator_people", JSONB(none_as_null=True), nullable=True
    )
    tool_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="用具编号"
    )
    merge_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="并瓶时间"
    )
    merge_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="并瓶数量(瓶)"
    )
    merge_cycle: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="并瓶周期"
    )
    merge_ph: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="并瓶PH"
    )
    merge_bacteria_density: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="并瓶菌浓"
    )
    merge_total_sugar: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="并瓶总糖"
    )
    merge_reducing_sugar: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="并瓶还原糖"
    )
    merge_amino_nitrogen: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="并瓶氨基氮"
    )
    tank_setup_operator: Mapped[list[dict[str, Any]] | str | None] = mapped_column(
        "tank_setup_operator_people", JSONB(none_as_null=True), nullable=True
    )
    cylinder_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="钢瓶编号"
    )
    merge_operator: Mapped[list[dict[str, Any]] | str | None] = mapped_column(
        "merge_operator_people", JSONB(none_as_null=True), nullable=True
    )
    workshop_inoculation_operator: Mapped[list[dict[str, Any]] | str | None] = (
        mapped_column(
            "workshop_inoculation_operator_people",
            JSONB(none_as_null=True),
            nullable=True,
        )
    )
    tank_remarks: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="备注（罐号）"
    )
    tank_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="罐产"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
