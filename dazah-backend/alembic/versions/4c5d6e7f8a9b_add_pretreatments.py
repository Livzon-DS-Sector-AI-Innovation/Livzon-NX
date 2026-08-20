"""add_pretreatments_table

Revision ID: 4c5d6e7f8a9b
Revises: 3b4c5d6e7f8a
Create Date: 2026-07-09
"""

import sqlalchemy as sa

from alembic import op

revision = "4c5d6e7f8a9b"
down_revision = "3b4c5d6e7f8a"


def upgrade():
    op.create_table(
        "pretreatments",
        sa.Column("seq_no", sa.Integer(), nullable=True, comment="序号"),
        sa.Column("received_batch", sa.String(128), nullable=False),
        sa.Column("broth_volume", sa.String(64), nullable=True),
        sa.Column("acid_type", sa.String(64), nullable=True),
        sa.Column("acid_amount", sa.String(64), nullable=True),
        sa.Column("neutralize_ph", sa.Float(), nullable=True),
        sa.Column("dilution_water_volume", sa.String(64), nullable=True),
        sa.Column("dilution_ratio", sa.String(64), nullable=True),
        sa.Column("target_temp", sa.Float(), nullable=True),
        sa.Column("holding_time", sa.String(64), nullable=True),
        sa.Column("temp_curve", sa.Text(), nullable=True),
        sa.Column("settling_time", sa.String(64), nullable=True),
        sa.Column("settling_temp", sa.Float(), nullable=True),
        sa.Column("stirring_speed", sa.String(64), nullable=True),
        sa.Column("stirring_time", sa.String(128), nullable=True),
        sa.Column("supernatant_volume", sa.String(64), nullable=True),
        sa.Column("sediment_weight", sa.String(64), nullable=True),
        sa.Column("titer_before", sa.Float(), nullable=True),
        sa.Column("titer_after", sa.Float(), nullable=True),
        sa.Column("yield_rate", sa.Float(), nullable=True),
        sa.Column("impurity_content", sa.Float(), nullable=True),
        sa.Column("loss", sa.Float(), nullable=True),
        sa.Column("residue_titer", sa.Float(), nullable=True),
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
        "ix_pretreat_batch",
        "pretreatments",
        ["received_batch"],
        unique=False,
        schema="production",
    )


def downgrade():
    op.drop_table("pretreatments", schema="production")
