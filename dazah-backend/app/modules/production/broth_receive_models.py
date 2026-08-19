"""发酵液接收记录 ORM"""

from datetime import datetime
from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.base_model import BaseModel


class BrothReceive(BaseModel):
    """发酵液接收记录表"""
    __tablename__ = "broth_receives"
    __table_args__ = (
        Index("ix_broth_receive_batch", "received_batch"),
        Index("ix_broth_receive_fermenter", "fermenter_no"),
        {"schema": "production"},
    )

    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="序号")
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default='203')
    received_batch: Mapped[str] = mapped_column(String(128), nullable=False, comment="接收批次")
    fermenter_no: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="发酵罐号")
    fermentation_batch: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="发酵批号")
    received_volume: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="接收体积/重量")
    broth_od: Mapped[float | None] = mapped_column(Float, nullable=True, comment="发酵液OD")
    titer_u_ml: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价(u/mL)")
    titer_mg_l: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价(mg/L)")
    broth_ph: Mapped[float | None] = mapped_column(Float, nullable=True, comment="发酵液pH")
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True, comment="温度")
    mycelium_concentration: Mapped[float | None] = mapped_column(Float, nullable=True, comment="菌丝浓度")
    residual_sugar: Mapped[float | None] = mapped_column(Float, nullable=True, comment="残糖")
    amino_nitrogen: Mapped[float | None] = mapped_column(Float, nullable=True, comment="氨基氮")
    receive_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="进厂/接收时间")
    supplier_team: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="供方班组")
    tank_bottom_residue: Mapped[float | None] = mapped_column(Float, nullable=True, comment="罐底渣量")
    sample_no: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="取样编号")
    sample_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="取样时间")
    inspection_result: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="检验结果")
    qualified: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="合格判定")
    receive_loss: Mapped[float | None] = mapped_column(Float, nullable=True, comment="接收损耗量")
    pipeline_leak_record: Mapped[str | None] = mapped_column(Text, nullable=True, comment="输送管路跑冒滴漏记录")
