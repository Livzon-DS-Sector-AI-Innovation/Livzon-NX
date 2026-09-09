"""发酵批次实际产量模型（看板历史数据）。

看板批次（FA26xxx）的实际放罐产量按批号唯一（进行中的记录），
删除采用软删；在看板页「历史数据」抽屉中录入，
供单批产量柱状图与最近完成批次回填使用。
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class FermentationBatchActual(BaseModel):
    """发酵批次实际产量"""

    __tablename__ = "fermentation_batch_actuals"
    __table_args__ = (
        Index(
            "ux_fermentation_batch_actuals_batch_no",
            "batch_no",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="批次号（如 FA26232）"
    )
    dump_date: Mapped[date | None] = mapped_column(
        Date(), nullable=True, comment="放罐日期"
    )
    yield_kg: Mapped[float | None] = mapped_column(
        Float(), nullable=True, comment="放罐产量(kg)"
    )
    remark: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="备注"
    )
