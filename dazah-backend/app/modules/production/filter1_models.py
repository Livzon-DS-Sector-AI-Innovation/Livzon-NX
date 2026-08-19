"""一次板框过滤 ORM"""
from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel

class Filter1(BaseModel):
    __tablename__ = "filter1"; __table_args__ = (Index("ix_f1_batch", "batch_no"), Index("ix_f1_frid", "feishu_record_id", unique=True), {"schema": "production"})
    feishu_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default='203')
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次号")
    feed_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="脱色液进料总量")
    feed_ph: Mapped[float | None] = mapped_column(Float, nullable=True, comment="进料pH")
    feed_temp: Mapped[float | None] = mapped_column(Float, nullable=True, comment="进料温度")
    feed_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="进料效价")
    filter_pressure: Mapped[float | None] = mapped_column(Float, nullable=True, comment="板框压力")
    feed_flow: Mapped[float | None] = mapped_column(Float, nullable=True, comment="进料流量")
    filter_duration: Mapped[float | None] = mapped_column(Float, nullable=True, comment="过滤时长")
    cloth_no: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="滤布编号")
    filtrate_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="滤清液总量")
    filtrate_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="滤清液效价")
    cake_wet_weight: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="滤饼湿重")
    cake_dry_weight: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="滤饼干重")
    cake_residue_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="残留效价")
    pipe_residue: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="管道残留")
    cake_moisture: Mapped[float | None] = mapped_column(Float, nullable=True, comment="含水率")
    filter_yield: Mapped[float | None] = mapped_column(Float, nullable=True, comment="收率")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
