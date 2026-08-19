"""二次浓缩 ORM"""
from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel

class Conc2(BaseModel):
    __tablename__ = "conc2"; __table_args__ = (Index("ix_c2_batch", "batch_no"), Index("ix_c2_frid", "feishu_record_id", unique=True), {"schema": "production"})
    feishu_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default='203')
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="二次板框母液合并总量(L)")
    vacuum_degree: Mapped[float | None] = mapped_column(Float, nullable=True, comment="真空(MPa)")
    evap_temp: Mapped[float | None] = mapped_column(Float, nullable=True, comment="温度(℃)")
    steam_pressure: Mapped[float | None] = mapped_column(Float, nullable=True, comment="蒸汽压力(MPa)")
    endpoint_refraction: Mapped[float | None] = mapped_column(Float, nullable=True, comment="浓缩终点折光(%)")
    endpoint_density: Mapped[float | None] = mapped_column(Float, nullable=True, comment="浓缩终点比重")
    conc_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="二次浓缩液体积(L)")
    conc_titer: Mapped[float | None] = mapped_column(Float, nullable=True, comment="二次浓缩液效价(U/mL)")
    conc_factor: Mapped[float | None] = mapped_column(Float, nullable=True, comment="浓缩倍数")
    condensate_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="冷凝水量(L)")
    bottom_residue: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="釜底残液(L)")
    evap_loss_rate: Mapped[float | None] = mapped_column(Float, nullable=True, comment="挥发损耗(%)")
    conc_yield: Mapped[float | None] = mapped_column(Float, nullable=True, comment="浓缩收率(%)")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
