"""safety knowledge articles align with EHS feishu bitable

安全知识库对齐 EHS 法规数据库多维表格：
- knowledge_articles 增加 EHS 法规字段、飞书镜像元数据（record_id 部分唯一）
- feishu_app_settings 增加 EHS 法规库绑定与同步状态列
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2f5a8c0e3b1"
down_revision: str | None = "b4c6e8f2a9d0"  # noqa: E501
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "article_no", sa.String(length=100), nullable=True, comment="法规编号"
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "regulation_category",
            sa.String(length=64),
            nullable=True,
            comment="法规类别（飞书原始值）",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column("source", sa.String(length=255), nullable=True, comment="颁布机关"),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "promulgation_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="颁布修订日期",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "implement_date",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="实施日期",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "regulation_status",
            sa.String(length=50),
            nullable=True,
            comment="法规状态（如 现行有效）",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "update_status",
            sa.String(length=50),
            nullable=True,
            comment="更新状态（如 新增/已更新）",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column("regulation_link", sa.Text(), nullable=True, comment="法规链接"),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column("notes", sa.Text(), nullable=True, comment="备注"),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "feishu_record_id",
            sa.String(length=50),
            nullable=True,
            comment="飞书多维表格 record_id（镜像唯一键）",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "feishu_attachments",
            sa.JSON(),
            nullable=True,
            comment="飞书附件快照 [{file_token,name,size}]",
        ),
        schema="safety",
    )
    op.create_index(
        "uq_knowledge_articles_feishu_record_active",
        "knowledge_articles",
        ["feishu_record_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false AND feishu_record_id IS NOT NULL"),
        schema="safety",
    )

    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "knowledge_app_token",
            sa.String(length=100),
            nullable=True,
            comment="EHS 法规库多维表格 app_token",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "knowledge_table_id",
            sa.String(length=100),
            nullable=True,
            comment="EHS 法规库多维表格 table_id",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "knowledge_last_sync_status",
            sa.String(length=20),
            nullable=True,
            comment="知识库最近同步状态: success/failed",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "knowledge_last_sync_error",
            sa.Text(),
            nullable=True,
            comment="知识库最近同步错误信息",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "knowledge_last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="知识库最近同步时间",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("feishu_app_settings", "knowledge_last_synced_at", schema="safety")
    op.drop_column("feishu_app_settings", "knowledge_last_sync_error", schema="safety")
    op.drop_column("feishu_app_settings", "knowledge_last_sync_status", schema="safety")
    op.drop_column("feishu_app_settings", "knowledge_table_id", schema="safety")
    op.drop_column("feishu_app_settings", "knowledge_app_token", schema="safety")
    op.drop_index(
        "uq_knowledge_articles_feishu_record_active",
        table_name="knowledge_articles",
        schema="safety",
    )
    op.drop_column("knowledge_articles", "feishu_attachments", schema="safety")
    op.drop_column("knowledge_articles", "feishu_record_id", schema="safety")
    op.drop_column("knowledge_articles", "notes", schema="safety")
    op.drop_column("knowledge_articles", "regulation_link", schema="safety")
    op.drop_column("knowledge_articles", "update_status", schema="safety")
    op.drop_column("knowledge_articles", "regulation_status", schema="safety")
    op.drop_column("knowledge_articles", "implement_date", schema="safety")
    op.drop_column("knowledge_articles", "promulgation_date", schema="safety")
    op.drop_column("knowledge_articles", "source", schema="safety")
    op.drop_column("knowledge_articles", "regulation_category", schema="safety")
    op.drop_column("knowledge_articles", "article_no", schema="safety")
