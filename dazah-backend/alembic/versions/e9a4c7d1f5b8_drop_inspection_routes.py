"""drop inspection routes

Revision ID: e9a4c7d1f5b8
Revises: d8f2a5b7c4e6
Create Date: 2026-10-10

设备巡检移除「巡检线路」概念：任务直接按设备+模板执行。
删除路线、路线排程、路线-设备、路线-地点、地点-设备、
地点-设备-模板六张表，以及任务表的路线字段、巡检记录的
路线地点字段。开发库中相关表均无数据。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e9a4c7d1f5b8"
down_revision = "d8f2a5b7c4e6"
branch_labels = None
depends_on = None

_DROP_TABLES = [
    # 依赖顺序：先子表后父表
    "route_equipment_templates",
    "route_location_equipments",
    "route_locations",
    "inspection_route_equipments",
    "inspection_route_schedules",
    "inspection_routes",
]


def upgrade() -> None:
    op.drop_column(
        "inspection_records",
        "route_location_id",
        schema="equipment",
    )
    op.drop_column("inspection_tasks", "route_summary", schema="equipment")
    op.drop_column("inspection_tasks", "route_id", schema="equipment")
    for table in _DROP_TABLES:
        op.execute(f'DROP TABLE IF EXISTS equipment."{table}" CASCADE')


def downgrade() -> None:
    # 线路结构已从代码中移除，降级仅恢复任务表的列占位，不恢复路线表
    op.add_column(
        "inspection_tasks",
        sa.Column("route_id", sa.Uuid(), nullable=True),
        schema="equipment",
    )
    op.add_column(
        "inspection_tasks",
        sa.Column("route_summary", sa.Text(), nullable=True),
        schema="equipment",
    )
    op.add_column(
        "inspection_records",
        sa.Column("route_location_id", sa.Uuid(), nullable=True),
        schema="equipment",
    )
