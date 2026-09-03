"""Check menu retirement against an isolated PostgreSQL schema."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.menu_seed_data import SEED_MENUS


def test_research_menu_keeps_other_features() -> None:
    research = next(menu for menu in SEED_MENUS if menu["key"] == "rd")
    paths = {menu["path"] for menu in research["children"]}
    assert "/rd/bayesian" not in paths
    assert {"/rd/projects", "/rd/ich-analysis", "/rd/pilot-workflow"} <= paths


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "status", "deleted", "expected"),
    [
        ("/rd/bayesian", "active", False, "disabled"),
        ("/rd/bayesian", "disabled", False, "disabled"),
        ("/rd/bayesian", "active", True, "active"),
        ("/rd/custom", "active", False, "active"),
    ],
)
async def test_menu_retirement_preserves_custom_menus_and_existing_state(
    db_session: AsyncSession,
    route: str,
    status: str,
    deleted: bool,
    expected: str,
) -> None:
    path = (
        Path(__file__).parents[2]
        / "alembic/versions/e4a9c2d7b601_retire_edbo_menu.py"
    )
    spec = importlib.util.spec_from_file_location("retire_edbo_menu", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    schema = f"edbo_retirement_test_{uuid4().hex}"
    connection = await db_session.connection()
    await connection.execute(sa.schema.CreateSchema(schema))
    connection = await connection.execution_options(
        schema_translate_map={"identity": schema}
    )
    menus = sa.Table(
        "menus",
        sa.MetaData(),
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("route_path", sa.String),
        sa.Column("status", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        schema="identity",
    )
    await connection.run_sync(menus.create)
    rows = [
        ("rd:bayesian", route, status, deleted),
        ("rd:projects", "/rd/projects", "active", False),
        ("custom", "/rd/bayesian", "active", False),
    ]
    await connection.execute(
        menus.insert(),
        [
            dict(zip(("key", "route_path", "status", "is_deleted"), row))
            for row in rows
        ],
    )

    def run_migration(sync_connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(sync_connection)):
            migration.upgrade()
            migration.upgrade()
            migration.downgrade()

    await connection.run_sync(run_migration)
    result = await connection.execute(sa.select(menus.c.key, menus.c.status))
    assert dict(result.all()) == {
        "rd:bayesian": expected,
        "rd:projects": "active",
        "custom": "active",
    }
    # The surrounding test transaction rolls back the isolated schema as well.
