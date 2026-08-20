"""陶瓷膜过滤 — 进料/运行/清洗/分离/设备 5表 ORM（匹配飞书字段）"""

from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class CeramicFeed(BaseModel):
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, comment="飞书记录ID"
    )
    __tablename__ = "ceramic_feeds"
    __table_args__ = (Index("ix_cf_batch", "batch_no"), {"schema": "production"})
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    feed_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    feed_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    feed_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    ph_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    tank_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    material_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class CeramicMembraneClean(BaseModel):
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, comment="飞书记录ID"
    )
    __tablename__ = "ceramic_membrane_cleans"
    __table_args__ = (Index("ix_cmc_mem_no", "membrane_no"), {"schema": "production"})
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clean_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    membrane_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cleaner_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cleaner_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    clean_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    clean_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    clean_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    flux_recovery: Mapped[float | None] = mapped_column(Float, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class CeramicMembraneOps(BaseModel):
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, comment="飞书记录ID"
    )
    __tablename__ = "ceramic_membrane_ops"
    __table_args__ = (Index("ix_cmo_batch", "batch_no"), {"schema": "production"})
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    membrane_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    membrane_velocity: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmp: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_temp: Mapped[float | None] = mapped_column(Float, nullable=True)
    permeate_flux: Mapped[float | None] = mapped_column(Float, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class CeramicEquipmentLog(BaseModel):
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, comment="飞书记录ID"
    )
    __tablename__ = "ceramic_equipment_logs"
    __table_args__ = (Index("ix_cel_date", "record_date"), {"schema": "production"})
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    equipment_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    abnormal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    abnormal_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    handler: Mapped[str | None] = mapped_column(String(64), nullable=True)
    restore_time: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)


class CeramicMaterialSeparation(BaseModel):
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, comment="飞书记录ID"
    )
    __tablename__ = "ceramic_material_separations"
    __table_args__ = (Index("ix_cms_batch", "batch_no"), {"schema": "production"})
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sep_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    separation_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retentate_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    permeate_volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    retentate_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    permeate_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
