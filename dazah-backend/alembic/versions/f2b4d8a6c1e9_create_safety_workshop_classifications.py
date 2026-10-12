"""create safety.workshop_classifications for AI fallback classification

车间/位置 的自由文本写法未命中别名与车间号规则时，由 LLM 按规范车间清单
自动归类；结果按原始写法缓存（唯一），避免每次统计重复调用 LLM。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f2b4d8a6c1e9"
down_revision: str | None = "e8a2c6d4b0f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workshop_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "raw_value",
            sa.String(length=200),
            nullable=False,
            comment="原始位置写法",
        ),
        sa.Column(
            "canonical",
            sa.String(length=120),
            nullable=False,
            comment="归类后的规范车间/部门名",
        ),
        sa.Column(
            "source",
            sa.String(length=20),
            server_default="ai",
            nullable=False,
            comment="来源: ai=LLM 自动归类",
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
        "uq_safety_workshop_classifications_raw_value",
        "workshop_classifications",
        ["raw_value"],
        unique=True,
        schema="safety",
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_safety_workshop_classifications_raw_value",
        table_name="workshop_classifications",
        schema="safety",
    )
    op.drop_table("workshop_classifications", schema="safety")
