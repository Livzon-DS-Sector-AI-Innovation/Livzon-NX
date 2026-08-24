"""add_field_mapping_to_feishu_config

Revision ID: a92e3c435c3b
Revises: 7885e266358f
Create Date: 2026-07-02 16:45:09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a92e3c435c3b"
down_revision: str | None = "7885e266358f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "production_feishu_configs",
        sa.Column(
            "field_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        schema="production",
    )
    op.add_column(
        "production_feishu_configs",
        sa.Column("sync_table_name", sa.String(128), nullable=True),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column("production_feishu_configs", "sync_table_name", schema="production")
    op.drop_column("production_feishu_configs", "field_mapping", schema="production")
