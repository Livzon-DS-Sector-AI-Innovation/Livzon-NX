"""行政公告通知台账表

公告通知为平台原生台账（非飞书镜像）：上传公告文件 → AI 识别元数据
（编号/标题/发布单位/发布日期/类别/备注/公告内容）→ 人工确认入账。
公告内容与原文存档仅经 operate 权限绑定的专用端点下发；``search_text``
只拼元数据，避免关键字搜索泄露内容线索。

Revision ID: b6d8a2e4c9f1
Revises: f9a3d5c7e1b2
Create Date: 2026-11-23 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b6d8a2e4c9f1"
down_revision: str | None = "f9a3d5c7e1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    """每张表独立生成基础列（Column 对象不可跨表复用）。"""
    return [
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "notices",
        *_base_columns(),
        *_base_constraints(),
        sa.Column(
            "notice_no",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="公告编号",
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="公告标题",
        ),
        sa.Column(
            "publisher",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="发布单位",
        ),
        sa.Column("published_at", sa.Date(), nullable=True, comment="发布日期"),
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            server_default="",
            comment="公告类别",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="公告内容（仅 operate 专用端点下发）",
        ),
        sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        sa.Column(
            "source_file_name",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="原文文件名",
        ),
        sa.Column(
            "source_storage_key",
            sa.String(500),
            nullable=False,
            server_default="",
            comment="原文存储键（MinIO/本地回退）",
        ),
        sa.Column(
            "source_content_type",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="原文 MIME 类型",
        ),
        sa.Column(
            "source_size_bytes",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="原文大小（字节）",
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="元数据搜索文本（不含公告内容）",
        ),
        sa.Index(
            "ix_administration_notices_published_at",
            "published_at",
            unique=False,
        ),
        sa.Index(
            "ix_administration_notices_category",
            "category",
            unique=False,
        ),
        schema="administration",
    )


def downgrade() -> None:
    op.drop_table("notices", schema="administration")
