"""add_fermentation_records_table

Revision ID: 2f0b698eb4d8
Revises: a1b2c3d4e5f6
Create Date: 2026-07-01 10:37:16.298235
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f0b698eb4d8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table('fermentation_records', schema='production'):
        op.drop_table('fermentation_records', schema='production')
    op.create_table('fermentation_records',
    sa.Column('batch_no', sa.String(length=64), nullable=False, comment='批号'),
    sa.Column('product_name', sa.String(length=100), nullable=False, comment='产品名称'),
    sa.Column('fermenter', sa.String(length=64), nullable=False, comment='发酵罐'),
    sa.Column('entry_date', sa.Date(), nullable=False, comment='进罐日期'),
    sa.Column('discharge_date', sa.Date(), nullable=True, comment='放罐日期'),
    sa.Column('cycle_1', sa.Float(), nullable=True, comment='周期1'),
    sa.Column('cycle_2', sa.Float(), nullable=True, comment='周期2'),
    sa.Column('cycle_3', sa.Float(), nullable=True, comment='周期3'),
    sa.Column('cycle_4', sa.Float(), nullable=True, comment='周期4'),
    sa.Column('cycle_5', sa.Float(), nullable=True, comment='周期5'),
    sa.Column('cycle_6', sa.Float(), nullable=True, comment='周期6'),
    sa.Column('tank_yield', sa.Float(), nullable=True, comment='罐产'),
    sa.Column('status', sa.String(length=32), nullable=False, comment='状态'),
    sa.Column('remarks', sa.Text(), nullable=True, comment='备注'),
    sa.Column('attachment', sa.String(length=500), nullable=True, comment='附件'),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['identity.users.id'], ),
    sa.ForeignKeyConstraint(['updated_by'], ['identity.users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='production'
    )
    op.create_index('ix_fermentation_records_batch_no', 'fermentation_records', ['batch_no'], unique=False, schema='production')
    op.create_index('ix_fermentation_records_product_name', 'fermentation_records', ['product_name'], unique=False, schema='production')


def downgrade() -> None:
    op.drop_index('ix_fermentation_records_product_name', table_name='fermentation_records', schema='production')
    op.drop_index('ix_fermentation_records_batch_no', table_name='fermentation_records', schema='production')
    op.drop_table('fermentation_records', schema='production')
