"""add equipment_ids to inspection_tasks

Revision ID: 6a44a65836b7
Revises: cf818aa211ef
Create Date: 2026-06-06 14:49:59.736288
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6a44a65836b7'
down_revision: Union[str, None] = 'cf818aa211ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('inspection_tasks',
        sa.Column('equipment_ids', sa.JSON(), nullable=True, comment='设备ID列表（多设备模式）'),
        schema='equipment',
    )


def downgrade() -> None:
    op.drop_column('inspection_tasks', 'equipment_ids', schema='equipment')
