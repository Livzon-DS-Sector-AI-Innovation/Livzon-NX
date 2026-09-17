"""Retire stale quality menus and restore the current inspection leaf shape."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d400000045"
down_revision: str | None = "c9d400000044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# These rows belong to menu versions that no longer exist in the current
# frontend catalog. Keep their identities in the database for audit/history,
# but remove them from the active menu tree.
_RETIRED_QUALITY_MENUS = (
    ("quality:department-contacts", "/quality/department-contacts"),
    ("quality:feishu-settings", "/quality/feishu-settings"),
    (
        "quality:inspection:inspection-instruments:inspection-instruments-assets",
        "/quality/inspection/instruments/assets",
    ),
    (
        "quality:inspection:inspection-instruments:inspection-instruments-change",
        "/quality/inspection/instruments/change",
    ),
    (
        "quality:inspection:inspection-items:inspection-items-dashboard",
        "/quality/inspection/items/dashboard",
    ),
    (
        "quality:inspection:inspection-liquid:inspection-liquid-raw",
        "/quality/inspection/liquid/raw-inspection",
    ),
    *(
        (
            f"quality:inspection:inspection-liquid:inspection-liquid-yl-{suffix}",
            f"/quality/inspection/liquid/yl-{suffix}",
        )
        for suffix in ("0xx", "1xx", "2xx", "3xx", "4xx", "5xx", "6xx", "7xx", "8xx")
    ),
    (
        "quality:inspection:inspection-solid:inspection-solid-manual",
        "/quality/inspection/solid/manual",
    ),
    (
        "quality:inspection:inspection-solid:inspection-solid-raw",
        "/quality/inspection/solid/raw-inspection",
    ),
    *(
        (
            f"quality:inspection:inspection-solid:inspection-solid-ys-{suffix}",
            f"/quality/inspection/solid/ys-{suffix}",
        )
        for suffix in ("000", "100", "200", "300", "400", "500", "600", "700", "800")
    ),
    (
        "quality:validation-confirmation",
        "/quality/validation",
    ),
    *(
        (
            f"quality:validation-confirmation:{key}",
            f"/quality/validation/{route}",
        )
        for key, route in (
            ("cleaning-validation", "cleaning-validation"),
            ("equipment-qualification", "equipment-qualification"),
            ("other-validations", "other-validations"),
            ("process-validation", "process-validation"),
            ("validation-plans", "plans"),
        )
    ),
)

_INSPECTION_LEAF_MENUS = (
    ("quality:inspection:inspection-solid", "/quality/inspection/solid"),
    ("quality:inspection:inspection-liquid", "/quality/inspection/liquid"),
)


def _menus_table() -> sa.Table:
    return sa.Table(
        "menus",
        sa.MetaData(),
        sa.Column("key", sa.String),
        sa.Column("route_path", sa.String),
        sa.Column("type", sa.String),
        sa.Column("status", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )


def upgrade() -> None:
    menus = _menus_table()
    for key, route_path in _RETIRED_QUALITY_MENUS:
        op.execute(
            menus.update()
            .where(
                menus.c.key == key,
                menus.c.route_path == route_path,
                menus.c.is_deleted.is_(False),
            )
            .values(status="disabled", is_deleted=True, updated_at=sa.func.now())
        )

    # The current catalog exposes these as routable leaf pages. Legacy rows
    # were stored as directories because they once had material-code children.
    for key, route_path in _INSPECTION_LEAF_MENUS:
        op.execute(
            menus.update()
            .where(
                menus.c.key == key,
                menus.c.route_path == route_path,
                menus.c.type == "directory",
                menus.c.status == "active",
                menus.c.is_deleted.is_(False),
            )
            .values(type="menu", updated_at=sa.func.now())
        )


def downgrade() -> None:
    # The retired rows must not be reactivated, and restoring the legacy
    # directory shape would expose menu identities with no frontend page.
    pass
