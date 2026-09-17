"""Retire three removed production page menus without deleting history."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000044"
down_revision: str | None = "c9d400000043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    menus = sa.Table(
        "menus",
        sa.MetaData(),
        sa.Column("key", sa.String),
        sa.Column("route_path", sa.String),
        sa.Column("status", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )
    for key, route_path in (
        ("production:process", "/production/process"),
        ("production:records", "/production/records"),
        ("production:balance", "/production/balance"),
    ):
        op.execute(
            menus.update()
            .where(
                menus.c.key == key,
                menus.c.route_path == route_path,
                menus.c.is_deleted.is_(False),
            )
            .values(status="disabled", is_deleted=True, updated_at=sa.func.now())
        )


def downgrade() -> None:
    # The removed page identities remain retired. Restoring database rows would
    # expose menus with no frontend route or page authorization definition.
    pass
