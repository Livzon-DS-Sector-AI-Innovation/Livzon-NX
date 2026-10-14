"""create safety.page_feishu_configs for page bitable bindings

镜像页（如「24小时值班隐患」）与飞书多维表格的绑定从代码移入数据库：
每个镜像页一行，记录 app_token / table_id / view_id / 隐藏字段 / 开关与
最近绑定测试结论，由「安全飞书设置」页维护，避免把多维表格配置写死在代码里。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c5d7e9a1b3f4"
# 主线在 d9e1f2a4b6c8 之后并行合入了 c5f9a3b2d8e4（设备按车间隔离），
# 本批基于旧主线开发导致分叉；把本迁移接在主线头之后恢复单链。
down_revision: str | None = "c5f9a3b2d8e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_feishu_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "page_key",
            sa.String(length=160),
            nullable=False,
            comment="页面标识（安全模块菜单页面 key）",
        ),
        sa.Column(
            "app_token",
            sa.String(length=100),
            nullable=True,
            comment="多维表格 app_token",
        ),
        sa.Column(
            "table_id",
            sa.String(length=100),
            nullable=True,
            comment="多维表格 table_id",
        ),
        sa.Column(
            "view_id",
            sa.String(length=100),
            nullable=True,
            comment="多维表格 view_id（仅记录，不做服务端视图过滤）",
        ),
        sa.Column(
            "hidden_field_names",
            sa.JSON(),
            nullable=True,
            comment="页面隐藏的字段名列表",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用该页面的表格绑定",
        ),
        sa.Column(
            "last_test_status",
            sa.String(length=20),
            nullable=True,
            comment="最近绑定测试状态: success/failed",
        ),
        sa.Column(
            "last_test_error",
            sa.Text(),
            nullable=True,
            comment="最近绑定测试错误信息",
        ),
        sa.Column(
            "last_tested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近绑定测试时间",
        ),
        sa.Column(
            "last_test_field_count",
            sa.Integer(),
            nullable=True,
            comment="最近绑定测试读到的字段数",
        ),
        sa.Column(
            "last_test_record_count",
            sa.Integer(),
            nullable=True,
            comment="最近绑定测试读到的记录数",
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        schema="safety",
    )
    op.create_index(
        "uq_safety_page_feishu_configs_page_key",
        "page_feishu_configs",
        ["page_key"],
        unique=True,
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_safety_page_feishu_configs_page_key",
        table_name="page_feishu_configs",
        schema="safety",
    )
    op.drop_table("page_feishu_configs", schema="safety")
