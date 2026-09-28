"""Add independently selectable sections to production overview grants."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "c9d400000058"
down_revision: str | None = "c9d400000057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("role_page_grants", "user_page_grants"):
        op.add_column(
            table,
            sa.Column("visible_sections", JSONB(), nullable=True),
            schema="identity",
        )


def downgrade() -> None:
    for table in ("user_page_grants", "role_page_grants"):
        op.drop_column(table, "visible_sections", schema="identity")
