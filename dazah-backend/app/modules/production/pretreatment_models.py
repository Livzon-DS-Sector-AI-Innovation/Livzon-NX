"""预处理工艺记录 ORM"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Pretreatment(BaseModel):
    """预处理工艺记录表"""

    __tablename__ = "pretreatments"
    __table_args__ = (
        Index("ix_pretreat_batch", "received_batch"),
        {"schema": "production"},
    )

    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="序号")
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    received_batch: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="接收批次"
    )
    broth_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="进罐发酵液总量"
    )
    acid_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="调酸用酸种类"
    )
    acid_amount: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="酸加入体积/重量"
    )
    neutralize_ph: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="中和终点pH"
    )
    dilution_water_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="稀释用水体积"
    )
    dilution_ratio: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="稀释倍数"
    )
    target_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="升温目标温度"
    )
    holding_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="保温时长"
    )
    temp_curve: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="升降温曲线"
    )
    settling_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="静置分层时长"
    )
    settling_temp: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="静置温度"
    )
    stirring_speed: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="搅拌转速"
    )
    stirring_time: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="搅拌启停时间"
    )
    supernatant_volume: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="上层清液量"
    )
    sediment_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="下层菌丝渣重量/体积"
    )
    titer_before: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="预处理前效价"
    )
    titer_after: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="预处理后效价"
    )
    yield_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="收率"
    )
    impurity_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质含量"
    )
    loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="预处理损耗"
    )
    residue_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="渣中残留效价"
    )
