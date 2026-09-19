"""Add feishu_form_url to hr entity settings (form-based entry per entity)."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000047"
down_revision: str | None = "c9d400000046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "hr_feishu_entity_settings"
_SCHEMA = "hr"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("feishu_form_url", sa.String(length=512), nullable=True),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "feishu_form_url", schema=_SCHEMA)
