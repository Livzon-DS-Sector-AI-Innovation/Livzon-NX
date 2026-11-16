"""作业安全监护人名单表

依据监护人考试合格名单管理需求，在 safety schema 新增 ``guardian_roster``：
按车间区分的监护人台账（姓名/车间/联系电话/岗位/分数/考试名称/考试日期/
备注/来源文件），以最新一次 Excel 导入为准（整表替换），支持手工增删改。

Revision ID: e7c2a9f4b6d8
Revises: 4bd62e5d78a1
Create Date: 2026-11-13 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7c2a9f4b6d8"
down_revision: str | None = "4bd62e5d78a1"
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
        "guardian_roster",
        *_base_columns(),
        *_base_constraints(),
        sa.Column("person_name", sa.String(100), nullable=False, comment="监护人姓名"),
        sa.Column(
            "workshop",
            sa.String(100),
            nullable=False,
            comment="车间/部门（自由文本）",
        ),
        sa.Column("phone", sa.String(32), nullable=True, comment="联系电话"),
        sa.Column("position", sa.String(100), nullable=True, comment="岗位"),
        sa.Column("score", sa.Integer(), nullable=True, comment="考试分数"),
        sa.Column(
            "exam_name",
            sa.String(100),
            nullable=True,
            comment="考试名称（如监护人考试）",
        ),
        sa.Column("exam_date", sa.Date(), nullable=True, comment="考试/合格日期"),
        sa.Column("remark", sa.String(200), nullable=True, comment="备注"),
        sa.Column(
            "source_file",
            sa.String(255),
            nullable=True,
            comment="来源导入文件名",
        ),
        sa.Index(
            "ix_guardian_roster_workshop",
            "workshop",
            unique=False,
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("guardian_roster", schema="safety")
