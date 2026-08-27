"""add pending_execution and executing to work_order status check

Revision ID: 5f70eb51dfc9
Revises: f068904911a9
Create Date: 2026-06-05 16:10:03.279684
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f70eb51dfc9"
down_revision: str | None = "f068904911a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE equipment.work_orders DROP CONSTRAINT IF EXISTS "
        "ck_work_orders_status"
    )
    op.create_check_constraint(
        "ck_work_orders_status",
        "work_orders",
        (
            "status IN ('待处理', '待执行', '已指派', '维修中', '执行中', "
            "'待验收', '已完成', '已关闭')"
        ),
        schema="equipment",
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE equipment.work_orders DROP CONSTRAINT IF EXISTS "
        "ck_work_orders_status"
    )
    op.create_check_constraint(
        "ck_work_orders_status",
        "work_orders",
        "status IN ('待处理', '已指派', '维修中', '待验收', '已完成', '已关闭')",
        schema="equipment",
    )
