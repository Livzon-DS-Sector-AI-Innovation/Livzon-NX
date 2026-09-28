"""Verify the overview grant migration on the isolated test database."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import AsyncSession


async def test_overview_sections_upgrade_and_downgrade(
    db_session: AsyncSession,
) -> None:
    path = (
        Path(__file__).parents[3]
        / "alembic/versions/c9d400000058_add_overview_visible_sections.py"
    )
    spec = importlib.util.spec_from_file_location("overview_sections_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    connection = await db_session.connection()

    def verify(sync_connection: sa.Connection) -> None:
        migration.op = Operations(MigrationContext.configure(sync_connection))

        def columns(table: str) -> dict[str, dict[str, object]]:
            return {
                column["name"]: column
                for column in sa.inspect(sync_connection).get_columns(
                    table, schema="identity"
                )
            }

        tables = ("role_page_grants", "user_page_grants")
        before = {table: columns(table) for table in tables}
        migration.downgrade()
        for table in tables:
            assert set(columns(table)) == set(before[table]) - {"visible_sections"}

        migration.upgrade()
        for table in tables:
            restored = columns(table)
            assert set(restored) == set(before[table])
            assert isinstance(restored["visible_sections"]["type"], sa.JSON)
            assert restored["visible_sections"]["nullable"] is True
            assert restored["visible_sections"]["default"] is None
            # Existing grants keep the backwards-compatible unrestricted value.
            assert sync_connection.scalar(
                sa.text(
                    f"SELECT count(*) FROM identity.{table} "
                    "WHERE visible_sections IS NOT NULL"
                )
            ) == 0

    await connection.run_sync(verify)
