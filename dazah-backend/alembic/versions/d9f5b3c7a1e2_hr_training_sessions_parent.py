"""hr training_sessions add parent_session_id

二级培训闭环：部门级会话从台账一键创建时记录上级会话，
并复制上级试卷草稿为快照。

Revision ID: d9f5b3c7a1e2
Revises: c7e3a9b2d5f8
Create Date: 2026-08-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9f5b3c7a1e2"
down_revision: str | None = "c7e3a9b2d5f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 修复基线漂移：training_ledgers.employee_number 建成 NOT NULL，与 ORM（可空）
    # 不一致；台账记录经"从台账创建二级培训"等路径允许无工号
    op.execute(
        """
        ALTER TABLE hr.training_ledgers
        ALTER COLUMN employee_number DROP NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE hr.training_sessions
        ADD COLUMN IF NOT EXISTS parent_session_id uuid
        """
    )
    op.execute(
        """
        ALTER TABLE hr.training_sessions
        ADD CONSTRAINT fk_training_sessions_parent_session_id
        FOREIGN KEY (parent_session_id) REFERENCES hr.training_sessions (id)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE hr.training_sessions
        DROP CONSTRAINT IF EXISTS fk_training_sessions_parent_session_id
        """
    )
    op.execute(
        """
        ALTER TABLE hr.training_ledgers
        ALTER COLUMN employee_number SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE hr.training_sessions
        DROP COLUMN IF EXISTS parent_session_id
        """
    )
