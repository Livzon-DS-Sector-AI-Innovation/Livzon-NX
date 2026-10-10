"""排产约束配置模型。

按产品一行存放排产校验与后续自动排产共用的工艺参数（当前仅 FA
使用）。数值可留空，留空时依赖该参数的校验自动跳过；由排产计划页
「排产约束」卡片维护。领域规则见 docs/production-fa-scheduling-rules.md。
"""
from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class ScheduleConstraintSetting(BaseModel):
    """排产约束配置（按产品）"""

    __tablename__ = "schedule_constraint_settings"
    __table_args__ = (
        Index(
            "ux_schedule_constraint_settings_product",
            "product_code",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        {"schema": "production"},
    )

    product_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="FA",
        comment="产品代码（当前仅 FA，其余产品为二期预留）",
    )
    standard_cycle_hours: Mapped[float | None] = mapped_column(
        Float(), nullable=True, comment="标准培养周期(h)"
    )
    cycle_tolerance_hours: Mapped[float | None] = mapped_column(
        Float(), nullable=True, comment="周期容差(h)：容差内视为正常波动"
    )
    max_cycle_hours: Mapped[float | None] = mapped_column(
        Float(), nullable=True, comment="最大培养周期(h)：工艺上限，超过视为排错"
    )
    turnaround_hours: Mapped[float | None] = mapped_column(
        Float(), nullable=True, comment="罐最小周转时间(h)：放罐结束到下次移种"
    )
    monthly_dump_target: Mapped[int | None] = mapped_column(
        Integer(), nullable=True, comment="月计划放罐批数"
    )
