"""hr training personnel config owner-scoped unique index

培训人员配置按登录人隔离：普通用户只见/改自己的配置，超管全局。
唯一索引重建为 (level, department, config_name, created_by) 的部分唯一索引
（WHERE is_deleted = false），不同用户可各自建同名配置。

Revision ID: b4c2e8a1f3d6
Revises: a9b3d5f7c1e4
Create Date: 2026-08-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c2e8a1f3d6"
down_revision: str | None = "a9b3d5f7c1e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS hr.ix_training_personnel_configs_level_dept_name
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        ix_training_personnel_configs_level_dept_name_owner
        ON hr.training_personnel_configs (level, department, config_name, created_by)
        WHERE is_deleted = false
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS hr.ix_training_personnel_configs_level_dept_name_owner
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        ix_training_personnel_configs_level_dept_name
        ON hr.training_personnel_configs (level, department, config_name)
        """
    )
