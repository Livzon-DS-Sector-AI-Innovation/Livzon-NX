"""create regulation radar tables for EHS regulation tracking

EHS 法规雷达：来源站点配置表 + 扫描批次表，并为 knowledge_articles 增加
来源类型、标准号、版本状态等跟踪字段。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a7c3e5b9d1f2"
down_revision: str | None = "f8d4b6e2c9a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── knowledge_articles 跟踪字段 ──
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "source_type",
            sa.String(length=20),
            server_default="feishu",
            nullable=False,
            comment="来源: feishu=飞书镜像 / manual=本地录入 / ai_radar=AI雷达发现",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "standard_no",
            sa.String(length=80),
            nullable=True,
            comment="标准号（如 GB 30871-2022，用于标准库检索）",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "version_status",
            sa.String(length=20),
            nullable=True,
            comment="标准版本状态: current=现行 / obsolete=已废止 / revised=已修订",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "version_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近版本核查时间",
        ),
        schema="safety",
    )
    op.add_column(
        "knowledge_articles",
        sa.Column(
            "ai_analysis",
            sa.JSON(),
            nullable=True,
            comment="AI 分析结果（相关性评分/判定理由/分析时间）",
        ),
        schema="safety",
    )
    op.create_index(
        "ix_knowledge_articles_source_type",
        "knowledge_articles",
        ["source_type"],
        schema="safety",
    )

    # ── 来源站点表 ──
    op.create_table(
        "regulation_radar_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "site_code", sa.String(length=50), nullable=False, comment="站点代码"
        ),
        sa.Column(
            "site_name", sa.String(length=120), nullable=False, comment="站点名称"
        ),
        sa.Column("domain", sa.String(length=120), nullable=False, comment="域名"),
        sa.Column(
            "channel",
            sa.String(length=30),
            server_default="column",
            nullable=False,
            comment="通道类型: column=栏目页抓取 / standard_search=标准号检索",
        ),
        sa.Column("list_url", sa.Text(), nullable=True, comment="栏目页地址"),
        sa.Column("parser", sa.String(length=50), nullable=True, comment="解析器标识"),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
            comment="是否启用",
        ),
        sa.Column(
            "last_crawled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近抓取时间",
        ),
        sa.Column(
            "last_status",
            sa.String(length=20),
            nullable=True,
            comment="最近抓取状态: success/failed",
        ),
        sa.Column("last_error", sa.Text(), nullable=True, comment="最近抓取错误信息"),
        sa.Column(
            "last_item_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="最近抓取条目数",
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
        "uq_regulation_radar_sites_domain_active",
        "regulation_radar_sites",
        ["domain"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )

    # ── 扫描批次表 ──
    op.create_table(
        "regulation_radar_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, comment="开始时间"
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="结束时间",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="running",
            nullable=False,
            comment="状态: running/success/partial/failed",
        ),
        sa.Column(
            "trigger",
            sa.String(length=20),
            server_default="manual",
            nullable=False,
            comment="触发方式: manual/schedule",
        ),
        sa.Column(
            "dry_run",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="是否干跑",
        ),
        sa.Column(
            "sites_total",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="参与站点数",
        ),
        sa.Column(
            "sites_failed",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="抓取失败站点数",
        ),
        sa.Column(
            "found_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="抓取条目总数",
        ),
        sa.Column(
            "new_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="判定为新法规数",
        ),
        sa.Column(
            "revised_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="判定为已修订/已废止数",
        ),
        sa.Column(
            "link_fixed_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="修复链接数",
        ),
        sa.Column(
            "skipped_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="跳过数（不相关/重复）",
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="处理失败数",
        ),
        sa.Column("items", sa.JSON(), nullable=True, comment="本批明细"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column(
            "is_acknowledged",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="页面提示是否已确认",
        ),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="确认时间",
        ),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        "ix_regulation_radar_runs_started",
        "regulation_radar_runs",
        ["started_at"],
        schema="safety",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_regulation_radar_runs_started",
        table_name="regulation_radar_runs",
        schema="safety",
    )
    op.drop_table("regulation_radar_runs", schema="safety")
    op.drop_index(
        "uq_regulation_radar_sites_domain_active",
        table_name="regulation_radar_sites",
        schema="safety",
    )
    op.drop_table("regulation_radar_sites", schema="safety")
    op.drop_index(
        "ix_knowledge_articles_source_type",
        table_name="knowledge_articles",
        schema="safety",
    )
    op.drop_column("knowledge_articles", "ai_analysis", schema="safety")
    op.drop_column("knowledge_articles", "version_checked_at", schema="safety")
    op.drop_column("knowledge_articles", "version_status", schema="safety")
    op.drop_column("knowledge_articles", "standard_no", schema="safety")
    op.drop_column("knowledge_articles", "source_type", schema="safety")
