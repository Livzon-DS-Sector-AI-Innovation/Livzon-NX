"""core.module_settings table

新线迁移链遗漏了 core.module_settings 表，而 app/shared/config_reader.py
（get_module_setting / set_module_setting，hr/warehouse 模块广泛使用）仍以
原始 SQL 读写该表。补齐与代码精确匹配的结构：
- 建表（module varchar(64) / key varchar(128) / value text / created_by、
  updated_by varchar(64)，与旧线 dazah_sync 结构一致）
- 部分唯一索引 (module, key) WHERE is_deleted = false，匹配
  set_module_setting 的 `ON CONFLICT (module, key) WHERE is_deleted = false`
- 普通索引加速 get_module_setting 的查询

Revision ID: e4f5a6b7c8d9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS core.module_settings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            module varchar(64) NOT NULL,
            key varchar(128) NOT NULL,
            value text NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_by varchar(64),
            updated_by varchar(64),
            is_deleted boolean NOT NULL DEFAULT false
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_core_module_settings_module_key
            ON core.module_settings (module, key) WHERE is_deleted = false
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_core_module_settings_module_key
            ON core.module_settings (module, key)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS core.module_settings")
