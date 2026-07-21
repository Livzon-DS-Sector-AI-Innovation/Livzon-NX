"""add warehouse feishu tables

Revision ID: a6f2c8d4e9b1
Revises: 8d5b8f4d2c31
Create Date: 2026-06-30 15:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6f2c8d4e9b1"
down_revision: str | None = "8d5b8f4d2c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS warehouse")
    op.create_table(
        "feishu_tables",
        sa.Column(
            "app_token",
            sa.String(length=128),
            nullable=False,
            comment="飞书多维表格 app_token",
        ),
        sa.Column(
            "table_id",
            sa.String(length=128),
            nullable=False,
            comment="飞书多维表格 table_id",
        ),
        sa.Column("name", sa.String(length=255), nullable=False, comment="数据表名称"),
        sa.Column("revision", sa.Integer(), nullable=True, comment="飞书表 revision"),
        sa.Column(
            "last_discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最近发现时间",
        ),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近事件时间",
        ),
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
        "ix_warehouse_feishu_tables_app_token",
        "feishu_tables",
        ["app_token"],
        unique=False,
        schema="warehouse",
    )
    op.create_index(
        "uq_warehouse_feishu_tables_app_token_table_id",
        "feishu_tables",
        ["app_token", "table_id"],
        unique=True,
        schema="warehouse",
    )


def downgrade() -> None:
    op.drop_index(
        "uq_warehouse_feishu_tables_app_token_table_id",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.drop_index(
        "ix_warehouse_feishu_tables_app_token",
        table_name="feishu_tables",
        schema="warehouse",
    )
    op.drop_table("feishu_tables", schema="warehouse")
