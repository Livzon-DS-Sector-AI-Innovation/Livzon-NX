"""Disable the retired EHS application menu that duplicates the review route."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2e9e5fc78d1"
down_revision: str | None = "18a00b63c9b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    menus = sa.table(
        "menus",
        sa.column("key", sa.String),
        sa.column("route_path", sa.String),
        sa.column("type", sa.String),
        sa.column("status", sa.String),
        sa.column("is_deleted", sa.Boolean),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )
    op.execute(
        menus.update()
        .where(
            menus.c.key == "safety:risk-hazard:ehs-change:ehs-change-apply",
            menus.c.route_path == "/safety/ehs-change",
            menus.c.type == "menu",
            menus.c.status == "active",
            menus.c.is_deleted.is_(False),
        )
        .values(status="disabled", updated_at=sa.func.now())
    )


def downgrade() -> None:
    # A retired permission identity must not reappear in the active menu.
    pass
