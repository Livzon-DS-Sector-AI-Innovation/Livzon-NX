"""Maintenance labor rate ORM model（维修工时费率）."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class MaintenanceLaborRate(BaseModel):
    """维修工时费率：岗位级（scope=role）或人员级（scope=person，优先）。

    解析优先级：person > role > 0（未配置不计工时成本）。
    """

    __tablename__ = "maintenance_labor_rates"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('role', 'person')",
            name="ck_maintenance_labor_rates_scope",
        ),
        CheckConstraint(
            "(scope = 'role' AND role_id IS NOT NULL) "
            "OR (scope = 'person' AND person_id IS NOT NULL)",
            name="ck_maintenance_labor_rates_target",
        ),
        # 费率可保留历史行（生效日期不同）；未删除行内同目标仅一条当前费率
        UniqueConstraint(
            "scope",
            "role_id",
            "person_id",
            "is_deleted",
            name="uq_maintenance_labor_rates_target",
        ),
        {"schema": "equipment"},
    )

    scope: Mapped[str] = mapped_column(String(10), comment="范围：role/person")
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.equipment_role.id"),
        nullable=True,
        comment="设备角色ID（scope=role）",
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity.users.id"),
        nullable=True,
        comment="人员用户ID（scope=person）",
    )
    hourly_rate: Mapped[float] = mapped_column(
        Numeric(10, 2), comment="时薪（元/小时）"
    )
    effective_from: Mapped[dt.date] = mapped_column(
        Date, comment="生效日期"
    )
    remark: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="备注"
    )
