"""redesign_production_plans

Revision ID: 1208b8fea528
Revises: a1b2c3d4e5f7
Create Date: 2026-07-14 11:12:26.514591
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1208b8fea528'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 删除旧的 plan_tasks 表
    op.drop_table('plan_tasks', schema='production')

    # 2. 删除 production_plans 旧字段
    op.drop_column('production_plans', 'plan_name', schema='production')
    op.drop_column('production_plans', 'plan_type', schema='production')
    op.drop_column('production_plans', 'plan_no', schema='production')
    op.drop_column('production_plans', 'completed_batches', schema='production')
    op.drop_column('production_plans', 'status', schema='production')
    op.drop_column('production_plans', 'total_batches', schema='production')
    op.drop_column('production_plans', 'notes', schema='production')
    op.drop_column('production_plans', 'plan_month', schema='production')

    # 3. 添加新字段
    op.add_column('production_plans', sa.Column('workshop', sa.String(length=64), nullable=True, comment='车间'), schema='production')
    op.add_column('production_plans', sa.Column('product_name', sa.String(length=128), nullable=False, comment='产品'), schema='production')
    op.add_column('production_plans', sa.Column('plan_date', sa.Date(), nullable=True, comment='日期'), schema='production')
    op.add_column('production_plans', sa.Column('planned_yield', sa.Float(), nullable=True, comment='计划产量'), schema='production')
    op.add_column('production_plans', sa.Column('actual_completion', sa.Float(), nullable=True, comment='实际完成'), schema='production')
    op.add_column('production_plans', sa.Column('completion_rate', sa.Float(), nullable=True, comment='完成率'), schema='production')
    op.add_column('production_plans', sa.Column('safety_status', sa.String(length=128), nullable=True, comment='安环情况'), schema='production')
    op.add_column('production_plans', sa.Column('quality_status', sa.String(length=128), nullable=True, comment='质量情况'), schema='production')
    op.add_column('production_plans', sa.Column('remarks', sa.Text(), nullable=True, comment='备注'), schema='production')
    op.add_column('production_plans', sa.Column('source', sa.String(length=32), server_default='manual', nullable=True, comment='数据来源'), schema='production')

    # 4. 创建索引
    op.create_index('ix_production_plans_product', 'production_plans', ['product_name'], unique=False, schema='production')
    op.create_index('ix_production_plans_date', 'production_plans', ['plan_date'], unique=False, schema='production')


def downgrade() -> None:
    # 回滚: 删新字段
    op.drop_index('ix_production_plans_date', table_name='production_plans', schema='production')
    op.drop_index('ix_production_plans_product', table_name='production_plans', schema='production')
    op.drop_column('production_plans', 'source', schema='production')
    op.drop_column('production_plans', 'remarks', schema='production')
    op.drop_column('production_plans', 'quality_status', schema='production')
    op.drop_column('production_plans', 'safety_status', schema='production')
    op.drop_column('production_plans', 'completion_rate', schema='production')
    op.drop_column('production_plans', 'actual_completion', schema='production')
    op.drop_column('production_plans', 'planned_yield', schema='production')
    op.drop_column('production_plans', 'plan_date', schema='production')
    op.drop_column('production_plans', 'product_name', schema='production')
    op.drop_column('production_plans', 'workshop', schema='production')

    # 回滚: 恢复旧字段
    op.add_column('production_plans', sa.Column('plan_name', sa.String(length=255), nullable=True), schema='production')
    op.add_column('production_plans', sa.Column('plan_type', sa.String(length=50), nullable=True), schema='production')
    op.add_column('production_plans', sa.Column('plan_no', sa.String(length=64), nullable=False), schema='production')
    op.add_column('production_plans', sa.Column('completed_batches', sa.Integer(), nullable=True), schema='production')
    op.add_column('production_plans', sa.Column('status', sa.String(length=32), server_default='draft', nullable=False), schema='production')
    op.add_column('production_plans', sa.Column('total_batches', sa.Integer(), nullable=True), schema='production')
    op.add_column('production_plans', sa.Column('notes', sa.Text(), nullable=True), schema='production')
    op.add_column('production_plans', sa.Column('plan_month', sa.String(length=7), nullable=True), schema='production')

    # 回滚: 重建 plan_tasks
    op.create_table('plan_tasks',
        sa.Column('plan_id', sa.UUID(), nullable=False),
        sa.Column('product_code', sa.String(length=64), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=True),
        sa.Column('batch_qty', sa.Integer(), nullable=True),
        sa.Column('assigned_to', sa.UUID(), nullable=True),
        sa.Column('assigned_to_name', sa.String(length=100), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['assigned_to'], ['identity.users.id']),
        sa.ForeignKeyConstraint(['plan_id'], ['production.production_plans.id']),
        schema='production'
    )
