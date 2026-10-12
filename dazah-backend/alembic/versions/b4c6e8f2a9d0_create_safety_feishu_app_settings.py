"""create safety.feishu_app_settings for web-managed feishu credentials

安全模块飞书凭证从环境变量迁移到数据库配置页（对齐质量/仓储模块）：
新增单行配置表，App Secret 加密存储；SAFETY_FEISHU_* 环境变量停用。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b4c6e8f2a9d0"
down_revision: str | None = "b7d2e4f60a58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feishu_app_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "app_id", sa.String(length=100), nullable=False, comment="飞书应用 App ID"
        ),
        sa.Column(
            "app_secret",
            sa.Text(),
            nullable=False,
            comment="飞书应用 App Secret（加密存储）",
        ),
        sa.Column(
            "bitable_app_token",
            sa.String(length=100),
            nullable=True,
            comment="隐患多维表格 app_token",
        ),
        sa.Column(
            "bitable_hazard_table_id",
            sa.String(length=100),
            nullable=True,
            comment="隐患多维表格 table_id",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用安全模块飞书集成",
        ),
        sa.Column(
            "last_test_status",
            sa.String(length=20),
            nullable=True,
            comment="最近连接测试状态: success/failed",
        ),
        sa.Column(
            "last_test_error", sa.Text(), nullable=True, comment="最近连接测试错误信息"
        ),
        sa.Column(
            "last_tested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近连接测试时间",
        ),
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
            "is_deleted", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["identity.users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["identity.users.id"],
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("feishu_app_settings", schema="safety")
