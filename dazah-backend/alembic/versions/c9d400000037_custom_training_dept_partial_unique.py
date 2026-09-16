"""Make custom training department name unique only for live rows.

自定义培训部门按名字软删除后，同名部门需要能重新添加：原实现是全量唯一索引
（含软删除行），重新添加会撞唯一键并抛 IntegrityError（接口 500）。

回滚注意：若库中已存在「同名 live + 软删除」并存记录，downgrade 重建全量唯一
索引会失败，需先清理历史同名行。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000037"
down_revision: str | None = "c9d400000036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_hr_custom_training_depts_name"
_TABLE_NAME = "hr_custom_training_departments"
_SCHEMA = "hr"


def upgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME, schema=_SCHEMA)
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["name"],
        unique=True,
        schema=_SCHEMA,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name=_TABLE_NAME, schema=_SCHEMA)
    op.create_index(
        _INDEX_NAME,
        _TABLE_NAME,
        ["name"],
        unique=True,
        schema=_SCHEMA,
    )
