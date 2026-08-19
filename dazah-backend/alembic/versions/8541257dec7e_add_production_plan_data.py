"""add_production_plan_data

Revision ID: 8541257dec7e
Revises: add269737689
Create Date: 2026-07-02 11:48:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '8541257dec7e'
down_revision: Union[str, None] = 'add269737689'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'production_plan_data' in inspector.get_table_names(schema='production'):
        return
    op.create_table('production_plan_data',
    sa.Column('batch_no', sa.String(64), nullable=True),
    sa.Column('product_name', sa.String(128), nullable=False),
    sa.Column('workshop', sa.String(64), nullable=True),
    sa.Column('plan_date', sa.Date(), nullable=True),
    sa.Column('unit', sa.String(32), nullable=True),
    sa.Column('planned_yield', sa.Float(), nullable=True),
    sa.Column('actual_completion', sa.Float(), nullable=True),
    sa.Column('completion_rate', sa.Float(), nullable=True),
    sa.Column('safety_status', sa.String(128), nullable=True),
    sa.Column('quality_status', sa.String(128), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('source', sa.String(32), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['identity.users.id']),
    sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id']),
    sa.PrimaryKeyConstraint('id'),
    schema='production')
    op.create_index('ix_plan_data_product', 'production_plan_data', ['product_name'], unique=False, schema='production')
    op.create_index('ix_plan_data_date', 'production_plan_data', ['plan_date'], unique=False, schema='production')

def downgrade() -> None:
    op.drop_index('ix_plan_data_date', table_name='production_plan_data', schema='production')
    op.drop_index('ix_plan_data_product', table_name='production_plan_data', schema='production')
    op.drop_table('production_plan_data', schema='production')
