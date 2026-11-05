"""restore maintenance_labor_rates.role_id foreign key

Revision ID: c5f1a8d3b6e2
Revises: c2d8f4b6e7a9
Create Date: 2026-11-04 06:30:00.000000

背景：c2d8f4b6e7a9 建表时误判 equipment.equipment_role 不存在（查询用了
复数表名），将 role_id 降级为软引用。实际该表一直存在，本迁移恢复库级
外键约束。
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5f1a8d3b6e2'
down_revision: str | None = 'c2d8f4b6e7a9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 先清理可能存在的脏引用，再加约束
    op.execute(
        "DELETE FROM equipment.maintenance_labor_rates r "
        "WHERE r.role_id IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM equipment.equipment_role e WHERE e.id = r.role_id)"
    )
    op.create_foreign_key(
        "fk_maintenance_labor_rates_role",
        "maintenance_labor_rates",
        "equipment_role",
        ["role_id"],
        ["id"],
        source_schema="equipment",
        referent_schema="equipment",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_maintenance_labor_rates_role",
        "maintenance_labor_rates",
        schema="equipment",
        type_="foreignkey",
    )
