"""二次离心 ORM"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Centrifuge2(BaseModel):
    __tablename__ = "centrifuge2"
    __table_args__ = (
        Index("ix_cf2_batch", "batch_no"),
        Index("ix_cf2_frid", "feishu_record_id", unique=True),
        {"schema": "production"},
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="二次浓缩结晶悬浮液进料总量(kg)"
    )
    rotation_speed: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="离心转速(rpm)"
    )
    sep_duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="分离时间(min)"
    )
    feed_flow: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="进料流速(L/h)"
    )
    crystal_wet_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="精制湿晶体总量(kg)"
    )
    waste_liquor_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="废母液总量(L)"
    )
    mother_liquor_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液残留效价(U/mL)"
    )
    crystal_moisture: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="湿晶含水率(%)"
    )
    liquor_recovery: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="母液回收量(L)"
    )
    crystal_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="晶体收率(%)"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
