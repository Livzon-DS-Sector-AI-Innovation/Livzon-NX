"""drop legacy full-unique index on core.module_settings

开发库上的历史表残留全量唯一索引 uq_module_settings_module_key，
与部分唯一索引 uq_core_module_settings_module_key（WHERE is_deleted=false）
并存。全量唯一会导致"软删后重新启用同 module/key"撞约束失败，
而 config_reader.set_module_setting 只依赖部分唯一索引。删掉遗留全量索引。

Revision ID: e6f7a8b9c0d1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS core.uq_module_settings_module_key")


def downgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_module_settings_module_key"
        " ON core.module_settings (module, key)"
    )
