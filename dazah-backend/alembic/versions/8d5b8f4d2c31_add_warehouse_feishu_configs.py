"""add warehouse feishu configs

Revision ID: 8d5b8f4d2c31
Revises: 21e7046001c0
Create Date: 2026-06-30 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d5b8f4d2c31"
down_revision: str | None = "21e7046001c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS warehouse")
    op.create_table(
        "feishu_configs",
        sa.Column(
            "config_name",
            sa.String(length=128),
            nullable=False,
            comment="配置名称",
        ),
        sa.Column(
            "app_id",
            sa.String(length=128),
            nullable=False,
            comment="飞书应用 App ID",
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
            "raw_material_table_id",
            sa.String(length=128),
            nullable=True,
            comment="原辅料库存表 table_id",
        ),
        sa.Column(
            "packaging_table_id",
            sa.String(length=128),
            nullable=True,
            comment="包材库存表 table_id",
        ),
        sa.Column(
            "product_table_id",
            sa.String(length=128),
            nullable=True,
            comment="成品库存表 table_id",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="是否启用",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
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
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="warehouse",
    )
    op.create_index(
        "ix_warehouse_feishu_configs_is_active",
        "feishu_configs",
        ["is_active"],
        unique=False,
        schema="warehouse",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_warehouse_feishu_configs_is_active",
        table_name="feishu_configs",
        schema="warehouse",
    )
    op.drop_table("feishu_configs", schema="warehouse")
