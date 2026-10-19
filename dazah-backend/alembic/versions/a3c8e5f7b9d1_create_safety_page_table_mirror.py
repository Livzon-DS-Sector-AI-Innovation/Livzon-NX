"""create safety.page_table_mirror_records + mirror columns on page_feishu_configs

页面镜像数据源：本地全量副本（定时同步 + 编辑写透），消除实时拉取的
2000 条窗口限制；绑定行新增镜像开关与最近同步状态回显。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3c8e5f7b9d1"
# 主线在并行合入 807ad84a1158（merge feedback and equipment safety）后，
# 本批基于旧主线开发产生分叉；改接主线头恢复单链。
# 主线在 807ad84a1158 之后并行合入 c4e6f8a0b2d1（equipment ledger archives），
# 本批基于旧主线开发产生分叉；改接主线头恢复单链。
down_revision: str | None = "c4e6f8a0b2d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_table_mirror_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "page_key",
            sa.String(length=160),
            nullable=False,
            comment="页面标识（对齐 page_feishu_configs）",
        ),
        sa.Column(
            "record_id",
            sa.String(length=64),
            nullable=False,
            comment="飞书记录 record_id",
        ),
        sa.Column(
            "fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="解码后的字段值（中文列名为键）",
        ),
        sa.Column(
            "search_text",
            sa.Text(),
            server_default="",
            nullable=False,
            comment="关键字搜索文本",
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="该行最近同步/写透时间",
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
        "uq_safety_page_table_mirror_records_page_record",
        "page_table_mirror_records",
        ["page_key", "record_id"],
        unique=True,
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "ix_safety_page_table_mirror_records_page",
        "page_table_mirror_records",
        ["page_key", "is_deleted"],
        schema="safety",
    )

    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "is_mirrored",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否使用本地镜像数据源（关闭则实时拉取飞书）",
        ),
        schema="safety",
    )
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近镜像同步完成时间",
        ),
        schema="safety",
    )
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "last_sync_status",
            sa.String(length=20),
            nullable=True,
            comment="最近镜像同步状态: success/failed",
        ),
        schema="safety",
    )
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "last_sync_error",
            sa.Text(),
            nullable=True,
            comment="最近镜像同步错误信息",
        ),
        schema="safety",
    )
    op.add_column(
        "page_feishu_configs",
        sa.Column(
            "last_sync_record_count",
            sa.Integer(),
            nullable=True,
            comment="最近镜像同步记录数",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("page_feishu_configs", "last_sync_record_count", schema="safety")
    op.drop_column("page_feishu_configs", "last_sync_error", schema="safety")
    op.drop_column("page_feishu_configs", "last_sync_status", schema="safety")
    op.drop_column("page_feishu_configs", "last_synced_at", schema="safety")
    op.drop_column("page_feishu_configs", "is_mirrored", schema="safety")
    op.drop_index(
        "ix_safety_page_table_mirror_records_page",
        table_name="page_table_mirror_records",
        schema="safety",
    )
    op.drop_index(
        "uq_safety_page_table_mirror_records_page_record",
        table_name="page_table_mirror_records",
        schema="safety",
    )
    op.drop_table("page_table_mirror_records", schema="safety")
