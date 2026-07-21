"""add workflow fields to quality tables

Revision ID: 20260605_0001
Revises: 20260604_0002
Create Date: 2026-06-05
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260605_0001'
down_revision = '20260604_0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === deviations: add missing columns ===
    op.add_column('deviations', sa.Column('handler', sa.String(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('returned_step', sa.String(50), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('status_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('discovery_location', sa.Text(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('discovery_time', sa.Text(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('affected_items', sa.Text(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('batch_number', sa.Text(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('discoverer', sa.String(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('needs_cross_dept_review', sa.Boolean(), server_default='true', nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('cross_dept_reviewers', sa.JSON(), server_default='[]', nullable=True), schema='quality')

    # === capas: add missing columns ===
    op.add_column('capas', sa.Column('returned_step', sa.String(50), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('status_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('reporter', sa.String(), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('source_code', sa.String(255), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('evaluation_deadline', sa.DateTime(timezone=True), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('qa_confirmer', sa.String(), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('qa_confirm_date', sa.DateTime(timezone=True), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('root_cause_attachments', postgresql.ARRAY(sa.Text()), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('reason_category', sa.String(255), nullable=True), schema='quality')

    # === department_contacts: add missing column ===
    op.add_column('department_contacts', sa.Column('is_production_workshop', sa.Boolean(), server_default='false', nullable=True), schema='quality')


def downgrade() -> None:
    # department_contacts
    op.drop_column('department_contacts', 'is_production_workshop', schema='quality')
    # capas
    for col in ['reason_category', 'root_cause_attachments', 'qa_confirm_date', 'qa_confirmer',
                'evaluation_deadline', 'source_code', 'reporter', 'status_updated_at', 'returned_step']:
        op.drop_column('capas', col, schema='quality')
    # deviations
    for col in ['cross_dept_reviewers', 'needs_cross_dept_review', 'discoverer', 'batch_number',
                'affected_items', 'discovery_time', 'discovery_location', 'status_updated_at',
                'returned_step', 'handler']:
        op.drop_column('deviations', col, schema='quality')
