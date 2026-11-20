"""Store operation-specific department selections on page grants."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d6a4b981e702"
down_revision = "f9a3d5c7e1b2"
branch_labels = None
depends_on = None

TABLES = ("role_page_grants", "user_page_grants")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("operation_departments", postgresql.JSONB(), nullable=True),
            schema="identity",
        )


def downgrade() -> None:
    # A custom grant has no equivalent legacy scope. The unsupported scope type
    # remains on the row so a downgraded application denies the grant.
    for table in TABLES:
        op.drop_column(table, "operation_departments", schema="identity")
