"""Remove the unused annual plan operation scope columns."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "8ac71ef51d03"
down_revision = "d6a4b981e702"
branch_labels = None
depends_on = None

TABLES = ("role_page_grants", "user_page_grants")


def upgrade() -> None:
    op.execute(
        "LOCK TABLE identity.role_page_grants, identity.user_page_grants "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM identity.role_page_grants
                WHERE scope_type = 'operation_departments'
                   OR operation_departments IS NOT NULL
            ) OR EXISTS (
                SELECT 1 FROM identity.user_page_grants
                WHERE scope_type = 'operation_departments'
                   OR operation_departments IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Stored operation-specific grants still exist';
            END IF;
        END;
        $$;
    """)
    for table in TABLES:
        op.drop_column(table, "operation_departments", schema="identity")


def downgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("operation_departments", postgresql.JSONB(), nullable=True),
            schema="identity",
        )
