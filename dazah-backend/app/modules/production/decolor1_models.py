"""一次脱色 ORM"""
from datetime import date
from sqlalchemy import Date, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel

class Decolor1(BaseModel):
    __tablename__ = "decolor1"; __table_args__ = (Index("ix_d1_batch", "batch_no"), Index("ix_d1_frid", "feishu_record_id", unique=True), {"schema": "production"})
    feishu_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default='203')
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次号")
    feed_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="陶瓷膜滤液进料体积/重量")
    feed_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="进料效价")
    carbon_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="脱色活性炭/树脂型号")
    dosage: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="投加量")
    stirring_speed: Mapped[float | None] = mapped_column(Float, nullable=True, comment="搅拌转速")
    decolor_temp: Mapped[float | None] = mapped_column(Float, nullable=True, comment="脱色温度")
    holding_time: Mapped[float | None] = mapped_column(Float, nullable=True, comment="保温吸附时长")
    endpoint_transmittance: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="终点透光率/色度")
    decolor_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="脱色后料液总量")
    color_before: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="脱色前色度")
    color_after: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="脱色后色度")
    color_removal_rate: Mapped[float | None] = mapped_column(Float, nullable=True, comment="色素去除率")
    heavy_metal: Mapped[str | None] = mapped_column(Text, nullable=True, comment="重金属检测数据")
    protein_impurity: Mapped[str | None] = mapped_column(Text, nullable=True, comment="蛋白杂质检测数据")
    transmittance_data: Mapped[str | None] = mapped_column(Text, nullable=True, comment="透光率检测数据")
    carbon_residue: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="活性炭残渣量")
