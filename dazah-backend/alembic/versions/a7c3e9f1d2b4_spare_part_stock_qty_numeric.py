"""备件现存量支持小数。

五金台账的结存量存在小数（米/千克等计量），Integer 会截断失真；
spare_part_stocks.current_qty 改为 Numeric(12, 2)。

Revision ID: a7c3e9f1d2b4
Revises: f2b4d8a6c1e9
Create Date: 2026-10-13

"""

import sqlalchemy as sa

from alembic import op

revision: str = "a7c3e9f1d2b4"
down_revision: str | None = "f2b4d8a6c1e9"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.alter_column(
        "spare_part_stocks",
        "current_qty",
        schema="equipment",
        existing_type=sa.Integer(),
        type_=sa.Numeric(12, 2),
        postgresql_using="current_qty::numeric(12,2)",
        comment="当前库存",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "spare_part_stocks",
        "current_qty",
        schema="equipment",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Integer(),
        postgresql_using="round(current_qty)::integer",
        existing_nullable=False,
    )
