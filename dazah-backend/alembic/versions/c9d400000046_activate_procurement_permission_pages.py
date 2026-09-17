"""Activate current procurement pages and retire stale labor menus."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000046"
down_revision: str | None = "c9d400000045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PROCUREMENT_PAGES_TO_ACTIVATE = (
    ("purchasing:supplier", "/purchasing/supplier"),
    ("purchasing:order", "/purchasing/order"),
)

# Keep obsolete menu identities for audit/history while removing them from the
# active menu tree. The directory is included because its children are retired
# below; leaving it active would expose an empty duplicate labor group.
_STALE_PROCUREMENT_MENUS = (
    (
        "purchasing:request:request-labor-protection",
        "/purchasing/request/labor-protection",
    ),
    ("purchasing:approval:approval-labor-protection", None),
    (
        "purchasing:approval:approval-labor-protection:approval-labor-protection-department-head",
        "/purchasing/approval/labor-protection/department-head",
    ),
    (
        "purchasing:approval:approval-labor-protection:approval-labor-protection-responsible-leader",
        "/purchasing/approval/labor-protection/responsible-leader",
    ),
)


def _menus_table() -> sa.Table:
    return sa.Table(
        "menus",
        sa.MetaData(),
        sa.Column("key", sa.String),
        sa.Column("route_path", sa.String),
        sa.Column("status", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )


def upgrade() -> None:
    menus = _menus_table()
    for key, route_path in _PROCUREMENT_PAGES_TO_ACTIVATE:
        op.execute(
            menus.update()
            .where(
                menus.c.key == key,
                menus.c.route_path == route_path,
                menus.c.status == "disabled",
                menus.c.is_deleted.is_(False),
            )
            .values(status="active", updated_at=sa.func.now())
        )

    for key, route_path in _STALE_PROCUREMENT_MENUS:
        route_filter = (
            menus.c.route_path.is_(None)
            if route_path is None
            else menus.c.route_path == route_path
        )
        op.execute(
            menus.update()
            .where(
                menus.c.key == key,
                route_filter,
                menus.c.is_deleted.is_(False),
            )
            .values(status="disabled", is_deleted=True, updated_at=sa.func.now())
        )


def downgrade() -> None:
    # A downgrade must not silently re-enable obsolete menu identities or
    # override an administrator's later activation decision.
    pass
