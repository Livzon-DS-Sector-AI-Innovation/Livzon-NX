"""simplify work_order status to 5 values

Revision ID: a7b8c9d0e1f2
Revises: 6a44a65836b7
Create Date: 2026-06-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = '6a44a65836b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 迁移现有数据：待执行→待处理，已指派→待处理，维修中→执行中
    op.execute(
        "UPDATE equipment.work_orders SET status = '待处理' WHERE status IN ('待执行', '已指派')"
    )
    op.execute(
        "UPDATE equipment.work_orders SET status = '执行中' WHERE status = '维修中'"
    )

    # 2. 更新 CHECK 约束为 5 个状态
    op.execute(
        "ALTER TABLE equipment.work_orders DROP CONSTRAINT IF EXISTS ck_work_orders_status"
    )
    op.create_check_constraint(
        "ck_work_orders_status",
        "work_orders",
        "status IN ('待处理', '执行中', '待验收', '已完成', '已关闭')",
        schema="equipment",
    )


def downgrade() -> None:
    # 恢复旧 CHECK 约束
    op.execute(
        "ALTER TABLE equipment.work_orders DROP CONSTRAINT IF EXISTS ck_work_orders_status"
    )
    op.create_check_constraint(
        "ck_work_orders_status",
        "work_orders",
        "status IN ('待处理', '待执行', '已指派', '维修中', '执行中', '待验收', '已完成', '已关闭')",
        schema="equipment",
    )
    # 注意：数据迁移无法精确还原（待处理/执行中已合并后的数据无法区分原始值）
