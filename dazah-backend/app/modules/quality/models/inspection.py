"""Inspection foundation ORM models for the quality module."""

import uuid
from datetime import date

from sqlalchemy import Date, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class QualityInspectionBaseModel(BaseModel):
    """Quality inspection base without database foreign-key constraints."""

    __abstract__ = True

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class LabItem(QualityInspectionBaseModel):
    """Laboratory consumable, reagent, standard or reference material."""

    __tablename__ = "lab_items"
    __table_args__ = (
        Index(
            "ix_quality_lab_items_active_status_expiry",
            "is_deleted",
            "status",
            "expiry_date",
        ),
        Index("ix_quality_lab_items_name", "name"),
        {"schema": "quality"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="物品名称")
    specification: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="规格/型号"
    )
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="类别"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="数量"
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="单位")
    location: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="存放位置"
    )
    supplier: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="供应商"
    )
    batch_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    expiry_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="有效期至"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
        comment="状态",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class LabInstrument(QualityInspectionBaseModel):
    """Laboratory testing instrument and its calibration status."""

    __tablename__ = "lab_instruments"
    __table_args__ = (
        UniqueConstraint("serial_no", name="uq_quality_lab_instruments_serial_no"),
        Index(
            "ix_quality_lab_instruments_active_status_calibration",
            "is_deleted",
            "status",
            "next_calibration_date",
        ),
        Index("ix_quality_lab_instruments_name", "name"),
        {"schema": "quality"},
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="仪器名称")
    model: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="型号"
    )
    serial_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="序列号"
    )
    manufacturer: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="生产厂家"
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="所属部门"
    )
    location: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="放置位置"
    )
    calibration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="最近校准日期"
    )
    next_calibration_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="下次校准日期"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
        comment="状态",
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class InspectionRecord(QualityInspectionBaseModel):
    """General quality inspection record."""

    __tablename__ = "inspection_records"
    __table_args__ = (
        UniqueConstraint(
            "inspection_no", name="uq_quality_inspection_records_inspection_no"
        ),
        Index(
            "ix_quality_inspection_records_active_type_date",
            "is_deleted",
            "inspection_type",
            "inspection_date",
        ),
        Index(
            "ix_quality_inspection_records_active_conclusion_date",
            "is_deleted",
            "conclusion",
            "inspection_date",
        ),
        {"schema": "quality"},
    )

    inspection_no: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="检验编号"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="产品名称"
    )
    batch_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    inspection_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="检验类型"
    )
    inspection_item: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="检验项目"
    )
    specification: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准规定"
    )
    test_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检验结果"
    )
    conclusion: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="检验结论"
    )
    inspector: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检验人"
    )
    inspection_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="检验日期"
    )
    department: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检验部门"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class FinishedProductInspection(QualityInspectionBaseModel):
    """Finished product inspection record."""

    __tablename__ = "finished_product_inspections"
    __table_args__ = (
        UniqueConstraint(
            "inspection_no", name="uq_quality_finished_product_inspections_no"
        ),
        Index(
            "ix_quality_finished_product_inspections_active_date",
            "is_deleted",
            "inspection_date",
        ),
        Index(
            "ix_quality_finished_product_inspections_product_batch",
            "product_name",
            "batch_no",
        ),
        {"schema": "quality"},
    )

    inspection_no: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="检验编号"
    )
    product_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="产品名称"
    )
    batch_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="批号"
    )
    inspection_item: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="检验项目"
    )
    specification: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准规定"
    )
    test_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检验结果"
    )
    conclusion: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="检验结论"
    )
    inspector: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检验人"
    )
    inspection_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="检验日期"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class SolidMaterialInspection(QualityInspectionBaseModel):
    """Solid raw or auxiliary material inspection record."""

    __tablename__ = "solid_material_inspections"
    __table_args__ = (
        UniqueConstraint(
            "inspection_no", name="uq_quality_solid_material_inspections_no"
        ),
        Index(
            "ix_quality_solid_material_inspections_active_date",
            "is_deleted",
            "inspection_date",
        ),
        Index(
            "ix_quality_solid_material_inspections_material_batch",
            "material_name",
            "material_batch",
        ),
        {"schema": "quality"},
    )

    inspection_no: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="检验编号"
    )
    material_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="物料名称"
    )
    material_batch: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="物料批号"
    )
    supplier: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="供应商"
    )
    inspection_item: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="检验项目"
    )
    specification: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准规定"
    )
    test_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检验结果"
    )
    conclusion: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="检验结论"
    )
    inspector: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检验人"
    )
    inspection_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="检验日期"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class LiquidMaterialInspection(QualityInspectionBaseModel):
    """Liquid raw or auxiliary material inspection record."""

    __tablename__ = "liquid_material_inspections"
    __table_args__ = (
        UniqueConstraint(
            "inspection_no", name="uq_quality_liquid_material_inspections_no"
        ),
        Index(
            "ix_quality_liquid_material_inspections_active_date",
            "is_deleted",
            "inspection_date",
        ),
        Index(
            "ix_quality_liquid_material_inspections_material_batch",
            "material_name",
            "material_batch",
        ),
        {"schema": "quality"},
    )

    inspection_no: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="检验编号"
    )
    material_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="物料名称"
    )
    material_batch: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="物料批号"
    )
    supplier: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="供应商"
    )
    inspection_item: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="检验项目"
    )
    specification: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="标准规定"
    )
    test_result: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="检验结果"
    )
    conclusion: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="检验结论"
    )
    inspector: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="检验人"
    )
    inspection_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="检验日期"
    )
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
