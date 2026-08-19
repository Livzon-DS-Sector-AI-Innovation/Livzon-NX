"""add_unique_batch_product_to_seed_cultures

Revision ID: 0a1b2c3d4e5f
Revises: 9f6a7b8c0d1e
Create Date: 2026-07-07
"""
from alembic import op

revision = '0a1b2c3d4e5f'
down_revision = '9f6a7b8c0d1e'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_seed_cultures_batch_product ON production.seed_cultures (batch_no, product_name) WHERE is_deleted = false")

def downgrade():
    op.execute("DROP INDEX IF EXISTS production.uq_seed_cultures_batch_product")
