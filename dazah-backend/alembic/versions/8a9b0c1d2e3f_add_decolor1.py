"""add_decolor1_table

Revision ID: 8a9b0c1d2e3f
Revises: 7f8a9b0c1d2e
Create Date: 2026-07-10
"""

import sqlalchemy as sa

from alembic import op

revision = "8a9b0c1d2e3f"
down_revision = "7f8a9b0c1d2e"


def upgrade():
    op.create_table(
        "decolor1",
        sa.Column("feishu_record_id", sa.String(64), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("feed_volume", sa.String(64), nullable=True),
        sa.Column("feed_titer", sa.Float(), nullable=True),
        sa.Column("carbon_type", sa.String(64), nullable=True),
        sa.Column("dosage", sa.String(64), nullable=True),
        sa.Column("stirring_speed", sa.Float(), nullable=True),
        sa.Column("decolor_temp", sa.Float(), nullable=True),
        sa.Column("holding_time", sa.Float(), nullable=True),
        sa.Column("endpoint_transmittance", sa.String(64), nullable=True),
        sa.Column("decolor_volume", sa.String(64), nullable=True),
        sa.Column("color_before", sa.String(64), nullable=True),
        sa.Column("color_after", sa.String(64), nullable=True),
        sa.Column("color_removal_rate", sa.Float(), nullable=True),
        sa.Column("heavy_metal", sa.Text(), nullable=True),
        sa.Column("protein_impurity", sa.Text(), nullable=True),
        sa.Column("transmittance_data", sa.Text(), nullable=True),
        sa.Column("carbon_residue", sa.String(64), nullable=True),
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
        "ix_d1_batch", "decolor1", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "ix_d1_frid", "decolor1", ["feishu_record_id"], unique=True, schema="production"
    )


def downgrade():
    op.drop_table("decolor1", schema="production")
