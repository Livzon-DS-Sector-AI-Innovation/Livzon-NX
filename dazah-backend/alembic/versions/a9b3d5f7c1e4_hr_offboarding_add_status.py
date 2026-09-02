"""hr offboarding add status column

离职台账新增「在职状态」字段（status），与原交接状态联动回填：
- 交接状态=已完成 ⟹ 在职状态=离职，其余默认在职
- 保留 handover_status 列不删（历史数据兼容，模型不再映射）

Revision ID: a9b3d5f7c1e4
Revises: c1e7f4a9b2d6
Create Date: 2026-08-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b3d5f7c1e4"
down_revision: str | None = "c1e7f4a9b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE hr.offboarding_records
        ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT '在职'
        """
    )
    # 回填：历史「交接状态=已完成」的记录视为已离职
    op.execute(
        """
        UPDATE hr.offboarding_records
        SET status = '离职'
        WHERE handover_status = '已完成'
        """
    )
    # 修复基线漂移：employee_id 建成了 NOT NULL，与 ORM（可空）不一致；
    # 飞书离职同步存在无匹配员工的记录，必须允许为空
    op.execute(
        """
        ALTER TABLE hr.offboarding_records
        ALTER COLUMN employee_id DROP NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE hr.offboarding_records
        DROP COLUMN IF EXISTS status
        """
    )
    # 反向恢复 NOT NULL（要求表中无 NULL employee_id，否则需先清理数据）
    op.execute(
        """
        ALTER TABLE hr.offboarding_records
        ALTER COLUMN employee_id SET NOT NULL
        """
    )
