"""trend AI dedup key: plain unique constraint -> partial unique index

趋势 AI 去重键改为「仅未删除行唯一」的部分唯一索引（对齐 AGENTS 软删除
唯一约束规范）：「重新分析」会软删旧行再建新行，普通 UniqueConstraint 会让
重插必撞唯一键（重分析必失败、仪表盘连带报错）。

Revision ID: c9d400000030
Revises: c9d400000029
Create Date: 2026-09-11 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000030"
down_revision: str | None = "c9d400000029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "quality_finished_trend_ai_analyses"
_CONSTRAINT = "uq_quality_finished_trend_ai_analysis_key"


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
    if not {"entity_code", "metric_key", "rule_type", "trend_end_batch"}.issubset(
        table_columns
    ):
        return  # 表尚未创建（极端旧库），跳过

    if _constraint_exists(bind):
        op.drop_constraint(
            _CONSTRAINT, _TABLE, schema="quality", type_="unique"
        )
    if not _index_exists(bind):
        op.execute(
            f'CREATE UNIQUE INDEX "{_CONSTRAINT}" '
            f'ON quality."{_TABLE}" '
            f"(entity_code, metric_key, rule_type, trend_end_batch) "
            f"WHERE is_deleted = false"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _index_exists(bind):
        op.drop_index(_CONSTRAINT, table_name=_TABLE, schema="quality")
    if not _constraint_exists(bind):
        op.create_unique_constraint(
            _CONSTRAINT,
            _TABLE,
            ["entity_code", "metric_key", "rule_type", "trend_end_batch"],
            schema="quality",
        )
