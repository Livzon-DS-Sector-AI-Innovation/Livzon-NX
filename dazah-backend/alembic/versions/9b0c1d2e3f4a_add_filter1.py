"""add_filter1_table

Revision ID: 9b0c1d2e3f4a
Revises: 8a9b0c1d2e3f
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "9b0c1d2e3f4a"
down_revision = "8a9b0c1d2e3f"


def upgrade():
    op.create_table(
        "filter1",
        sa.Column("feishu_record_id", sa.String(64), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("feed_volume", sa.String(64), nullable=True),
        sa.Column("feed_ph", sa.Float(), nullable=True),
        sa.Column("feed_temp", sa.Float(), nullable=True),
        sa.Column("feed_titer", sa.Float(), nullable=True),
        sa.Column("filter_pressure", sa.Float(), nullable=True),
        sa.Column("feed_flow", sa.Float(), nullable=True),
        sa.Column("filter_duration", sa.Float(), nullable=True),
        sa.Column("cloth_no", sa.String(64), nullable=True),
        sa.Column("filtrate_volume", sa.String(64), nullable=True),
        sa.Column("filtrate_titer", sa.Float(), nullable=True),
        sa.Column("cake_wet_weight", sa.String(64), nullable=True),
        sa.Column("cake_dry_weight", sa.String(64), nullable=True),
        sa.Column("cake_residue_titer", sa.Float(), nullable=True),
        sa.Column("pipe_residue", sa.String(64), nullable=True),
        sa.Column("cake_moisture", sa.Float(), nullable=True),
        sa.Column("filter_yield", sa.Float(), nullable=True),
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
        "ix_f1_batch", "filter1", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "ix_f1_frid", "filter1", ["feishu_record_id"], unique=True, schema="production"
    )


def downgrade():
    op.drop_table("filter1", schema="production")
