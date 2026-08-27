"""add production feishu config

Revision ID: a7c100000019
Revises: a7c100000018
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c100000019"
down_revision: str | None = "a7c100000018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS production")
    op.create_table(
        "feishu_configs",
        sa.Column(
            "config_name", sa.String(length=128), nullable=False, comment="配置名称"
        ),
        sa.Column(
            "app_id", sa.String(length=128), nullable=False, comment="飞书应用 App ID"
        ),
        sa.Column(
            "encrypted_app_secret",
            sa.String(length=1024),
            nullable=False,
            comment="加密后的飞书应用 App Secret",
        ),
        sa.Column(
            "bitable_app_token",
            sa.String(length=128),
            nullable=False,
            comment="飞书多维表格 app_token",
        ),
        sa.Column(
            "table_id",
            sa.String(length=128),
            nullable=False,
            comment="飞书多维表格数据表 table_id",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_production_feishu_configs_is_active",
        "feishu_configs",
        ["is_active"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_production_feishu_configs_is_active",
        table_name="feishu_configs",
        schema="production",
    )
    op.drop_table("feishu_configs", schema="production")
