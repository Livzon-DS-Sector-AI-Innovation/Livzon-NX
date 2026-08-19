"""add_feishu_record_id_to_ceramic_5tables

Revision ID: 7f8a9b0c1d2e
Revises: 6e7f8a9b0c1d
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
revision = '7f8a9b0c1d2e'; down_revision = '6e7f8a9b0c1d'

TABLES = ['ceramic_feeds','ceramic_membrane_ops','ceramic_membrane_cleans','ceramic_material_separations','ceramic_equipment_logs']

def upgrade():
    for t in TABLES:
        op.add_column(t, sa.Column('feishu_record_id', sa.String(64), nullable=True), schema='production')
        op.create_index(f'ix_{t}_frid', t, ['feishu_record_id'], unique=True, schema='production')

def downgrade():
    for t in TABLES:
        op.drop_index(f'ix_{t}_frid', table_name=t, schema='production')
        op.drop_column(t, 'feishu_record_id', schema='production')
