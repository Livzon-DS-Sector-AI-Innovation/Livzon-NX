"""seed deviation workbench settings row

偏差工作台提示词设置表在迁移时预置固定主键行，使 GET /settings 端点只读
（不再在读取时 get-or-create 写库，消除 GET 副作用）。

Revision ID: c2d3e4f5a6b7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-01
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 与 app.modules.quality.models.deviation_workbench.WORKBENCH_SETTINGS_ID 保持一致
WORKBENCH_SETTINGS_ID = "10000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO quality.deviation_workbench_settings
            (id, report_system_prompt, created_at, updated_at, is_deleted)
        VALUES ('{WORKBENCH_SETTINGS_ID}', '', now(), now(), false)
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"DELETE FROM quality.deviation_workbench_settings "
        f"WHERE id = '{WORKBENCH_SETTINGS_ID}'"
    )
