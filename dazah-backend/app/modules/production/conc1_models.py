"""一次浓缩 ORM"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Conc1(BaseModel):
    __tablename__ = "conc1"
    __table_args__ = (
        Index("ix_c1_batch", "batch_no"),
        Index("ix_c1_frid", "feishu_record_id", unique=True),
        {"schema": "production"},
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="板框滤清液进料体积(L)"
    )
    feed_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="板框滤清液进料效价(U/mL)"
    )
    feed_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="板框滤清液进料温度(℃)"
    )
    vacuum_degree: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩真空度(MPa)"
    )
    evap_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="蒸发温度(℃)"
    )
    steam_pressure: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="蒸汽压力(MPa)"
    )
    conc_duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩时长(h)"
    )
    condensate_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="冷凝水产出量(L)"
    )
    endpoint_density: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩终点比重(g/cm³)"
    )
    endpoint_refraction: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩终点折光(%)"
    )
    endpoint_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="浓缩终点体积(L)"
    )
    conc_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="浓缩后料液重量(kg)"
    )
    conc_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="浓缩后料液体积(L)"
    )
    conc_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩后效价(U/mL)"
    )
    conc_factor: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩倍数(倍)"
    )
    evap_loss: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="蒸发损耗量(L)"
    )
    wall_residue: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="釜壁粘壁残料量(L)"
    )
    conc_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="浓缩收率(%)"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
