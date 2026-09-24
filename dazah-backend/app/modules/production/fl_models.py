"""氟苯尼考预混剂（FL）批次工序流转模型。

数据来源为飞书多维表格按月分表（「N月排产」），一行一个批次，
记录指令→领料→投料→混合→包装→请检→入库各工序日期与包装实际重量；
当前工序不入库，查询时按已填节点推导。
"""

from datetime import date

from sqlalchemy import Date, Float, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FlBatch(BaseModel):
    __tablename__ = "fl_batches"
    __table_args__ = (
        Index(
            "uq_fl_batches_batch_no",
            "batch_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_fl_batches_data_month", "data_month"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="生产批号（FL-YYMM+月内流水，如 FL-2609001）",
    )
    order_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="指令日期"
    )
    pick_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="领料日期"
    )
    charge_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="投料日期"
    )
    charge_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="投料时间（文本区间，如 8:00~10:00）"
    )
    mix_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="混合（生产）日期"
    )
    mix_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="混合时间（文本区间）"
    )
    spec: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="规格（如 10kg/袋、2袋/箱）"
    )
    pack_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="包装重量实际值（kg）"
    )
    pack_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="包装日期"
    )
    pack_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="包装时间（文本区间）"
    )
    inspection_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="请检日期"
    )
    inbound_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="入库日期"
    )
    source_table: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="来源飞书月表名（如 9月排产）"
    )
    data_month: Mapped[str | None] = mapped_column(
        String(7), nullable=True, comment="归组月份 YYYY-MM（按批号 YYMM）"
    )
    sync_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="同步备注（异常与跳过原因）"
    )
