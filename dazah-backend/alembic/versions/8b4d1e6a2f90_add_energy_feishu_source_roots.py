"""add energy Feishu source roots

Revision ID: 8b4d1e6a2f90
Revises: 7f3a9c2d1e4b
Create Date: 2026-07-21 17:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8b4d1e6a2f90"
down_revision: str | None = "7f3a9c2d1e4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feishu_source_roots",
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("root_token", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "discovery_status", sa.String(32), server_default="pending", nullable=False
        ),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovery_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "config_id",
            "source_type",
            "root_token",
            "is_deleted",
            name="uq_energy_feishu_source_root",
        ),
        schema="energy",
    )
    op.create_index(
        "ix_energy_feishu_source_roots_config",
        "feishu_source_roots",
        ["config_id", "is_active"],
        schema="energy",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_energy_feishu_source_roots_config",
        table_name="feishu_source_roots",
        schema="energy",
    )
    op.drop_table("feishu_source_roots", schema="energy")
