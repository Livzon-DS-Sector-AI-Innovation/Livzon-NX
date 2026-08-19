"""add_conc1_table

Revision ID: 1a2b3c4d5e6f
Revises: 9b0c1d2e3f4a
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
revision = '1a2b3c4d5e6f'; down_revision = '9b0c1d2e3f4a'

def upgrade():
    op.create_table('conc1',
    sa.Column('feishu_record_id', sa.String(64), nullable=True), sa.Column('seq_no', sa.Integer(), nullable=True),
    sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('feed_volume', sa.String(64), nullable=True),
    sa.Column('feed_titer', sa.Float(), nullable=True), sa.Column('feed_temp', sa.Float(), nullable=True),
    sa.Column('vacuum_degree', sa.Float(), nullable=True), sa.Column('evap_temp', sa.Float(), nullable=True),
    sa.Column('steam_pressure', sa.Float(), nullable=True), sa.Column('conc_duration', sa.Float(), nullable=True),
    sa.Column('condensate_volume', sa.String(64), nullable=True), sa.Column('endpoint_density', sa.Float(), nullable=True),
    sa.Column('endpoint_refraction', sa.Float(), nullable=True), sa.Column('endpoint_volume', sa.String(64), nullable=True),
    sa.Column('conc_weight', sa.String(64), nullable=True), sa.Column('conc_volume', sa.String(64), nullable=True),
    sa.Column('conc_titer', sa.Float(), nullable=True), sa.Column('conc_factor', sa.Float(), nullable=True),
    sa.Column('evap_loss', sa.String(64), nullable=True), sa.Column('wall_residue', sa.String(64), nullable=True),
    sa.Column('conc_yield', sa.Float(), nullable=True), sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
    sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
    sa.PrimaryKeyConstraint('id'), schema='production')
    op.create_index('ix_c1_batch', 'conc1', ['batch_no'], unique=False, schema='production')
    op.create_index('ix_c1_frid', 'conc1', ['feishu_record_id'], unique=True, schema='production')

def downgrade():
    op.drop_table('conc1', schema='production')
