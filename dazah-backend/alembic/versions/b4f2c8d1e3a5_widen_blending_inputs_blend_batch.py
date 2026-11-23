"""Widen blending_inputs.blend_batch for multi-batch cells

Revision ID: b4f2c8d1e3a5
Revises: c7d9e1f3a5b7
Create Date: 2026-11-14 12:00:00.000000

混粉杂质计算源表的「混合批号」列存在多批号连写（如
"MC-260714    USMC-M-2607007 USMC-M-2607008"，44 字符），
varchar(32) 截断报错导致该工段同步失败；加宽到 varchar(255)。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4f2c8d1e3a5"
down_revision: str | None = "c7d9e1f3a5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "blending_inputs",
        "blend_batch",
        existing_type=sa.String(32),
        type_=sa.String(255),
        existing_nullable=False,
        schema="production",
    )


def downgrade() -> None:
    op.alter_column(
        "blending_inputs",
        "blend_batch",
        existing_type=sa.String(255),
        type_=sa.String(32),
        existing_nullable=False,
        schema="production",
    )
