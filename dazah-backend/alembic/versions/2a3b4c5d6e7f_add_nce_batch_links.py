"""add_nce_batch_links_table

Revision ID: 2a3b4c5d6e7f
Revises: 1f2e3d4c5b6a
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '2a3b4c5d6e7f'
down_revision = '1f2e3d4c5b6a'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('nce_batch_links',
    sa.Column('id', UUID(), nullable=False),
    sa.Column('nce_id', UUID(), nullable=False, comment='非密事件ID'),
    sa.Column('batch_id', UUID(), nullable=False, comment='发酵批次ID'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', UUID(), nullable=True),
    sa.Column('updated_by', UUID(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['nce_id'], ['production.non_conforming_events.id']),
    sa.ForeignKeyConstraint(['batch_id'], ['production.fermentation_records.id']),
    sa.PrimaryKeyConstraint('id'),
    schema='production')
    op.create_index('ix_nce_links_nce_id', 'nce_batch_links', ['nce_id'], unique=False, schema='production')
    op.create_index('ix_nce_links_batch_id', 'nce_batch_links', ['batch_id'], unique=False, schema='production')

def downgrade():
    op.drop_table('nce_batch_links', schema='production')
