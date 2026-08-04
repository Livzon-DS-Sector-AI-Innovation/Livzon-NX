"""normalize migrated external identity binding source

Revision ID: 8b42d1e6f903
Revises: 7a31c9e4d2b8
Create Date: 2026-08-03 02:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "8b42d1e6f903"
down_revision: str | None = "7a31c9e4d2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE identity.external_identity_bindings
        SET source = 'directory_sync'
        WHERE source = 'identity.users'
          AND binding_metadata->>'migration_source' = 'identity.users'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE identity.external_identity_bindings
        SET source = 'identity.users'
        WHERE source = 'directory_sync'
          AND binding_metadata->>'migration_source' = 'identity.users'
        """
    )
