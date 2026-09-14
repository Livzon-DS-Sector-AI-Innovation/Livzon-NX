"""add extract_kg to fermentation_batch_actuals

Revision ID: b5d2e8a4c6f9
Revises: 957e2da4f7c7
Create Date: 2026-09-11

提炼工段上线：批次实际产量表增加提炼成品产量列（可空），
与放罐产量同批复核算收率；历史行缺省为 NULL 不受影响。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b5d2e8a4c6f9"
down_revision = "957e2da4f7c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fermentation_batch_actuals",
        sa.Column(
            "extract_kg",
            sa.Float(),
            nullable=True,
            comment="提炼成品产量(kg)",
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column(
        "fermentation_batch_actuals",
        "extract_kg",
        schema="production",
    )
