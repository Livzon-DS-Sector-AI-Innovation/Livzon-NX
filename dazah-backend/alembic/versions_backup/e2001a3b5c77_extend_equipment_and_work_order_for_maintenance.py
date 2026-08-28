"""extend equipment and work_order for maintenance

Revision ID: e2001a3b5c77
Revises: 1e3a6f5002da
Create Date: 2026-06-04 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2001a3b5c77"
down_revision: str | None = "1e3a6f5002da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Update order_type check constraint to include 计划维护 and 巡检
    op.drop_constraint("ck_work_orders_order_type", "work_orders", schema="equipment")
    op.create_check_constraint(
        "ck_work_orders_order_type",
        "work_orders",
        "order_type IN ('故障维修', '计划维护', '巡检', '校准')",
        schema="equipment",
    )

    # Update status check constraint to include 待执行 and 执行中
    op.drop_constraint("ck_work_orders_status", "work_orders", schema="equipment")
    op.create_check_constraint(
        "ck_work_orders_status",
        "work_orders",
        (
            "status IN ('待处理', '已指派', '维修中', '待验收', '已完成', "
            "'已关闭', '待执行', '执行中')"
        ),
        schema="equipment",
    )


def downgrade() -> None:
    # Revert status check constraint
    op.drop_constraint("ck_work_orders_status", "work_orders", schema="equipment")
    op.create_check_constraint(
        "ck_work_orders_status",
        "work_orders",
        "status IN ('待处理', '已指派', '维修中', '待验收', '已完成', '已关闭')",
        schema="equipment",
    )

    # Revert order_type check constraint
    op.drop_constraint("ck_work_orders_order_type", "work_orders", schema="equipment")
    op.create_check_constraint(
        "ck_work_orders_order_type",
        "work_orders",
        "order_type IN ('故障维修', '校准')",
        schema="equipment",
    )
