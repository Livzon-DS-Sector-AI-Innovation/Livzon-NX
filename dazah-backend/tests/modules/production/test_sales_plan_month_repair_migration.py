"""Restore a historical month column without losing sales-plan snapshots."""

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
    / "a4d6f2b8c901_repair_sales_plan_data_month.py"
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sales_month_repair", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_revision(conn: Connection, module: ModuleType, direction: str) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, direction)()


@pytest.mark.asyncio
async def test_missing_sales_plan_month_is_repaired_without_losing_rows(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = migration()
    schema = "sales_month_repair_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    table = sa.Table(
        "sales_plan_details",
        sa.MetaData(),
        sa.Column("marker", sa.String(32), primary_key=True),
        schema=schema,
    )
    connection = await db_session.connection()
    await connection.run_sync(lambda c: table.create(c))
    await db_session.execute(table.insert().values(marker="preserve-existing"))
    await connection.run_sync(run_revision, module, "upgrade")

    def inspect_table(conn: Connection) -> sa.Table:
        inspector = sa.inspect(conn)
        column = next(
            c
            for c in inspector.get_columns(table.name, schema=schema)
            if c["name"] == "data_month"
        )
        assert isinstance(column["type"], sa.String) and column["type"].length == 7
        assert column["nullable"]
        indexes = inspector.get_indexes(table.name, schema=schema)
        assert any(
            i["name"] == "ix_sales_plan_data_month"
            and i["column_names"] == ["data_month"]
            for i in indexes
        )
        return sa.Table(table.name, sa.MetaData(), schema=schema, autoload_with=conn)

    repaired = await connection.run_sync(inspect_table)
    assert (await db_session.execute(sa.select(repaired))).all() == [
        ("preserve-existing", None)
    ]
    await db_session.execute(repaired.update().values(data_month="2026-10"))
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(run_revision, module, "downgrade")
    assert (await db_session.execute(sa.select(repaired))).all() == [
        ("preserve-existing", "2026-10")
    ]


@pytest.mark.asyncio
async def test_existing_sales_plan_month_keeps_values_and_repairs_missing_index(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = migration()
    schema = "sales_month_existing_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    table = sa.Table(
        "sales_plan_details",
        sa.MetaData(),
        sa.Column("marker", sa.String(32), primary_key=True),
        sa.Column("data_month", sa.String(7)),
        schema=schema,
    )
    connection = await db_session.connection()
    await connection.run_sync(lambda c: table.create(c))
    await db_session.execute(
        table.insert().values(marker="snapshot", data_month="2026-09")
    )
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(run_revision, module, "downgrade")
    assert (await db_session.execute(sa.select(table))).all() == [
        ("snapshot", "2026-09")
    ]
    indexes = await connection.run_sync(
        lambda c: sa.inspect(c).get_indexes(table.name, schema=schema)
    )
    assert len(indexes) == 1 and indexes[0]["column_names"] == ["data_month"]


@pytest.mark.asyncio
async def test_sales_month_repair_rejects_a_missing_table(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = migration()
    schema = "sales_month_missing_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    connection = await db_session.connection()
    with pytest.raises(RuntimeError, match="sales_plan_details"):
        await connection.run_sync(run_revision, module, "upgrade")
    assert not await connection.run_sync(
        lambda c: sa.inspect(c).has_table("sales_plan_details", schema=schema)
    )
