"""add_centrifuge2_table

Revision ID: 7a8b9c0d1e2a
Revises: 6f7a8b9c0d1e
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "7a8b9c0d1e2a"
down_revision = "6f7a8b9c0d1e"


def upgrade():
    op.create_table(
        "centrifuge2",
        sa.Column("feishu_record_id", sa.String(64), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("feed_volume", sa.String(64), nullable=True),
        sa.Column("rotation_speed", sa.Float(), nullable=True),
        sa.Column("sep_duration", sa.Float(), nullable=True),
        sa.Column("feed_flow", sa.Float(), nullable=True),
        sa.Column("crystal_wet_weight", sa.String(64), nullable=True),
        sa.Column("waste_liquor_volume", sa.String(64), nullable=True),
        sa.Column("mother_liquor_titer", sa.Float(), nullable=True),
        sa.Column("crystal_moisture", sa.Float(), nullable=True),
        sa.Column("liquor_recovery", sa.String(64), nullable=True),
        sa.Column("crystal_yield", sa.Float(), nullable=True),
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
        "ix_cf2_batch", "centrifuge2", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "ix_cf2_frid",
        "centrifuge2",
        ["feishu_record_id"],
        unique=True,
        schema="production",
    )


def downgrade():
    op.drop_table("centrifuge2", schema="production")
