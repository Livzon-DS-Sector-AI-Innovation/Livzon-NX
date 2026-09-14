"""Align legacy production menu rows with the current permission catalog."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000034"
down_revision: str | None = "c9d400000033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    menus = sa.Table(
        "menus",
        sa.MetaData(),
        sa.Column("key", sa.String),
        sa.Column("type", sa.String),
        sa.Column("route_path", sa.String),
        sa.Column("status", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )
    for legacy_directory_key, legacy_route_path in (
        ("production:batches", "/production/batches"),
        ("production:plan", "/production/plan"),
    ):
        op.execute(
            menus.update()
            .where(
                menus.c.key == legacy_directory_key,
                menus.c.route_path == legacy_route_path,
                menus.c.status == "active",
                menus.c.is_deleted.is_(False),
            )
            .values(type="directory", route_path=None, updated_at=sa.func.now())
        )

    op.execute(
        menus.update()
        .where(
            menus.c.key == "production:cost",
            menus.c.route_path == "/production/cost",
            menus.c.status == "active",
            menus.c.is_deleted.is_(False),
        )
        .values(status="disabled", updated_at=sa.func.now())
    )


def downgrade() -> None:
    # Keep the obsolete record disabled and the legacy parents as directories.
    # Reversing these changes would reintroduce pages intentionally retired from
    # the permission catalog and could hide the current child-page hierarchy.
    pass
