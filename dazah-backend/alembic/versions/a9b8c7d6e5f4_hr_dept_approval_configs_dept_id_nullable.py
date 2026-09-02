"""hr_dept_approval_configs department_id nullable

部门级审批人配置解除对部门表的强绑定：
部门表为空（如开发环境未同步部门）时仍可按 department_name 展示与编辑配置。

Revision ID: a9b8c7d6e5f4
Revises: f7a8b9c0d1e2
Create Date: 2026-08-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "b7c3d9e4f6a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "hr_dept_approval_configs",
        "department_id",
        nullable=True,
        schema="hr",
    )


def downgrade() -> None:
    op.alter_column(
        "hr_dept_approval_configs",
        "department_id",
        nullable=False,
        schema="hr",
    )
