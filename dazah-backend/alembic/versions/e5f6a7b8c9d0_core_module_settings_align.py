"""core.module_settings 结构对齐（幂等）

处理开发库（dazah@5433）上历史遗留的旧结构 module_settings 表：
- 补 created_at / created_by / updated_by 三列（若缺失）
- 若存在历史全量唯一索引 uq_core_module_settings_module_key，删除并重建为
  与 set_module_setting `ON CONFLICT (module, key) WHERE is_deleted = false`
  精确匹配的部分唯一索引
- ix_core_module_settings_module_key 普通索引幂等确保存在

对已是最新结构的库（dazah_test）全部为 IF NOT EXISTS / 判空，无操作。

Revision ID: e5f6a7b8c9d0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) 幂等补列（历史旧结构缺 created_at/created_by/updated_by）
    op.execute(
        "ALTER TABLE core.module_settings ADD COLUMN IF NOT EXISTS"
        " created_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        "ALTER TABLE core.module_settings ADD COLUMN IF NOT EXISTS"
        " created_by varchar(64)"
    )
    op.execute(
        "ALTER TABLE core.module_settings ADD COLUMN IF NOT EXISTS"
        " updated_by varchar(64)"
    )
    # 2) 历史全量唯一索引 → 部分唯一索引（与 ON CONFLICT 谓词匹配）
    #    先删旧（若存在），再建新；普通索引幂等保留
    op.execute(
        "DROP INDEX IF EXISTS core.uq_core_module_settings_module_key"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_core_module_settings_module_key"
        " ON core.module_settings (module, key) WHERE is_deleted = false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_core_module_settings_module_key"
        " ON core.module_settings (module, key)"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS core.uq_core_module_settings_module_key"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_core_module_settings_module_key"
        " ON core.module_settings (module, key)"
    )
