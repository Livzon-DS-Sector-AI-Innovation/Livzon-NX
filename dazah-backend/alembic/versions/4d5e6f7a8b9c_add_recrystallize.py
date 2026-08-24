"""add_recrystallize_table

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"


def upgrade():
    op.create_table(
        "recrystallize",
        sa.Column("feishu_record_id", sa.String(64), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("feed_volume", sa.String(64), nullable=True),
        sa.Column("feed_titer", sa.Float(), nullable=True),
        sa.Column("solvent_amount", sa.String(64), nullable=True),
        sa.Column("water_amount", sa.String(64), nullable=True),
        sa.Column("solvent_ratio", sa.String(64), nullable=True),
        sa.Column("carbon_dosage", sa.Float(), nullable=True),
        sa.Column("dissolve_temp", sa.Float(), nullable=True),
        sa.Column("holding_time", sa.Float(), nullable=True),
        sa.Column("cooling_rate", sa.Float(), nullable=True),
        sa.Column("crystal_temp", sa.Float(), nullable=True),
        sa.Column("crystal_time", sa.Float(), nullable=True),
        sa.Column("color_hazen", sa.Float(), nullable=True),
        sa.Column("transmittance", sa.Float(), nullable=True),
        sa.Column("crystal_size", sa.Float(), nullable=True),
        sa.Column("mother_liquor_titer", sa.Float(), nullable=True),
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
        "ix_rx_batch", "recrystallize", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "ix_rx_frid",
        "recrystallize",
        ["feishu_record_id"],
        unique=True,
        schema="production",
    )


def downgrade():
    op.drop_table("recrystallize", schema="production")
