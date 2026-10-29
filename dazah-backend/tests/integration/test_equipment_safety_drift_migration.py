"""Repair known omissions without changing existing application data."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import op

PATH = (
    Path(__file__).parents[2]
    / "alembic/versions/f4a6c8e0b2d5_repair_equipment_safety_schema_drift.py"
)
BASE_TABLES = (
    "inspection_feishu_config",
    "feishu_app_settings",
    "page_feishu_configs",
    "hazard_identifications",
)


def migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("equipment_safety_repair", PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_revision(conn: Connection, module: ModuleType, direction: str) -> None:
    with Operations.context(MigrationContext.configure(conn)):
        getattr(module, direction)()


async def base_schema(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    *,
    omit: str | None = None,
) -> str:
    schema = "drift_repair_" + uuid4().hex
    await db.execute(sa.schema.CreateSchema(schema))
    monkeypatch.setattr(module, "SAFETY_SCHEMA", schema)
    monkeypatch.setattr(module, "EQUIPMENT_SCHEMA", schema)
    connection = await db.connection()
    for name in BASE_TABLES:
        if name == omit:
            continue
        table = sa.Table(
            name,
            sa.MetaData(),
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("marker", sa.String(32), nullable=False),
            schema=schema,
        )
        await connection.run_sync(table.create)
        await db.execute(table.insert().values(id=uuid4(), marker="keep-existing"))
    return schema


async def reflect(db: AsyncSession, schema: str, name: str) -> sa.Table:
    connection = await db.connection()
    return await connection.run_sync(
        lambda conn: sa.Table(name, sa.MetaData(), schema=schema, autoload_with=conn)
    )


@pytest.mark.asyncio
async def test_repair_is_repeatable_and_preserves_rows_and_configuration(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = await base_schema(db_session, monkeypatch, module)
    connection = await db_session.connection()
    await connection.run_sync(run_revision, module, "upgrade")
    equipment = await reflect(db_session, schema, "inspection_feishu_config")
    settings = await reflect(db_session, schema, "feishu_app_settings")
    page = await reflect(db_session, schema, "page_feishu_configs")
    hazard = await reflect(db_session, schema, "hazard_identifications")
    assert await db_session.scalar(sa.select(equipment.c.base_url)) == ""
    assert (
        await db_session.scalar(sa.select(settings.c.fire_expiry_notify_enabled))
        is False
    )
    await db_session.execute(
        equipment.update().values(base_url="https://example.test/base")
    )
    await db_session.execute(
        settings.update().values(
            fire_expiry_notify_enabled=True,
            fire_expiry_notify_milestones=[30, 7],
            fire_expiry_notify_chat_ids=["synthetic-chat"],
        )
    )
    await db_session.execute(page.update().values(writeback_table_id="synthetic-table"))
    await db_session.execute(hazard.update().values(responsible_unit="测试车间"))

    fire = await reflect(db_session, schema, "fire_equipment")
    inspection = await reflect(db_session, schema, "fire_inspection_records")
    log = await reflect(db_session, schema, "fire_expiry_notification_log")
    equipment_id, inspection_id, log_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    await db_session.execute(
        fire.insert().values(
            id=equipment_id,
            page_key="test",
            table_id="table",
            record_id="record",
            fields={"marker": "keep"},
            expiry_date=now.date(),
        )
    )
    await db_session.execute(
        inspection.insert().values(
            id=inspection_id,
            equipment_id=equipment_id,
            equipment_type="extinguisher",
            items=[{"key": "pressure", "result": "ok"}],
            result="pass",
            inspected_at=now,
            feishu_record_id="synthetic-record",
        )
    )
    await db_session.execute(
        log.insert().values(
            id=log_id,
            equipment_id=equipment_id,
            milestone_days=7,
            notified_at=now,
        )
    )
    await connection.run_sync(run_revision, module, "upgrade")
    await connection.run_sync(run_revision, module, "downgrade")
    assert (
        await db_session.scalar(sa.select(equipment.c.base_url))
        == "https://example.test/base"
    )
    assert await db_session.scalar(
        sa.select(settings.c.fire_expiry_notify_milestones)
    ) == [30, 7]
    assert (
        await db_session.scalar(sa.select(settings.c.fire_expiry_notify_enabled))
        is True
    )
    assert (
        await db_session.scalar(sa.select(page.c.writeback_table_id))
        == "synthetic-table"
    )
    assert await db_session.scalar(sa.select(hazard.c.responsible_unit)) == "测试车间"
    assert await db_session.scalar(sa.select(fire.c.fields)) == {"marker": "keep"}
    assert (
        await db_session.scalar(sa.select(inspection.c.feishu_record_id))
        == "synthetic-record"
    )
    assert await db_session.scalar(sa.select(log.c.id)) == log_id
    for name in BASE_TABLES:
        table = await reflect(db_session, schema, name)
        assert await db_session.scalar(sa.select(table.c.marker)) == "keep-existing"

    def inspect_contract(conn: Connection) -> None:
        inspector = sa.inspect(conn)
        indexes = inspector.get_indexes("fire_equipment", schema=schema)
        unique = next(i for i in indexes if i["name"].startswith("uq_"))
        assert unique["unique"] is True
        assert unique["column_names"] == ["table_id", "record_id"]
        assert "is_deleted" in str(unique["dialect_options"]["postgresql_where"])
        constraints = inspector.get_unique_constraints(
            "fire_expiry_notification_log", schema=schema
        )
        assert any(
            c["column_names"] == ["equipment_id", "milestone_days"] for c in constraints
        )
        foreign_keys = inspector.get_foreign_keys(
            "fire_inspection_records", schema=schema
        )
        assert any(f["referred_table"] == "fire_equipment" for f in foreign_keys)

    await connection.run_sync(inspect_contract)


@pytest.mark.asyncio
async def test_partial_later_columns_and_indexes_are_repaired(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = await base_schema(db_session, monkeypatch, module)
    connection = await db_session.connection()
    await connection.run_sync(run_revision, module, "upgrade")

    def remove_later_objects(conn: Connection) -> None:
        with Operations.context(MigrationContext.configure(conn)):
            op.drop_column("fire_equipment", "expiry_date", schema=schema)
            op.drop_column("fire_inspection_records", "feishu_record_id", schema=schema)
            op.drop_index(
                "ix_safety_fire_inspections_inspected_at",
                table_name="fire_inspection_records",
                schema=schema,
            )
            op.drop_table("fire_expiry_notification_log", schema=schema)

    await connection.run_sync(remove_later_objects)
    await connection.run_sync(run_revision, module, "upgrade")
    fire = await reflect(db_session, schema, "fire_equipment")
    inspection = await reflect(db_session, schema, "fire_inspection_records")
    assert isinstance(fire.c.expiry_date.type, sa.Date)
    assert isinstance(inspection.c.feishu_record_id.type, sa.String)
    assert (
        await reflect(db_session, schema, "fire_expiry_notification_log")
    ).c.id.primary_key
    indexes = await connection.run_sync(
        lambda c: sa.inspect(c).get_indexes("fire_inspection_records", schema=schema)
    )
    assert any(i["name"] == "ix_safety_fire_inspections_inspected_at" for i in indexes)


@pytest.mark.asyncio
@pytest.mark.parametrize("omit", BASE_TABLES)
async def test_missing_base_stops_before_any_repair(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    omit: str,
) -> None:
    module = migration()
    schema = await base_schema(db_session, monkeypatch, module, omit=omit)
    connection = await db_session.connection()
    with pytest.raises(RuntimeError, match="is missing"):
        await connection.run_sync(run_revision, module, "upgrade")
    assert not await connection.run_sync(
        lambda c: sa.inspect(c).has_table("fire_equipment", schema=schema)
    )
    for name in BASE_TABLES:
        if name != omit:
            table = await reflect(db_session, schema, name)
            assert set(table.c.keys()) == {"id", "marker"}


@pytest.mark.asyncio
async def test_unknown_partial_fire_table_stops_before_any_repair(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = migration()
    schema = await base_schema(db_session, monkeypatch, module)
    connection = await db_session.connection()
    partial = sa.Table(
        "fire_equipment",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        schema=schema,
    )
    await connection.run_sync(partial.create)
    with pytest.raises(RuntimeError, match="is incomplete"):
        await connection.run_sync(run_revision, module, "upgrade")
    table = await reflect(db_session, schema, "inspection_feishu_config")
    assert set(table.c.keys()) == {"id", "marker"}
