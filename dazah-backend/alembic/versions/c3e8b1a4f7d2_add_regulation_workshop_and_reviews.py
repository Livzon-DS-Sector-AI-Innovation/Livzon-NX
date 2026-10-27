"""regulation workshop column and compliance reviews table

安全操作规程增强：
- ``safety.operation_regulations`` 新增 ``workshop`` 列：车间/部门归属，
  支持按车间组织与筛选操规台账（对齐各车间安全资料的整理方式）；
- 新表 ``safety.regulation_reviews``：操规 AI 合规审核记录
  （结论、评分、缺失项、不合规项、改进建议）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3e8b1a4f7d2"
down_revision: str | None = "b5d8f2a6c1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operation_regulations",
        sa.Column(
            "workshop",
            sa.String(length=60),
            nullable=True,
            server_default="",
            comment="车间/部门（如 103车间、201二车间、动力部）",
        ),
        schema="safety",
    )
    op.create_index(
        "ix_safety_operation_regulations_workshop",
        "operation_regulations",
        ["workshop"],
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.create_table(
        "regulation_reviews",
        sa.Column(
            "regulation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("safety.operation_regulations.id"),
            nullable=False,
            comment="关联操规ID",
        ),
        sa.Column(
            "regulation_name",
            sa.String(length=255),
            nullable=False,
            comment="操规名称（冗余，便于追溯）",
        ),
        sa.Column(
            "result",
            sa.String(length=20),
            nullable=False,
            server_default="fail",
            comment="审核结论: pass/conditional_pass/fail",
        ),
        sa.Column(
            "score",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="合规评分（0-100）",
        ),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
            server_default="",
            comment="总体评价",
        ),
        sa.Column(
            "missing_items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment="缺失项 [{item, requirement, basis, severity, suggestion}]",
        ),
        sa.Column(
            "non_compliant_items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment="不合规项 [{item, requirement, basis, severity, suggestion}]",
        ),
        sa.Column(
            "suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
            comment="改进建议列表",
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=True,
            comment="发起审核的用户",
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Index(
            "ix_safety_regulation_reviews_regulation",
            "regulation_id",
            "is_deleted",
        ),
        schema="safety",
    )


def downgrade() -> None:
    op.drop_table("regulation_reviews", schema="safety")
    op.drop_index(
        "ix_safety_operation_regulations_workshop",
        table_name="operation_regulations",
        schema="safety",
    )
    op.drop_column("operation_regulations", "workshop", schema="safety")
