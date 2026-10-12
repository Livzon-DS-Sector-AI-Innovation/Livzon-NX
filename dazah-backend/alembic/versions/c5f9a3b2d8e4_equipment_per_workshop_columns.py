"""equipment per workshop columns

Revision ID: c5f9a3b2d8e4
Revises: b4e2f8a1c7d3
Create Date: 2026-10-12

设备模块全面按车间化第一步：台账（equipments）、备件（spare_parts）、
人员（equipment_personnel）三张主表增加 workshop_code（存量回填 201-1）；
维护保养（工单/维护计划/校准）经 equipment_id 关联派生车间，不加列。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c5f9a3b2d8e4"
down_revision = "b4e2f8a1c7d3"
branch_labels = None
depends_on = None

_WORKSHOP_CODE = "201-1"

_TABLES = [
    ("equipments", "ix_equipments_workshop"),
    ("spare_parts", "ix_spare_parts_workshop"),
    ("equipment_personnel", "ix_equipment_personnel_workshop"),
]


def upgrade() -> None:
    for table, index_name in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "workshop_code",
                sa.String(length=10),
                nullable=False,
                server_default=_WORKSHOP_CODE,
                comment="归属车间代码（如 101-1 / 201-1）",
            ),
            schema="equipment",
        )
        op.create_index(
            index_name,
            table,
            ["workshop_code"],
            schema="equipment",
        )


def downgrade() -> None:
    for table, index_name in _TABLES:
        op.drop_index(index_name, table_name=table, schema="equipment")
        op.drop_column(table, "workshop_code", schema="equipment")
