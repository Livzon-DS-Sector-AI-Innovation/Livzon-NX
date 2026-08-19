"""rebuild_ceramic_5tables_with_feishu_fields

Revision ID: 6e7f8a9b0c1d
Revises: 5d6e7f8a9b0c
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
revision = '6e7f8a9b0c1d'; down_revision = '5d6e7f8a9b0c'

def upgrade():
    for t in ['ceramic_feeds','ceramic_membrane_ops','ceramic_membrane_cleans','ceramic_material_separations','ceramic_equipment_logs']:
        op.drop_table(t, schema='production')

    # 1. 进料数据
    op.create_table('ceramic_feeds',
        sa.Column('seq_no', sa.Integer(), nullable=True), sa.Column('feed_date', sa.Date(), nullable=True),
        sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('feed_volume', sa.Float(), nullable=True),
        sa.Column('feed_concentration', sa.Float(), nullable=True), sa.Column('feed_temp', sa.Float(), nullable=True),
        sa.Column('ph_value', sa.Float(), nullable=True), sa.Column('tank_no', sa.String(64), nullable=True),
        sa.Column('material_name', sa.String(64), nullable=True), sa.Column('operator', sa.String(64), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
        sa.PrimaryKeyConstraint('id'), schema='production')

    # 2. 膜清洗
    op.create_table('ceramic_membrane_cleans',
        sa.Column('seq_no', sa.Integer(), nullable=True), sa.Column('clean_date', sa.Date(), nullable=True),
        sa.Column('membrane_no', sa.String(64), nullable=True), sa.Column('cleaner_type', sa.String(64), nullable=True),
        sa.Column('cleaner_concentration', sa.Float(), nullable=True), sa.Column('clean_temp', sa.Float(), nullable=True),
        sa.Column('clean_time', sa.Float(), nullable=True), sa.Column('clean_pressure', sa.Float(), nullable=True),
        sa.Column('flux_recovery', sa.Float(), nullable=True), sa.Column('operator', sa.String(64), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
        sa.PrimaryKeyConstraint('id'), schema='production')

    # 3. 膜运行
    op.create_table('ceramic_membrane_ops',
        sa.Column('seq_no', sa.Integer(), nullable=True), sa.Column('run_date', sa.Date(), nullable=True),
        sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('membrane_no', sa.String(64), nullable=True),
        sa.Column('run_pressure', sa.Float(), nullable=True), sa.Column('membrane_velocity', sa.Float(), nullable=True),
        sa.Column('tmp', sa.Float(), nullable=True), sa.Column('run_temp', sa.Float(), nullable=True),
        sa.Column('permeate_flux', sa.Float(), nullable=True), sa.Column('operator', sa.String(64), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
        sa.PrimaryKeyConstraint('id'), schema='production')

    # 4. 设备运行
    op.create_table('ceramic_equipment_logs',
        sa.Column('seq_no', sa.Integer(), nullable=True), sa.Column('record_date', sa.Date(), nullable=True),
        sa.Column('equipment_no', sa.String(64), nullable=False), sa.Column('run_status', sa.String(32), nullable=True),
        sa.Column('abnormal_type', sa.String(64), nullable=True), sa.Column('abnormal_desc', sa.Text(), nullable=True),
        sa.Column('action_taken', sa.Text(), nullable=True), sa.Column('action_result', sa.Text(), nullable=True),
        sa.Column('handler', sa.String(64), nullable=True), sa.Column('restore_time', sa.Date(), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
        sa.PrimaryKeyConstraint('id'), schema='production')

    # 5. 物料分离
    op.create_table('ceramic_material_separations',
        sa.Column('seq_no', sa.Integer(), nullable=True), sa.Column('sep_date', sa.Date(), nullable=True),
        sa.Column('batch_no', sa.String(128), nullable=False), sa.Column('separation_stage', sa.String(32), nullable=True),
        sa.Column('retentate_volume', sa.Float(), nullable=True), sa.Column('permeate_volume', sa.Float(), nullable=True),
        sa.Column('retentate_concentration', sa.Float(), nullable=True), sa.Column('permeate_concentration', sa.Float(), nullable=True),
        sa.Column('concentration_factor', sa.Float(), nullable=True), sa.Column('operator', sa.String(64), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True), sa.Column('updated_by', sa.Uuid(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['created_by'],['identity.users.id']), sa.ForeignKeyConstraint(['updated_by'],['identity.users.id']),
        sa.PrimaryKeyConstraint('id'), schema='production')

def downgrade():
    for t in ['ceramic_material_separations','ceramic_equipment_logs','ceramic_membrane_ops','ceramic_membrane_cleans','ceramic_feeds']:
        op.drop_table(t, schema='production')
