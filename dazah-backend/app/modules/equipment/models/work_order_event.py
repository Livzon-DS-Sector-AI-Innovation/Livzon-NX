"""Work order event ORM model（工单事件流水）."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.work_order import WorkOrder


class WorkOrderEvent(BaseModel):
    """工单事件流水：时间线与审计的唯一事实源（方案E）。

    event_type: created/assigned/transferred/started/completed/verified/
    rejected/closed/claimed/material_requested/suggested_purchase
    """

    __tablename__ = "work_order_events"
    __table_args__ = ({"schema": "equipment"},)

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.work_orders.id"),
        comment="工单ID",
    )
    event_type: Mapped[str] = mapped_column(String(30), comment="事件类型")
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True, comment="操作人（空=系统）"
    )
    operator_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="操作人姓名"
    )
    source: Mapped[str] = mapped_column(
        String(20), default="web", server_default="web",
        comment="来源：web/feishu/voice/scheduler/system",
    )
    message_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="关联卡片消息ID"
    )
    detail: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="事件附加信息"
    )

    work_order: Mapped[WorkOrder] = relationship(
        "WorkOrder", foreign_keys=[work_order_id]
    )
