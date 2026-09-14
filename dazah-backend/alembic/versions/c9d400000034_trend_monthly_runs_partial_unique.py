"""trend monthly run dedup key: plain unique constraint -> partial unique index

月度运行标记（一个周期一行）改为「仅未删除行唯一」的部分唯一索引（对齐软删除
唯一约束规范）：原普通 UniqueConstraint 让软删标记行永久占位，"重跑本月"
（软删旧标记再插入）必撞唯一键。与 c9d400000030 对趋势 AI 表的处理一致。

Revision ID: c9d400000034
Revises: c9d400000033
Create Date: 2026-09-14 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000034"
down_revision: str | None = "c9d400000033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "quality_trend_monthly_runs"
_CONSTRAINT = "uq_quality_trend_monthly_run_period"


def _constraint_exists(bind) -> bool:
    inspector = sa.inspect(bind)
    existing_constraints = {
        uc["name"]
        for uc in inspector.get_unique_constraints(_TABLE, schema="quality")
    }
    return _CONSTRAINT in existing_constraints


def _index_exists(bind) -> bool:
    inspector = sa.inspect(bind)
    existing_indexes = {
        idx["name"] for idx in inspector.get_indexes(_TABLE, schema="quality")
    }
    return _CONSTRAINT in existing_indexes


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_columns = {
        col["name"] for col in inspector.get_columns(_TABLE, schema="quality")
    }
    if "period" not in table_columns:
        return  # 表尚未创建（极端旧库），跳过

    if _constraint_exists(bind):
        op.drop_constraint(_CONSTRAINT, _TABLE, schema="quality", type_="unique")
    if not _index_exists(bind):
        op.execute(
            f'CREATE UNIQUE INDEX "{_CONSTRAINT}" '
            f'ON quality."{_TABLE}" '
            f"(period) WHERE is_deleted = false"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind):
        op.drop_index(_CONSTRAINT, table_name=_TABLE, schema="quality")
    if not _constraint_exists(bind):
        op.create_unique_constraint(
            _CONSTRAINT, _TABLE, ["period"], schema="quality"
        )
