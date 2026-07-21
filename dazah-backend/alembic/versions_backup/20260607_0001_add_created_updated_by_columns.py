"""add created_by and updated_by columns to quality tables

Revision ID: 20260607_0001
Revises: add_report_columns_to_deviations
Create Date: 2026-06-07

"""
from alembic import op
import sqlalchemy as sa


revision = '20260607_0001'
down_revision = 'add_report_columns_to_deviations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_by and updated_by to deviations
    op.add_column('deviations', sa.Column('created_by', sa.Uuid(), nullable=True), schema='quality')
    op.add_column('deviations', sa.Column('updated_by', sa.Uuid(), nullable=True), schema='quality')
    op.create_foreign_key(
        'fk_deviations_created_by',
        'deviations', 'users',
        ['created_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )
    op.create_foreign_key(
        'fk_deviations_updated_by',
        'deviations', 'users',
        ['updated_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )

    # Add created_by and updated_by to capas
    op.add_column('capas', sa.Column('created_by', sa.Uuid(), nullable=True), schema='quality')
    op.add_column('capas', sa.Column('updated_by', sa.Uuid(), nullable=True), schema='quality')
    op.create_foreign_key(
        'fk_capas_created_by',
        'capas', 'users',
        ['created_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )
    op.create_foreign_key(
        'fk_capas_updated_by',
        'capas', 'users',
        ['updated_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )

    # Add created_by and updated_by to department_contacts
    op.add_column('department_contacts', sa.Column('created_by', sa.Uuid(), nullable=True), schema='quality')
    op.add_column('department_contacts', sa.Column('updated_by', sa.Uuid(), nullable=True), schema='quality')
    op.create_foreign_key(
        'fk_department_contacts_created_by',
        'department_contacts', 'users',
        ['created_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )
    op.create_foreign_key(
        'fk_department_contacts_updated_by',
        'department_contacts', 'users',
        ['updated_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )

    # Add created_by and updated_by to department_weekly_confirmations
    op.add_column('department_weekly_confirmations', sa.Column('created_by', sa.Uuid(), nullable=True), schema='quality')
    op.add_column('department_weekly_confirmations', sa.Column('updated_by', sa.Uuid(), nullable=True), schema='quality')
    op.create_foreign_key(
        'fk_department_weekly_confirmations_created_by',
        'department_weekly_confirmations', 'users',
        ['created_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )
    op.create_foreign_key(
        'fk_department_weekly_confirmations_updated_by',
        'department_weekly_confirmations', 'users',
        ['updated_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )

    # Add created_by and updated_by to attachment_reviews
    op.add_column('attachment_reviews', sa.Column('created_by', sa.Uuid(), nullable=True), schema='quality')
    op.add_column('attachment_reviews', sa.Column('updated_by', sa.Uuid(), nullable=True), schema='quality')
    op.create_foreign_key(
        'fk_attachment_reviews_created_by',
        'attachment_reviews', 'users',
        ['created_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )
    op.create_foreign_key(
        'fk_attachment_reviews_updated_by',
        'attachment_reviews', 'users',
        ['updated_by'], ['id'],
        source_schema='quality',
        referent_schema='identity'
    )


def downgrade() -> None:
    # Drop from attachment_reviews
    op.drop_constraint('fk_attachment_reviews_updated_by', 'attachment_reviews', schema='quality')
    op.drop_constraint('fk_attachment_reviews_created_by', 'attachment_reviews', schema='quality')
    op.drop_column('attachment_reviews', 'updated_by', schema='quality')
    op.drop_column('attachment_reviews', 'created_by', schema='quality')

    # Drop from department_weekly_confirmations
    op.drop_constraint('fk_department_weekly_confirmations_updated_by', 'department_weekly_confirmations', schema='quality')
    op.drop_constraint('fk_department_weekly_confirmations_created_by', 'department_weekly_confirmations', schema='quality')
    op.drop_column('department_weekly_confirmations', 'updated_by', schema='quality')
    op.drop_column('department_weekly_confirmations', 'created_by', schema='quality')

    # Drop from department_contacts
    op.drop_constraint('fk_department_contacts_updated_by', 'department_contacts', schema='quality')
    op.drop_constraint('fk_department_contacts_created_by', 'department_contacts', schema='quality')
    op.drop_column('department_contacts', 'updated_by', schema='quality')
    op.drop_column('department_contacts', 'created_by', schema='quality')

    # Drop from capas
    op.drop_constraint('fk_capas_updated_by', 'capas', schema='quality')
    op.drop_constraint('fk_capas_created_by', 'capas', schema='quality')
    op.drop_column('capas', 'updated_by', schema='quality')
    op.drop_column('capas', 'created_by', schema='quality')

    # Drop from deviations
    op.drop_constraint('fk_deviations_updated_by', 'deviations', schema='quality')
    op.drop_constraint('fk_deviations_created_by', 'deviations', schema='quality')
    op.drop_column('deviations', 'updated_by', schema='quality')
    op.drop_column('deviations', 'created_by', schema='quality')
