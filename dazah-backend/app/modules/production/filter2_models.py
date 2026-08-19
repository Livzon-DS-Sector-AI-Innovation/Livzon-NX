"""二次板框过滤 ORM"""
from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel

class Filter2(BaseModel):
    __tablename__ = "filter2"; __table_args__ = (Index("ix_f2_batch", "batch_no"), Index("ix_f2_frid", "feishu_record_id", unique=True), {"schema": "production"})
    feishu_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default='203')
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="重结晶脱色悬浮液总进料量(kg)")
    filter_pressure: Mapped[float | None] = mapped_column(Float, nullable=True, comment="过滤压力(MPa)")
    filter_duration: Mapped[float | None] = mapped_column(Float, nullable=True, comment="过滤时长(min)")
    cloth_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="滤布型号")
    cake_wet_weight: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="晶体滤饼湿重(kg)")
    cake_dry_weight: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="晶体滤饼干重(kg)")
    crystal_purity: Mapped[float | None] = mapped_column(Float, nullable=True, comment="晶体纯度(%)")
    crystal_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="晶体效价(U/g)")
    filtrate_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="二次母液滤液总量(L)")
    mother_liquor_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="母液残留效价(U/mL)")
    wash_water: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="滤饼洗涤用水量(L)")
    combined_liquor: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="洗涤后母液合并量(L)")
    wash_loss: Mapped[float | None] = mapped_column(Float, nullable=True, comment="洗涤损失(%)")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
