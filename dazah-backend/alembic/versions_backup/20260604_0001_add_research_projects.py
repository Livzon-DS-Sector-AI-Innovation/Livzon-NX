"""add research projects table

Revision ID: 20260604_0001
Revises: 1e3a6f5002da
Create Date: 2026-06-04 01:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260604_0001'
down_revision: Union[str, None] = '1e3a6f5002da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('research_projects',
    sa.Column('project_no', sa.String(length=50), nullable=False, comment='项目编号'),
    sa.Column('name', sa.String(length=200), nullable=False, comment='项目名称'),
    sa.Column('project_type', sa.String(length=100), nullable=True, comment='项目类型'),
    sa.Column('stage', sa.String(length=20), nullable=False, comment='项目阶段：立项/研发中试/验证/注册/商业化'),
    sa.Column('status', sa.String(length=20), nullable=False, comment='项目状态：进行中/已暂停/已完成/已终止'),
    sa.Column('leader', sa.String(length=100), nullable=True, comment='项目负责人'),
    sa.Column('start_date', sa.Date(), nullable=True, comment='开始日期'),
    sa.Column('end_date', sa.Date(), nullable=True, comment='结束日期'),
    sa.Column('description', sa.Text(), nullable=True, comment='项目描述'),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.CheckConstraint("stage IN ('立项', '研发中试', '验证', '注册', '商业化')", name='ck_research_projects_stage'),
    sa.CheckConstraint("status IN ('进行中', '已暂停', '已完成', '已终止')", name='ck_research_projects_status'),
    sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='research'
    )


def downgrade() -> None:
    op.drop_table('research_projects', schema='research')
