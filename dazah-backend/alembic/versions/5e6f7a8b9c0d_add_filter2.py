"""add_filter2_table

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
revision = '5e6f7a8b9c0d'; down_revision = '4d5e6f7a8b9c'

def upgrade():
    op.create_table('filter2',
    sa.Column('feishu_record_id', sa.String(64), nullable=True), sa.Column('seq_no', sa.Integer(), nullable=True),
    sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('feed_volume', sa.String(64), nullable=True),
    sa.Column('filter_pressure', sa.Float(), nullable=True), sa.Column('filter_duration', sa.Float(), nullable=True),
    sa.Column('cloth_type', sa.String(64), nullable=True), sa.Column('cake_wet_weight', sa.String(64), nullable=True),
    sa.Column('cake_dry_weight', sa.String(64), nullable=True), sa.Column('crystal_purity', sa.Float(), nullable=True),
    sa.Column('crystal_titer', sa.Float(), nullable=True), sa.Column('filtrate_volume', sa.String(64), nullable=True),
    sa.Column('mother_liquor_titer', sa.Float(), nullable=True), sa.Column('wash_water', sa.String(64), nullable=True),
    sa.Column('combined_liquor', sa.String(64), nullable=True), sa.Column('wash_loss', sa.Float(), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
    sa.PrimaryKeyConstraint('id'), schema='production')
    op.create_index('ix_f2_batch', 'filter2', ['batch_no'], unique=False, schema='production')
    op.create_index('ix_f2_frid', 'filter2', ['feishu_record_id'], unique=True, schema='production')

def downgrade():
    op.drop_table('filter2', schema='production')
