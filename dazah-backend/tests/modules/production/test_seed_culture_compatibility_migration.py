"""Exercise the old and new column contracts on the same PostgreSQL rows."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

REVISION = "4bd62e5d78a1"


@pytest.mark.asyncio
async def test_seed_culture_legacy_writes_survive_upgrade_and_image_rollback(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    revision = ScriptDirectory("alembic").get_revision(REVISION)
    assert revision is not None
    migration = revision.module
    schema = "seed_compat_" + uuid4().hex
    monkeypatch.setattr(migration, "SCHEMA", schema)
    await db_session.execute(sa.schema.CreateSchema(schema))
    connection = await db_session.connection()

    previous = sa.Table(
        "seed_cultures",
        sa.MetaData(),
        sa.Column("id", sa.Integer, primary_key=True),
        *(
            sa.Column(name, JSONB(none_as_null=True))
            for name in migration.PERSON_COLUMNS
        ),
        schema=schema,
    )
    await connection.run_sync(previous.create)
    people = [
        {"name": "李四", "open_id": "ou_li", "avatar_url": "https://example.test/li"}
    ]
    await db_session.execute(
        previous.insert().values(
            id=1, **dict.fromkeys(migration.PERSON_COLUMNS, "张三、李四")
        )
    )
    await db_session.execute(previous.insert().values(id=2, prepare_operator=people))

    def run_revision(conn, direction):
        with Operations.context(MigrationContext.configure(conn)):
            getattr(migration, direction)()

    await connection.run_sync(run_revision, "upgrade")
    upgraded = await connection.run_sync(
        lambda conn: sa.Table(
            previous.name, sa.MetaData(), schema=schema, autoload_with=conn
        )
    )
    initial = (
        (await db_session.execute(upgraded.select().where(upgraded.c.id == 1)))
        .mappings()
        .one()
    )
    for name in migration.PERSON_COLUMNS:
        assert isinstance(upgraded.c[name].type, sa.String)
        assert initial[name] == initial[f"{name}_people"] == "张三、李四"
    assert (
        await db_session.scalar(
            sa.select(upgraded.c.prepare_operator).where(upgraded.c.id == 2)
        )
        == "李四"
    )

    await db_session.execute(
        upgraded.insert().values(id=3, prepare_operator="旧版新增")
    )
    await db_session.execute(
        upgraded.insert().values(id=4, prepare_operator_people=people)
    )
    await db_session.execute(
        upgraded.update()
        .where(upgraded.c.id == 4)
        .values(prepare_operator="李四", sterilization_operator="旧版消毒")
    )
    unchanged = (
        (await db_session.execute(upgraded.select().where(upgraded.c.id == 4)))
        .mappings()
        .one()
    )
    assert unchanged["prepare_operator_people"] == people
    assert unchanged["sterilization_operator_people"] == "旧版消毒"

    await db_session.execute(
        upgraded.update()
        .where(upgraded.c.id == 4)
        .values(prepare_operator="回滚后更新", sterilization_operator=None)
    )
    updated = (
        (await db_session.execute(upgraded.select().where(upgraded.c.id == 4)))
        .mappings()
        .one()
    )
    assert updated["prepare_operator_people"] == "回滚后更新"
    assert updated["sterilization_operator_people"] is None
    assert (
        await db_session.scalar(
            sa.select(upgraded.c.prepare_operator_people).where(upgraded.c.id == 3)
        )
        == "旧版新增"
    )

    await connection.run_sync(run_revision, "downgrade")
    assert (
        await db_session.scalar(
            sa.select(previous.c.prepare_operator).where(previous.c.id == 2)
        )
        == people
    )
    assert (
        await db_session.scalar(
            sa.select(previous.c.prepare_operator).where(previous.c.id == 4)
        )
        == "回滚后更新"
    )
