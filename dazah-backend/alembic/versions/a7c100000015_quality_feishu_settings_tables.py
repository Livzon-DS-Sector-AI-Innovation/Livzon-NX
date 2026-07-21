"""add quality feishu settings tables

Revision ID: a7c100000015
Revises: a7c100000014
Create Date: 2026-07-03 23:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7c100000015"
down_revision: str | None = "a7c100000014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SCHEMA_NAME = "quality"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")

    op.create_table(
        "quality_feishu_app_settings",
        sa.Column("app_id", sa.String(length=100), nullable=False),
        sa.Column("app_secret", sa.Text(), nullable=False),
        sa.Column("app_token", sa.String(length=100), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("last_test_status", sa.String(length=20), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=SCHEMA_NAME,
    )

    op.create_table(
        "quality_feishu_entity_settings",
        sa.Column("entity_code", sa.String(length=100), nullable=False),
        sa.Column("entity_name", sa.String(length=100), nullable=False),
        sa.Column("entity_group", sa.String(length=100), nullable=False),
        sa.Column("base_table_name", sa.String(length=100), nullable=True),
        sa.Column("base_table_id", sa.String(length=100), nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "enable_push_to_feishu",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "enable_pull_from_feishu",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_sync_status", sa.String(length=20), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.UniqueConstraint("entity_code", name="uq_quality_feishu_entity_settings_code"),
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.drop_table("quality_feishu_entity_settings", schema=SCHEMA_NAME)
    op.drop_table("quality_feishu_app_settings", schema=SCHEMA_NAME)