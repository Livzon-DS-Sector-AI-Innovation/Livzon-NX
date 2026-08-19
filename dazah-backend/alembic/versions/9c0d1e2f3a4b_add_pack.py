"""add_pack_table

Revision ID: 9c0d1e2f3a4b
Revises: 8b9c0d1e2f3a
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
revision = '9c0d1e2f3a4b'; down_revision = '8b9c0d1e2f3a'

def upgrade():
    op.create_table('pack',
    sa.Column('feishu_record_id', sa.String(64), nullable=True), sa.Column('seq_no', sa.Integer(), nullable=True),
    sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('feed_weight', sa.String(64), nullable=True),
    sa.Column('incoming_batch', sa.String(128), nullable=True), sa.Column('incoming_titer', sa.Float(), nullable=True),
    sa.Column('incoming_moisture', sa.Float(), nullable=True), sa.Column('impurity_report', sa.Text(), nullable=True),
    sa.Column('pack_spec', sa.String(64), nullable=True), sa.Column('barrel_count', sa.Float(), nullable=True),
    sa.Column('per_barrel_weight', sa.String(64), nullable=True), sa.Column('total_net_weight', sa.String(64), nullable=True),
    sa.Column('sample_weight', sa.String(64), nullable=True), sa.Column('retain_weight', sa.String(64), nullable=True),
    sa.Column('reject_weight', sa.String(64), nullable=True), sa.Column('screen_loss', sa.String(64), nullable=True),
    sa.Column('spill_loss', sa.String(64), nullable=True), sa.Column('total_yield', sa.Float(), nullable=True),
    sa.Column('pack_date', sa.String(64), nullable=True), sa.Column('operator', sa.String(64), nullable=True),
    sa.Column('outer_pack_no', sa.String(128), nullable=True), sa.Column('warehouse_qty', sa.String(64), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
    sa.PrimaryKeyConstraint('id'), schema='production')
    op.create_index('ix_pack_batch', 'pack', ['batch_no'], unique=False, schema='production')
    op.create_index('ix_pack_frid', 'pack', ['feishu_record_id'], unique=True, schema='production')

def downgrade():
    op.drop_table('pack', schema='production')
