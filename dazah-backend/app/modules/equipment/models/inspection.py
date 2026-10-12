"""Inspection ORM models: tasks, photos."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel

if TYPE_CHECKING:
    from app.modules.equipment.models.equipment import Equipment
    from app.platform.identity.models import User


class InspectionTask(BaseModel):
    """巡检任务表"""

    __tablename__ = "inspection_tasks"
    __table_args__ = (
        UniqueConstraint("task_no", "is_deleted", name="uq_inspection_tasks_task_no"),
        CheckConstraint(
            "status IN ('待执行', '执行中', '已完成', '已关闭')",
            name="ck_inspection_tasks_status",
        ),
        CheckConstraint(
            "plan_type IN ('线路巡检', '设备巡检')",
            name="ck_inspection_tasks_plan_type",
        ),
        CheckConstraint(
            "overall_result IS NULL OR overall_result IN ('正常', '异常')",
            name="ck_inspection_tasks_overall_result",
        ),
        {"schema": "equipment"},
    )

    task_no: Mapped[str] = mapped_column(
        String(50), comment="任务编号 IT-yyyymmdd-xxxx"
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        nullable=True,
        comment="单设备ID（单设备模式，兼容旧数据）",
    )
    equipment_ids: Mapped[list[str] | None] = mapped_column(
        JSON, nullable=True, comment="设备ID列表（多设备模式）"
    )
    template_ids: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="[DEPRECATED] 模板ID列表，推荐用 equipment_templates",
    )
    equipment_templates: Mapped[dict[str, list[str]] | None] = mapped_column(
        JSON, nullable=True, comment="设备-模板绑定 {equipment_id: [template_id,...]}"
    )
    plan_type: Mapped[str] = mapped_column(
        String(20),
        default="设备巡检",
        comment="巡检类型：线路巡检/设备巡检",
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="巡检人员ID",
    )
    planned_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), comment="计划巡检时间"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="待执行",
        comment="任务状态：待执行/执行中/已完成/已关闭",
    )
    overall_result: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="总体结果：正常/异常"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="开始时间"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="完成时间"
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="关闭时间"
    )
    closure_remark: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="关闭备注"
    )

    # 关系
    equipment: Mapped[Equipment | None] = relationship(
        "Equipment", foreign_keys=[equipment_id]
    )
    assignee: Mapped[User | None] = relationship("User", foreign_keys=[assigned_to])


class InspectionPhoto(BaseModel):
    """巡检到位照片表"""

    __tablename__ = "inspection_photos"
    __table_args__ = ({"schema": "equipment"},)

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.inspection_tasks.id"),
        comment="巡检任务ID",
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.equipments.id"),
        nullable=True,
        comment="设备ID（线路巡检时可为空）",
    )
    file_name: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(500), comment="服务器文件路径")
    file_size: Mapped[int | None] = mapped_column(comment="文件大小（字节）")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="上传时间",
    )
