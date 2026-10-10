"""create inspection feishu config

Revision ID: a3d8f2c6e1b9
Revises: f1c7e9a3d4b6
Create Date: 2026-10-10

设备巡检飞书镜像配置表：应用凭据（App Secret 加密存储）、
三张多维表格引用与连接测试状态。数据库行优先于
EQUIPMENT_FEISHU_* 环境变量回退。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a3d8f2c6e1b9"
down_revision = "f1c7e9a3d4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspection_feishu_config",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column(
            "app_id", sa.String(length=100),
            nullable=False, server_default="", comment="飞书应用 App ID",
        ),
        sa.Column(
            "app_secret", sa.Text(),
            nullable=False, server_default="",
            comment="飞书应用 App Secret（加密存储）",
        ),
        sa.Column(
            "app_token", sa.String(length=200),
            nullable=False, server_default="", comment="多维表格 App Token",
        ),
        sa.Column(
            "today_table_id", sa.String(length=100),
            nullable=False, server_default="", comment="今日巡检表 ID",
        ),
        sa.Column(
            "history_table_id", sa.String(length=100),
            nullable=False, server_default="",
            comment="设备历史巡检记录表 ID",
        ),
        sa.Column(
            "device_table_id", sa.String(length=100),
            nullable=False, server_default="", comment="设备档案表 ID",
        ),
        sa.Column(
            "is_enabled", sa.Boolean(),
            server_default=sa.text("true"), nullable=False,
            comment="启用镜像同步",
        ),
        sa.Column(
            "last_test_status", sa.String(length=20), nullable=True,
            comment="最近连接测试结果",
        ),
        sa.Column(
            "last_test_error", sa.Text(), nullable=True,
            comment="最近连接测试失败原因",
        ),
        sa.Column(
            "last_tested_at", sa.DateTime(timezone=True), nullable=True,
            comment="最近连接测试时间",
        ),
        schema="equipment",
    )


def downgrade() -> None:
    op.drop_table("inspection_feishu_config", schema="equipment")
