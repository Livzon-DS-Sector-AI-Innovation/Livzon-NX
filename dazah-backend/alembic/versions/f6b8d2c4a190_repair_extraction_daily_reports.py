"""Restore the historical extraction report table when local schema has drifted.

Revision ID: f6b8d2c4a190
Revises: e3a715c9d602

The table belongs to historical revision c8f5a2d7e4b6. Existing installations
must retain both their table and data; only a missing table is created here.
"""

import sqlalchemy as sa

from alembic import op

revision = "f6b8d2c4a190"
down_revision = "e3a715c9d602"
branch_labels = None
depends_on = None

SCHEMA = "production"
TABLE = "extraction_daily_reports"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_schema(SCHEMA):
        raise RuntimeError("Production schema is missing; review schema drift first")
    if inspector.has_table(TABLE, schema=SCHEMA):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("quantity_kg", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("identity.users.id")),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("identity.users.id")),
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("product_code", sa.String(32), nullable=False, server_default="FA"),
        schema=SCHEMA,
    )
    op.create_index(
        "ux_extraction_daily_reports_product_date",
        TABLE,
        ["product_code", "report_date"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    # This table is still owned by c8f5a2d7e4b6 in the parent history. Removing
    # this repair must not delete pre-existing tables or newly recorded data.
    pass
