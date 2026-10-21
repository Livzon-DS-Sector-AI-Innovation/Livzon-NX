"""Repair a missing historical table without dropping existing report data."""

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

PATH = (
    Path(__file__).parents[3]
    / "alembic"
    / "versions"
    / "f6b8d2c4a190_repair_extraction_daily_reports.py"
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("report_repair_migration", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_revision(connection: Connection, module: ModuleType, direction: str) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()


@pytest.mark.asyncio
async def test_missing_report_table_is_repaired_with_soft_delete_uniqueness(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = "report_repair_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    connection = await db_session.connection()
    await connection.run_sync(run_revision, module, "upgrade")

    def inspect_table(conn: Connection) -> sa.Table:
        inspector = sa.inspect(conn)
        columns = {
            c["name"]: c
            for c in inspector.get_columns(
                "extraction_daily_reports",
                schema=schema,
            )
        }
        assert set(columns) == {
            "id",
            "product_code",
            "report_date",
            "quantity_kg",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "is_deleted",
        }
        assert isinstance(columns["id"]["type"], sa.Uuid)
        assert isinstance(columns["report_date"]["type"], sa.Date)
        assert isinstance(columns["quantity_kg"]["type"], sa.Float)
        assert not columns["is_deleted"]["nullable"]
        assert inspector.get_pk_constraint("extraction_daily_reports", schema=schema)[
            "constrained_columns"
        ] == ["id"]
        indexes = inspector.get_indexes("extraction_daily_reports", schema=schema)
        unique = next(
            i
            for i in indexes
            if i["name"] == "ux_extraction_daily_reports_product_date"
        )
        assert unique["unique"]
        assert unique["column_names"] == ["product_code", "report_date"]
        assert "is_deleted = false" in unique["dialect_options"]["postgresql_where"]
        foreign_keys = inspector.get_foreign_keys(
            "extraction_daily_reports", schema=schema
        )
        assert {tuple(k["constrained_columns"]) for k in foreign_keys} == {
            ("created_by",),
            ("updated_by",),
        }
        assert all(k["referred_schema"] == "identity" for k in foreign_keys)
        return sa.Table(
            "extraction_daily_reports", sa.MetaData(), schema=schema, autoload_with=conn
        )

    table = await connection.run_sync(inspect_table)
    from datetime import date

    for value in [1, 2, 3]:
        identifier = uuid4()
        await db_session.execute(
            table.insert().values(
                id=identifier,
                report_date=date(2026, 10, 16),
                quantity_kg=value,
            )
        )
        if value != 3:
            await db_session.execute(
                table.update().where(table.c.id == identifier).values(is_deleted=True)
            )
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(table)) == 3
    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(table)
            .where(table.c.is_deleted.is_(False))
        )
        == 1
    )

    # This is a historical repair; rolling back this revision must preserve data
    # still owned by the original c8f5a2d7e4b6 migration in the parent history.
    await connection.run_sync(run_revision, module, "downgrade")
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(inspect_table)
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(table)) == 3


@pytest.mark.asyncio
async def test_repair_does_not_recreate_a_table_that_already_exists(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = "report_existing_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    connection = await db_session.connection()
    table = sa.Table(
        "extraction_daily_reports",
        sa.MetaData(),
        sa.Column("marker", sa.String(32), primary_key=True),
        schema=schema,
    )
    await connection.run_sync(lambda c: table.create(c))
    await db_session.execute(table.insert().values(marker="preserve-existing"))
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(run_revision, module, "downgrade")
    assert (await db_session.execute(sa.select(table.c.marker))).scalars().all() == [
        "preserve-existing"
    ]


@pytest.mark.asyncio
async def test_repair_rejects_a_missing_production_schema(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = "report_missing_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    connection = await db_session.connection()
    with pytest.raises(RuntimeError, match="schema"):
        await connection.run_sync(run_revision, module, "upgrade")
    assert not await connection.run_sync(lambda c: sa.inspect(c).has_schema(schema))
