"""add_product_name_to_seed_cultures

Revision ID: 9f6a7b8c0d1e
Revises: 8e5f6a7b9c0d
Create Date: 2026-07-06 18:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision: str = "9f6a7b8c0d1e"
down_revision = "8e5f6a7b9c0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "seed_cultures",
        sa.Column("product_name", sa.String(64), nullable=True),
        schema="production",
    )
    op.execute(
        "UPDATE production.seed_cultures SET product_name = '' WHERE product_name IS NULL"  # noqa: E501
    )
    op.alter_column(
        "seed_cultures", "product_name", nullable=False, schema="production"
    )


def downgrade() -> None:
    op.drop_column("seed_cultures", "product_name", schema="production")
