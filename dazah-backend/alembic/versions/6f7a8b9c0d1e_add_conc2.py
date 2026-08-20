"""add_conc2_table

Revision ID: 6f7a8b9c0d1e
Revises: 5e6f7a8b9c0d
Create Date: 2026-07-13
"""

import sqlalchemy as sa

from alembic import op

revision = "6f7a8b9c0d1e"
down_revision = "5e6f7a8b9c0d"


def upgrade():
    op.create_table(
        "conc2",
        sa.Column("feishu_record_id", sa.String(64), nullable=True),
        sa.Column("seq_no", sa.Integer(), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=False),
        sa.Column("feed_volume", sa.String(64), nullable=True),
        sa.Column("vacuum_degree", sa.Float(), nullable=True),
        sa.Column("evap_temp", sa.Float(), nullable=True),
        sa.Column("steam_pressure", sa.Float(), nullable=True),
        sa.Column("endpoint_refraction", sa.Float(), nullable=True),
        sa.Column("endpoint_density", sa.Float(), nullable=True),
        sa.Column("conc_volume", sa.String(64), nullable=True),
        sa.Column("conc_titer", sa.Float(), nullable=True),
        sa.Column("conc_factor", sa.Float(), nullable=True),
        sa.Column("condensate_volume", sa.String(64), nullable=True),
        sa.Column("bottom_residue", sa.String(64), nullable=True),
        sa.Column("evap_loss_rate", sa.Float(), nullable=True),
        sa.Column("conc_yield", sa.Float(), nullable=True),
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
        "ix_c2_batch", "conc2", ["batch_no"], unique=False, schema="production"
    )
    op.create_index(
        "ix_c2_frid", "conc2", ["feishu_record_id"], unique=True, schema="production"
    )


def downgrade():
    op.drop_table("conc2", schema="production")
