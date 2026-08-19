"""烘干 ORM"""
from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel

class Dry(BaseModel):
    __tablename__ = "dry"; __table_args__ = (Index("ix_dry_batch", "batch_no"), Index("ix_dry_frid", "feishu_record_id", unique=True), {"schema": "production"})
    feishu_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default='203')
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_weight: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="二次离心湿晶体投料重量(kg)")
    wet_moisture: Mapped[float | None] = mapped_column(Float, nullable=True, comment="湿品含水率(%)")
    oven_temp: Mapped[float | None] = mapped_column(Float, nullable=True, comment="烘箱温度(℃)")
    vacuum_degree: Mapped[float | None] = mapped_column(Float, nullable=True, comment="真空度(MPa)")
    dry_duration: Mapped[float | None] = mapped_column(Float, nullable=True, comment="干燥时长(h)")
    air_flow: Mapped[float | None] = mapped_column(Float, nullable=True, comment="热风风量(m³/h)")
    turn_interval: Mapped[float | None] = mapped_column(Float, nullable=True, comment="翻料间隔时间(min)")
    endpoint_moisture: Mapped[float | None] = mapped_column(Float, nullable=True, comment="终点水分(%)")
    dry_weight: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="干品总重量(kg)")
    dry_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="干品效价(U/g)")
    dry_purity: Mapped[float | None] = mapped_column(Float, nullable=True, comment="干品纯度(%)")
    powder_loss: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="烘干飞粉损耗(kg)")
    tray_residue: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="托盘粘料残留(kg)")
    dry_yield: Mapped[float | None] = mapped_column(Float, nullable=True, comment="干燥收率(%)")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
