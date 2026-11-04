"""Repair knowledge case ORM model（维修知识案例库）."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.equipment import Equipment
    from app.modules.equipment.models.work_order import WorkOrder


class RepairKnowledgeCase(BaseModel):
    """维修知识案例：故障维修工单验收合格后由维修人确认入库"""

    __tablename__ = "repair_knowledge_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'verified', 'dismissed')",
            name="ck_repair_knowledge_cases_status",
        ),
        {"schema": "equipment"},
    )

    source_work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.work_orders.id"),
        nullable=True,
        comment="来源工单ID（人工补录可为空）",
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        nullable=True,
        comment="设备ID（检索本设备层）",
    )
    equipment_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.equipment_categories.id"),
        nullable=True,
        comment="设备分类ID（检索同分类层）",
    )
    workshop_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="车间代码（展示用）"
    )
    symptom_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="故障现象代码"
    )
    symptom_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="故障现象名称"
    )
    cause_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="故障原因代码"
    )
    cause_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="故障原因名称"
    )
    action_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="维修措施代码"
    )
    action_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="维修措施名称"
    )
    fault_description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="故障描述"
    )
    repair_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="维修过程描述"
    )
    key_steps: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="关键维修步骤（LLM 抽取建议，人工确认后入库）",
    )
    parts_used: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="使用备件清单 [{spare_part_id,name,qty}]",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        comment="状态：draft草稿/verified已入库/dismissed已忽略",
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="确认人ID",
    )
    verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="确认时间"
    )
    use_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="被推荐采纳次数"
    )
    equipment_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="设备名称快照（列表展示）"
    )
    equipment_no: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="设备编号快照"
    )

    source_work_order: Mapped[WorkOrder | None] = relationship(
        "WorkOrder", foreign_keys=[source_work_order_id]
    )
    equipment: Mapped[Equipment | None] = relationship(
        "Equipment", foreign_keys=[equipment_id]
    )
