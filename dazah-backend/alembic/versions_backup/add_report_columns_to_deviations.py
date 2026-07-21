"""add report columns to deviations

Revision ID: add_report_columns_to_deviations
Revises: 20260605_0001
Create Date: 2026-06-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_report_columns_to_deviations'
down_revision = '20260605_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('deviations', sa.Column('report_content', sa.Text(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('report_versions', sa.JSON(), nullable=True), schema='quality')


def downgrade() -> None:
    op.drop_column('deviations', 'report_versions', schema='quality')
    op.drop_column('deviations', 'report_content', schema='quality')
