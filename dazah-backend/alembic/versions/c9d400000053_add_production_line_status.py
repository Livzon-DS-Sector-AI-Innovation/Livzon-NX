"""add production line status for product halt tracking"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9d400000053"
down_revision: str | None = "c9d400000052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 产品生产线停产状态：人工维护的即时状态，全平台可见（看板收起、汇总隐藏）
    op.create_table(
        "production_line_status",
        sa.Column(
            "product_code",
            sa.String(length=16),
            nullable=False,
            comment="产品代码（FA/MC/DR/LV/MV/TY/FL）",
        ),
        sa.Column(
            "halted",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="是否停产中",
        ),
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
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_code", name="uq_production_line_status_product"
        ),
        schema="production",
    )


def downgrade() -> None:
    op.drop_table("production_line_status", schema="production")
