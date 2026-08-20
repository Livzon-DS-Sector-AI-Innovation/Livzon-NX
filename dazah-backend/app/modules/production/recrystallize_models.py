"""二次重结晶脱色 ORM"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Recrystallize(BaseModel):
    __tablename__ = "recrystallize"
    __table_args__ = (
        Index("ix_rx_batch", "batch_no"),
        Index("ix_rx_frid", "feishu_record_id", unique=True),
        {"schema": "production"},
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="上清液总量(L)"
    )
    feed_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上清液效价(U/mL)"
    )
    solvent_amount: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="溶剂投加量(L)"
    )
    water_amount: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="纯水投加量(L)"
    )
    solvent_ratio: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="溶剂配比(V/V)"
    )
    carbon_dosage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="脱色炭/树脂投加量(%)"
    )
    dissolve_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="升温溶解温度(℃)"
    )
    holding_time: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="保温时间(min)"
    )
    cooling_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="降温速率(℃/h)"
    )
    crystal_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="终点结晶温度(℃)"
    )
    crystal_time: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="养晶时长(h)"
    )
    color_hazen: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="结晶液色度(Hazen)"
    )
    transmittance: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="透光率(%)"
    )
    crystal_size: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="晶体粒度(μm)"
    )
    mother_liquor_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液效价(U/mL)"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
