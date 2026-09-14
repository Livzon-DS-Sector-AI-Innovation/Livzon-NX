"""趋势 AI 月度定时分析运行状态表。

每月定时（默认 25 日，通知设置可改）全量分析并推送；本表按 period 记录
当月是否已跑，防止同月重复触发（周期 Generator 每日检查一次）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000031"
down_revision: str | None = "c9d400000030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "quality_trend_monthly_runs"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    if inspector.has_table(_TABLE, schema="quality"):
        return
    op.create_table(
        _TABLE,
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="running",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="quality",
    )
    op.create_unique_constraint(
        "uq_quality_trend_monthly_run_period",
        _TABLE,
        ["period"],
        schema="quality",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_quality_trend_monthly_run_period",
        _TABLE,
        schema="quality",
        type_="unique",
    )
    op.drop_table(_TABLE, schema="quality")
