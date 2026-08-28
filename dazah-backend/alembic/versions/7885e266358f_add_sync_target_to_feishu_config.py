"""add_sync_target_to_feishu_config

Revision ID: 7885e266358f
Revises: 8541257dec7e
Create Date: 2026-07-02 16:16:35
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7885e266358f"
down_revision: str | None = "8541257dec7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "production_feishu_configs",
        sa.Column(
            "sync_target",
            sa.String(32),
            nullable=False,
            server_default="production_plan",
            comment="同步目标",
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_column("production_feishu_configs", "sync_target", schema="production")
