"""安全承诺日报与信息卡（应急〔2018〕74号 承诺公告制度）

- ``safety.safety_commitment_reports``：每日安全风险研判与承诺公告日报，
  非软删内 report_date 唯一——一自然日一条。
- ``safety.safety_commitment_cards``：安全承诺页左右滚动信息卡
  （安全承诺信息 / 重大危险源信息）。
- ``safety.feishu_app_settings``：新增安全承诺推送配置 4 列
  （开关 / 推送时间 / 公告群 / 填报人员）。

Revision ID: e4c7a1b9d5f3
Revises: d7b2f9a4c1e6
Create Date: 2026-11-09 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e4c7a1b9d5f3"
down_revision: str | None = "d7b2f9a4c1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

jsonb = postgresql.JSONB(astext_type=sa.Text())


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
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default="false"
        ),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    op.create_table(
        "safety_commitment_reports",
        *_base_columns(),
        sa.Column(
            "report_date", sa.Date(), nullable=False,
            comment="报告日期（自然日）",
        ),
        sa.Column(
            "enterprise_status",
            jsonb,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="企业状态结构化数据（车间/装置/特殊作业/隐患/承包商/重大危险源/包保责任人）",
        ),
        sa.Column(
            "commitment_text",
            sa.Text(),
            nullable=True,
            comment="企业安全承诺公告正文（可编辑）",
        ),
        sa.Column(
            "risk_assessment",
            jsonb,
            nullable=True,
            comment="AI 风险研判结果（等级/摘要/风险/建议/依据）",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
            comment="状态: draft=草稿 published=已发布",
        ),
        sa.Column(
            "publisher_name",
            sa.String(100),
            nullable=True,
            comment="承诺人（主要负责人）姓名",
        ),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="发布时间",
        ),
        sa.Column(
            "fill_source",
            sa.String(20),
            nullable=True,
            comment="最近一次填报来源: web/feishu",
        ),
        sa.ForeignKeyConstraint(["published_by"], ["identity.users.id"]),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_safety_commitment_reports_date",
        "safety_commitment_reports",
        ["report_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema="safety",
    )

    op.create_table(
        "safety_commitment_cards",
        *_base_columns(),
        sa.Column(
            "card_type",
            sa.String(32),
            nullable=False,
            comment="卡片类型: commitment=安全承诺信息 major_hazard=重大危险源信息",
        ),
        sa.Column(
            "title",
            sa.String(100),
            nullable=False,
            server_default="",
            comment="卡片标题",
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="卡片正文内容",
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="排序（同类型内升序）",
        ),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_safety_commitment_cards_type_sort",
        "safety_commitment_cards",
        ["card_type", "sort_order"],
        schema="safety",
    )

    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "commitment_notify_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="是否启用安全承诺每日填报推送（按 commitment_push_time 定时推卡）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "commitment_push_time",
            sa.String(5),
            nullable=True,
            server_default="08:30",
            comment="每日填报卡片推送时间（HH:mm，上海时区）",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "commitment_chat_ids",
            jsonb,
            nullable=True,
            comment="承诺公告推送群 chat_id 列表",
        ),
        schema="safety",
    )
    op.add_column(
        "feishu_app_settings",
        sa.Column(
            "commitment_user_ids",
            jsonb,
            nullable=True,
            comment="安全承诺填报人员 open_id 列表",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_column("feishu_app_settings", "commitment_user_ids", schema="safety")
    op.drop_column("feishu_app_settings", "commitment_chat_ids", schema="safety")
    op.drop_column("feishu_app_settings", "commitment_push_time", schema="safety")
    op.drop_column("feishu_app_settings", "commitment_notify_enabled", schema="safety")
    op.drop_index(
        "ix_safety_commitment_cards_type_sort",
        table_name="safety_commitment_cards",
        schema="safety",
    )
    op.drop_table("safety_commitment_cards", schema="safety")
    op.drop_index(
        "uq_safety_commitment_reports_date",
        table_name="safety_commitment_reports",
        schema="safety",
    )
    op.drop_table("safety_commitment_reports", schema="safety")
