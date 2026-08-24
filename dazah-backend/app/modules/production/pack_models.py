"""包装 ORM"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class Pack(BaseModel):
    __tablename__ = "pack"
    __table_args__ = (
        Index("ix_pack_batch", "batch_no"),
        Index("ix_pack_frid", "feishu_record_id", unique=True),
        {"schema": "production"},
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    seq_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workshop: Mapped[str] = mapped_column(String(32), nullable=False, default="203")
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批次")
    feed_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="烘干干品总重量(kg)"
    )
    incoming_batch: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="来料批号"
    )
    incoming_titer: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="来料效价(U/g)"
    )
    incoming_moisture: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="来料水分(%)"
    )
    impurity_report: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="杂质检测报告"
    )
    pack_spec: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分装规格(kg/桶)"
    )
    barrel_count: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="包装桶数量(桶)"
    )
    per_barrel_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="每桶实际装料重量(kg)"
    )
    total_net_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="总包装成品净重(kg)"
    )
    sample_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="取样复检重量(kg)"
    )
    retain_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="留样重量(kg)"
    )
    reject_weight: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="不合格品重量(kg)"
    )
    screen_loss: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="筛分粉尘损耗(kg)"
    )
    spill_loss: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分装撒料损耗(kg)"
    )
    total_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="成品总收率(%)"
    )
    pack_date: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="包装日期"
    )
    operator: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="操作人员"
    )
    outer_pack_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="外包装编号"
    )
    warehouse_qty: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="入库数量(kg)"
    )
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
