"""车间维度过滤辅助。

台账/备件/人员主表自带 workshop_code 列；维护类实体（工单、维护计划、
校准计划与记录）经 equipment_id 关联 equipments 派生车间，用 EXISTS
子查询过滤，避免改动各实体表结构。
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.sql.selectable import Exists

from app.modules.equipment.models.equipment import Equipment


def equipment_workshop_filter(
    equipment_id_column: Any, workshop_code: str
) -> Exists:
    """EXISTS 子查询：实体所属设备归属指定车间。"""
    return sa.exists(
        sa.select(Equipment.id).where(
            Equipment.id == equipment_id_column,
            Equipment.workshop_code == workshop_code,
            Equipment.is_deleted == False,  # noqa: E712
        )
    )
