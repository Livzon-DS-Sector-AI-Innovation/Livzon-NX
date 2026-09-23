"""create production.line_halt_events for halt/resume timeline"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9d400000056"
down_revision: str | None = "c9d400000054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 停产/复产事件时间线：每次切换追加一条，供停产历史查看；
    # 当前状态仍在 production_line_status，事件表只增不改
    op.create_table(
        "line_halt_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "product_code",
            sa.String(length=16),
            nullable=False,
            comment="产品代码（FA/MC/LN/DR/LV/MV/TY/FL）",
        ),
        sa.Column(
            "halted",
            sa.Boolean(),
            nullable=False,
            comment="true=停产 false=复产",
        ),
        sa.Column(
            "reason",
            sa.String(length=100),
            nullable=True,
            comment="原因备注（选填：转产/检修/季节性停产/误操作等）",
        ),
        sa.Column(
            "operator_name",
            sa.String(length=64),
            nullable=True,
            comment="操作人姓名",
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
        schema="production",
    )
    op.create_index(
        "ix_line_halt_events_product_created",
        "line_halt_events",
        ["product_code", "created_at"],
        unique=False,
        schema="production",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_line_halt_events_product_created",
        table_name="line_halt_events",
        schema="production",
    )
    op.drop_table("line_halt_events", schema="production")
