"""add identity feishu configs

Revision ID: 7c4f2a9b1d6e
Revises: 9a1b2c3d4e5f
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c4f2a9b1d6e"
down_revision: str | None = "9a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.create_table(
        "feishu_configs",
        sa.Column("config_name", sa.String(length=128), nullable=False),
        sa.Column("app_id", sa.String(length=128), nullable=False),
        sa.Column("encrypted_app_secret", sa.String(length=1024), nullable=False),
        sa.Column("sync_root_department_id", sa.String(length=128), nullable=True),
        sa.Column("sync_member_department_id", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_sync_status", sa.String(length=32), nullable=True),
        sa.Column("last_sync_message", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_diagnostic_status", sa.String(length=32), nullable=True),
        sa.Column("last_diagnostic_message", sa.Text(), nullable=True),
        sa.Column("last_diagnostic_result", sa.Text(), nullable=True),
        sa.Column("last_diagnosed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("config_name", name="uq_identity_feishu_configs_name"),
        schema="identity",
    )
    op.create_index(
        "ix_identity_feishu_configs_is_active",
        "feishu_configs",
        ["is_active"],
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_feishu_configs_is_active",
        table_name="feishu_configs",
        schema="identity",
    )
    op.drop_table("feishu_configs", schema="identity")
