"""Ensure the reviewed permission modules start in the pending-review state.

The original page-permission migration seeded the first group of modules, but
registration was added to the reviewed catalog later.  Keep the rollout rows
explicit and idempotent so an absent row is shown as ``draft`` (待核验)
without changing a module that has already been published or rolled back.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000033"
down_revision: str | None = "c9d400000032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODULE_CODES = ("hr", "warehouse", "registration", "production")


def upgrade() -> None:
    statement = sa.text(
        """
        INSERT INTO identity.permission_module_rollouts
            (id, module_code, status, version, is_deleted)
        VALUES (:id, :module_code, 'draft', 0, false)
        ON CONFLICT (module_code) DO NOTHING
        """
    )
    for module_code in _MODULE_CODES:
        op.execute(
            statement.bindparams(
                sa.bindparam("id", value=uuid.uuid4(), type_=sa.Uuid()),
                sa.bindparam(
                    "module_code", value=module_code, type_=sa.String(length=64)
                ),
            )
        )


def downgrade() -> None:
    """Keep rollout records on downgrade to avoid deleting authorization state."""
