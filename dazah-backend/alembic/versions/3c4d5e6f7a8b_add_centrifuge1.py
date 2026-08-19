"""add_centrifuge1_table

Revision ID: 3c4d5e6f7a8b
Revises: 1a2b3c4d5e6f
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
revision = '3c4d5e6f7a8b'; down_revision = '1a2b3c4d5e6f'

def upgrade():
    op.create_table('centrifuge1',
    sa.Column('feishu_record_id', sa.String(64), nullable=True), sa.Column('seq_no', sa.Integer(), nullable=True),
    sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('feed_volume', sa.String(64), nullable=True),
    sa.Column('solid_content', sa.Float(), nullable=True), sa.Column('feed_temp', sa.Float(), nullable=True),
    sa.Column('rotation_speed', sa.Float(), nullable=True), sa.Column('centrifuge_duration', sa.Float(), nullable=True),
    sa.Column('feed_flow', sa.Float(), nullable=True), sa.Column('sep_temp', sa.Float(), nullable=True),
    sa.Column('supernatant_volume', sa.String(64), nullable=True), sa.Column('supernatant_titer', sa.Float(), nullable=True),
    sa.Column('solid_waste_weight', sa.String(64), nullable=True), sa.Column('waste_titer', sa.Float(), nullable=True),
    sa.Column('waste_moisture', sa.Float(), nullable=True), sa.Column('centrifuge_yield', sa.Float(), nullable=True),
    sa.Column('solid_waste_output', sa.String(64), nullable=True), sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
    sa.PrimaryKeyConstraint('id'), schema='production')
    op.create_index('ix_cf1_batch', 'centrifuge1', ['batch_no'], unique=False, schema='production')
    op.create_index('ix_cf1_frid', 'centrifuge1', ['feishu_record_id'], unique=True, schema='production')

def downgrade():
    op.drop_table('centrifuge1', schema='production')
