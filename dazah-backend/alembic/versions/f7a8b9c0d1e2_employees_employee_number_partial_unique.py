"""employees employee_number partial unique for soft-delete

工号唯一约束改为"仅未删除行唯一"的部分唯一索引：
离职员工（软删）不再占用工号，同工号再入职不再触发 IntegrityError 500。
对齐 AGENTS「软删除需要 WHERE is_deleted = false 的部分唯一索引」。

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # baseline 建的无名 UniqueConstraint（PG 默认名 employees_employee_number_key）
    op.drop_constraint(
        "employees_employee_number_key",
        "employees",
        schema="hr",
        type_="unique",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_employee_number_active
            ON hr.employees (employee_number) WHERE is_deleted = false
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS hr.uq_employees_employee_number_active"
    )
    op.create_unique_constraint(
        "employees_employee_number_key",
        "employees",
        ["employee_number"],
        schema="hr",
    )
