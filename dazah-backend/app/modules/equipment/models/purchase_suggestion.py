"""Spare part purchase suggestion ORM model（备件采购建议）."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.spare_part import SparePart
    from app.modules.equipment.models.work_order import WorkOrder


class SparePartPurchaseSuggestion(BaseModel):
    """备件采购建议：库存低于安全线自动生成（或工单申请备件不足生成）。

    状态机：suggested → submitted（已生成采购申请）→ partial/done（到货回写）；
    suggested/submitted 可 cancelled。
    """

    __tablename__ = "spare_part_purchase_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('suggested', 'submitted', 'partial', 'done', 'cancelled')",
            name="ck_spare_part_purchase_suggestions_status",
        ),
        CheckConstraint(
            "source IN ('auto', 'work_order', 'manual')",
            name="ck_spare_part_purchase_suggestions_source",
        ),
        # 未关闭的建议：同备件仅一条（自动扫描 upsert 依据）
        Index(
            "uq_spare_part_purchase_suggestions_open",
            "spare_part_id",
            unique=True,
            postgresql_where=text(
                "is_deleted = false AND status IN "
                "('suggested', 'submitted', 'partial')"
            ),
        ),
        {"schema": "equipment"},
    )

    spare_part_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.spare_parts.id"),
        comment="备件ID",
    )
    current_qty: Mapped[int] = mapped_column(comment="生成时库存")
    safety_qty: Mapped[int] = mapped_column(comment="安全线")
    suggest_qty: Mapped[int] = mapped_column(comment="建议采购数量")
    status: Mapped[str] = mapped_column(
        String(20), default="suggested", comment="状态"
    )
    source: Mapped[str] = mapped_column(
        String(20), default="auto", comment="来源：auto扫描/work_order工单/manual手动"
    )
    source_work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.work_orders.id"),
        nullable=True,
        comment="来源工单ID（source=work_order 时填）",
    )
    purchase_request_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="采购申请单ID（提交采购后回填）",
    )
    purchase_ref: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="采购回执摘要（单号/时间，冗余展示）",
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity.users.id"), nullable=True, comment="提交人"
    )
    submitted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="提交时间"
    )
    arrived_qty: Mapped[int] = mapped_column(
        default=0, server_default="0", comment="已到货数量"
    )
    unit_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True, comment="参考单价快照"
    )

    spare_part: Mapped[SparePart] = relationship(
        "SparePart", foreign_keys=[spare_part_id]
    )
    source_work_order: Mapped[WorkOrder | None] = relationship(
        "WorkOrder", foreign_keys=[source_work_order_id]
    )
