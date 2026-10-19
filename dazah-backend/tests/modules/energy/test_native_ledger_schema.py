import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import MetaData
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.energy.ledger_models import LEDGER_TABLES


@pytest.mark.asyncio
async def test_native_ledger_migration_matches_models_without_cross_module_foreign_keys(
    db_session: AsyncSession,
) -> None:
    metadata = MetaData()
    names = {table.name for table in LEDGER_TABLES}
    for table in LEDGER_TABLES:
        assert table.schema == "energy"
        assert all(not column.foreign_keys for column in table.columns)
        table.to_metadata(metadata)

    def compare(connection: Connection) -> list[object]:
        context = MigrationContext.configure(
            connection,
            opts={
                "include_schemas": True,
                "include_name": lambda name, kind, parents: (
                    name == "energy"
                    if kind == "schema"
                    else name in names
                    if kind == "table"
                    else True
                ),
            },
        )
        return list(compare_metadata(context, metadata))

    connection = await db_session.connection()
    assert await connection.run_sync(compare) == []
