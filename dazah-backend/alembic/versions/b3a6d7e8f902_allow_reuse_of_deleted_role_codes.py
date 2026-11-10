"""Allow reuse of codes from soft-deleted roles.

Revision ID: b3a6d7e8f902
Revises: e5b9d2f4a8c7
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3a6d7e8f902"
down_revision: str | None = "e5b9d2f4a8c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"
OLD_CONSTRAINT = "uq_identity_roles_code"
ACTIVE_INDEX = "uq_identity_roles_active_code"


def upgrade() -> None:
    op.create_index(
        ACTIVE_INDEX,
        "roles",
        ["code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.drop_constraint(OLD_CONSTRAINT, "roles", type_="unique", schema=SCHEMA)


def downgrade() -> None:
    # PostgreSQL rejects this constraint if a code has already been reused.
    op.create_unique_constraint(OLD_CONSTRAINT, "roles", ["code"], schema=SCHEMA)
    op.drop_index(ACTIVE_INDEX, table_name="roles", schema=SCHEMA)
