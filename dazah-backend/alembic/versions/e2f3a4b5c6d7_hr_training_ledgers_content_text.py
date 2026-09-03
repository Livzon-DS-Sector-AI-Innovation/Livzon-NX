"""hr training_ledgers.training_content VARCHAR -> TEXT

解除培训台账"培训内容"字段 4096 字符上限（仅该字段，其余字段不动）。
Revises 指向 main 当前迁移头 9e2f4a6c8b10（merge_page_permission_main_heads），
避免在旧头 d1e2f3a4b5c6 上分叉产生多 head。

Revision ID: e2f3a4b5c6d7
Revises: 9e2f4a6c8b10
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "9e2f4a6c8b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "training_ledgers",
        "training_content",
        existing_type=sa.String(4096),
        type_=sa.Text(),
        existing_nullable=True,
        schema="hr",
    )


def downgrade() -> None:
    op.alter_column(
        "training_ledgers",
        "training_content",
        existing_type=sa.Text(),
        type_=sa.String(4096),
        existing_nullable=True,
        schema="hr",
    )
