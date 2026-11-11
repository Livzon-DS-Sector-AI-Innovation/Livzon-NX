"""应急预案 AI 工作台：结构化正文、修订快照与对话记录

- ``safety.emergency_plan_contents``：应急预案结构化正文（与预案一对一），
  记录正文状态、当前修订号、生成参数与最近一次 AI 审核报告。
- ``safety.emergency_plan_revisions``：每次 AI 生成/修正/对话修改/人工编辑/
  导入/恢复的完整正文快照与修正日志，(plan_id, revision_no) 唯一。
- ``safety.emergency_plan_ai_messages``：工作台对话记录。

Revision ID: e5a9c3d7f2b8
Revises: d7b2f9a4c1e6
Create Date: 2026-11-09 11:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5a9c3d7f2b8"
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
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
    ]


def _base_constraints() -> tuple[sa.Constraint, ...]:
    return (
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def _plan_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["plan_id"], ["safety.emergency_plans.id"], ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "emergency_plan_contents",
        *_base_columns(),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属应急预案",
        ),
        sa.Column("content", jsonb, nullable=True, comment="结构化正文"),
        sa.Column(
            "content_status",
            sa.String(20),
            nullable=False,
            server_default="empty",
            comment="正文状态: empty/draft/reviewed/finalized",
        ),
        sa.Column(
            "revision_no",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="当前修订号",
        ),
        sa.Column(
            "ai_generated",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="正文是否经 AI 生成",
        ),
        sa.Column(
            "generation_params", jsonb, nullable=True, comment="最近一次生成参数"
        ),
        sa.Column("last_review", jsonb, nullable=True, comment="最近一次 AI 审核报告"),
        sa.Column(
            "last_reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次审核时间",
        ),
        sa.Column(
            "content_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="正文最近修改时间",
        ),
        _plan_fk(),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "uq_safety_emergency_plan_contents_plan",
        "emergency_plan_contents",
        ["plan_id"],
        unique=True,
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "emergency_plan_revisions",
        *_base_columns(),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属应急预案",
        ),
        sa.Column(
            "revision_no", sa.Integer(), nullable=False, comment="修订号（预案内递增）"
        ),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            comment="来源: ai_generate/ai_fix/ai_chat/user_edit/import/restore",
        ),
        sa.Column(
            "summary",
            sa.String(500),
            nullable=False,
            server_default="",
            comment="修订摘要",
        ),
        sa.Column("content", jsonb, nullable=False, comment="该修订的完整正文快照"),
        sa.Column(
            "changed_sections",
            jsonb,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="相对上一修订变化的章节标识",
        ),
        sa.Column(
            "changes",
            jsonb,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="修正日志 [{section, reason, before, after}]",
        ),
        _plan_fk(),
        *_base_constraints(),
        sa.UniqueConstraint(
            "plan_id", "revision_no", name="uq_safety_emergency_plan_revisions_no"
        ),
        schema="safety",
    )

    op.create_table(
        "emergency_plan_ai_messages",
        *_base_columns(),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="所属应急预案",
        ),
        sa.Column(
            "role", sa.String(20), nullable=False, comment="角色: user/assistant"
        ),
        sa.Column("content", sa.Text(), nullable=False, comment="消息内容"),
        sa.Column(
            "revision_no",
            sa.Integer(),
            nullable=True,
            comment="该轮对话产生的修订号",
        ),
        _plan_fk(),
        *_base_constraints(),
        schema="safety",
    )
    op.create_index(
        "ix_safety_emergency_plan_ai_messages_plan",
        "emergency_plan_ai_messages",
        ["plan_id", "created_at"],
        schema="safety",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_safety_emergency_plan_ai_messages_plan",
        table_name="emergency_plan_ai_messages",
        schema="safety",
    )
    op.drop_table("emergency_plan_ai_messages", schema="safety")
    op.drop_table("emergency_plan_revisions", schema="safety")
    op.drop_index(
        "uq_safety_emergency_plan_contents_plan",
        table_name="emergency_plan_contents",
        schema="safety",
    )
    op.drop_table("emergency_plan_contents", schema="safety")
