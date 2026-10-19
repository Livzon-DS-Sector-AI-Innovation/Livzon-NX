"""Repair overview query columns while preserving plans and actual quantities."""

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
    / "alembic/versions/b7e9a3c5d102_repair_production_overview_columns.py"
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("overview_column_repair", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_revision(conn: Connection, module: ModuleType, direction: str) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, direction)()


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_columns", [False, True])
async def test_overview_repair_preserves_existing_rows_and_defaults(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    existing_columns: bool,
) -> None:
    module = migration()
    schema = "overview_repair_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    connection = await db_session.connection()
    for name, field, column_type, value in [
        ("production_plans", "row_order", sa.Integer(), 7),
        ("fermentation_batch_actuals", "extract_kg", sa.Float(), 3.25),
    ]:
        columns = [sa.Column("marker", sa.String(32), primary_key=True)]
        if existing_columns:
            columns.append(sa.Column(field, column_type))
        table = sa.Table(name, sa.MetaData(), *columns, schema=schema)
        await connection.run_sync(lambda c: table.create(c))
        values = {"marker": "preserve"}
        if existing_columns:
            values[field] = value
        await db_session.execute(table.insert().values(**values))

    await connection.run_sync(run_revision, module, "upgrade")
    for name, field, expected, value in [
        ("production_plans", "row_order", 0, 7),
        ("fermentation_batch_actuals", "extract_kg", None, 3.25),
    ]:
        table = await connection.run_sync(
            lambda c: sa.Table(name, sa.MetaData(), schema=schema, autoload_with=c)
        )
        assert (await db_session.execute(sa.select(table))).all() == [
            ("preserve", value if existing_columns else expected)
        ]
        if not existing_columns:
            assert table.c[field].nullable is (field == "extract_kg")
            assert isinstance(
                table.c[field].type, sa.Integer if field == "row_order" else sa.Float
            )
        await db_session.execute(table.update().values(**{field: value}))
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(run_revision, module, "downgrade")
    for name, field, value in [
        ("production_plans", "row_order", 7),
        ("fermentation_batch_actuals", "extract_kg", 3.25),
    ]:
        table = await connection.run_sync(
            lambda c: sa.Table(name, sa.MetaData(), schema=schema, autoload_with=c)
        )
        assert await db_session.scalar(sa.select(table.c[field])) == value


@pytest.mark.asyncio
async def test_missing_table_stops_repair_before_any_column_is_added(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = "overview_missing_" + uuid4().hex
    monkeypatch.setattr(module, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    connection = await db_session.connection()
    table = sa.Table(
        "production_plans",
        sa.MetaData(),
        sa.Column("marker", sa.Integer()),
        schema=schema,
    )
    await connection.run_sync(lambda c: table.create(c))
    with pytest.raises(RuntimeError, match="fermentation_batch_actuals"):
        await connection.run_sync(run_revision, module, "upgrade")
    columns = await connection.run_sync(
        lambda c: sa.inspect(c).get_columns(table.name, schema=schema)
    )
    assert [c["name"] for c in columns] == ["marker"]
