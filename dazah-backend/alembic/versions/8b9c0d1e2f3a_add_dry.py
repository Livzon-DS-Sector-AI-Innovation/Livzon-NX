"""add_dry_table

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2a
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "8b9c0d1e2f3a"
down_revision = "7a8b9c0d1e2a"


def upgrade():
    op.create_table(
        "dry",
        sa.Column("feishu_record_id", sa.String(64), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("feed_weight", sa.String(64), nullable=True),
        sa.Column("wet_moisture", sa.Float(), nullable=True),
        sa.Column("oven_temp", sa.Float(), nullable=True),
        sa.Column("vacuum_degree", sa.Float(), nullable=True),
        sa.Column("dry_duration", sa.Float(), nullable=True),
        sa.Column("air_flow", sa.Float(), nullable=True),
        sa.Column("turn_interval", sa.Float(), nullable=True),
        sa.Column("endpoint_moisture", sa.Float(), nullable=True),
        sa.Column("dry_weight", sa.String(64), nullable=True),
        sa.Column("dry_titer", sa.Float(), nullable=True),
        sa.Column("dry_purity", sa.Float(), nullable=True),
        sa.Column("powder_loss", sa.String(64), nullable=True),
        sa.Column("tray_residue", sa.String(64), nullable=True),
        sa.Column("dry_yield", sa.Float(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["identity.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="production",
    )
    op.create_index(
        "ix_dry_batch", "dry", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "ix_dry_frid", "dry", ["feishu_record_id"], unique=True, schema="production"
    )


def downgrade():
    op.drop_table("dry", schema="production")
