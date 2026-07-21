"""Pressure differential inspection ORM models."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class PointMapping(BaseModel):
    """位点映射表 — 位点编号绑定区域和标准压差"""

    __tablename__ = "point_mappings"
    __table_args__ = (
        UniqueConstraint("point_id", name="uq_point_mappings_point_id"),
        Index("ix_point_mappings_area", "area"),
        {"schema": "production"},
    )

    point_id: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="位点编号，如 PD-0101"
    )
    area: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="区域：无菌区/精洗区/配液区/走廊/更衣室/其他"
    )
    standard_pressure: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="标准压差值 (Pa)"
    )


class PressureRecord(BaseModel):
    """压差记录表"""

    __tablename__ = "pressure_records"
    __table_args__ = (
        Index("ix_pressure_records_point_id", "point_id"),
        Index("ix_pressure_records_area", "area"),
        Index("ix_pressure_records_record_time", "record_time"),
        Index("ix_pressure_records_status", "status"),
        Index("ix_pressure_records_batch_id", "batch_id"),
        {"schema": "production"},
    )

    point_id: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="位点编号"
    )
    area: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="区域"
    )
    pressure_value: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="压差值 (Pa)"
    )
    standard_pressure: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="标准压差值"
    )
    record_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="记录时间"
    )
    input_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", comment="录入方式: manual/ocr"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="审核状态: pending/approved/rejected",
    )
    reject_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="驳回原因"
    )
    image_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="OCR 上传图片地址"
    )
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )
    creator: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="记录人"
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="批次 ID（同一批提交的记录共享）"
    )
    time_slot: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="时段标签，如 08:00、14:00"
    )


class OcrTask(BaseModel):
    """OCR 任务表"""

    __tablename__ = "ocr_tasks"
    __table_args__ = (
        Index("ix_ocr_tasks_status", "status"),
        {"schema": "production"},
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="任务状态: pending/processing/completed/failed/cancelled/submitted",
    )
    image_url: Mapped[str] = mapped_column(
        Text, nullable=False, comment="图片地址"
    )
    result: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="OCR 识别结果 JSON"
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="提交后生成的批次 ID"
    )
    creator: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="创建人"
    )


class DataMaster(BaseModel):
    """数据总表 — 统一管理所有物料数据"""

    __tablename__ = "data_master"
    __table_args__ = (
        Index("ix_data_master_record_date", "record_date"),
        Index("ix_data_master_material_name", "material_name"),
        Index("ix_data_master_source", "source"),
        {"schema": "production"},
    )

    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="记录日期"
    )
    material_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="物料名称"
    )
    spec_model: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="规格型号"
    )
    quantity: Mapped[float] = mapped_column(
        Float, nullable=False, default=0, comment="数量"
    )
    unit: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="单位"
    )
    supplier: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="供应商"
    )
    remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="备注"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", comment="来源: manual/ocr"
    )
    creator_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="创建人姓名"
    )


class Notification(BaseModel):
    """通知表"""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_target_user_id", "target_user_id"),
        {"schema": "production"},
    )

    type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="通知类型: ocr_completed/ocr_failed"
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="标题"
    )
    message: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否已读"
    )
    target_user_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="目标用户 ID"
    )
    related_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, comment="关联实体 ID"
    )
    related_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="关联实体类型: ocr_task"
    )
