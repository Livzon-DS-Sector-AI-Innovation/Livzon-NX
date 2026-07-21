from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.validation_record import ValidationRecord

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_EXECUTION_TABLES = (
    "quality.equipment_qualification_records",
    "quality.process_validation_records",
    "quality.cleaning_validation_records",
    "quality.other_validation_records",
)


def _build_alembic_config() -> Config:
    config = Config(str(_PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    return config


@lru_cache(maxsize=1)
def ensure_validation_records_migrated() -> None:
    command.upgrade(_build_alembic_config(), "head")


async def reset_validation_records_table(db_session: AsyncSession) -> None:
    ensure_validation_records_migrated()
    for table_name in _EXECUTION_TABLES:
        await db_session.execute(text(f"DELETE FROM {table_name}"))
    await db_session.execute(ValidationRecord.__table__.delete())
    await db_session.commit()


async def assert_validation_migration_state(db_session: AsyncSession) -> None:
    table_name = (
        await db_session.execute(text("SELECT to_regclass('quality.validation_records')"))
    ).scalar_one()
    execution_tables = [
        (
            await db_session.execute(text(f"SELECT to_regclass('{execution_table}')"))
        ).scalar_one()
        for execution_table in _EXECUTION_TABLES
    ]
    revision_count = (
        await db_session.execute(text("SELECT COUNT(*) FROM alembic_version"))
    ).scalar_one()

    assert table_name == "quality.validation_records"
    assert execution_tables == list(_EXECUTION_TABLES)
    assert revision_count >= 1
