"""一次离心 ORM"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Centrifuge1(BaseModel):
    __tablename__ = "centrifuge1"
    __table_args__ = (
        Index("ix_cf1_batch", "batch_no"),
        Index("ix_cf1_frid", "feishu_record_id", unique=True),
        {"schema": "production"},
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="浓缩液进料总量(L)"
    )
    solid_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="固含量(%)"
    )
    feed_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="进料温度(℃)"
    )
    rotation_speed: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="转速(rpm)"
    )
    centrifuge_duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="离心时长(min)"
    )
    feed_flow: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="进料流量(L/h)"
    )
    sep_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="分离温度(℃)"
    )
    supernatant_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="上清液总量(L)"
    )
    supernatant_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上清液效价(U/mL)"
    )
    solid_waste_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="固体渣重量(kg)"
    )
    waste_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="渣效价(U/g)"
    )
    waste_moisture: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="渣含水率(%)"
    )
    centrifuge_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="离心上清收率(%)"
    )
    solid_waste_output: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="固体废渣产出量(kg)"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
