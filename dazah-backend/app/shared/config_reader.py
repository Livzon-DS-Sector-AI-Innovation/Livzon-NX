"""Runtime configuration reader — reads module-level settings from database
core.module_settings.
Fallback to environment variables if DB is unavailable or table doesn't exist.
"""

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_module_setting(module: str, key: str, default: str = "") -> str:
    """Read a module setting from DB. Falls back to os.getenv(key, default)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT value FROM core.module_settings W"
                    "HERE module = :module AND key = :key AND"
                    " is_deleted = false"
                ),
                {"module": module, "key": key},
            )
            row = result.fetchone()
            if row and isinstance(row[0], str):
                return row[0]
    except Exception as exc:
        logger.warning("DB read failed for %s.%s: %s", module, key, exc)

    return os.getenv(key, default)


async def get_module_setting_bool(module: str, key: str, default: bool = False) -> bool:
    val = await get_module_setting(module, key, "true" if default else "false")
    return val.lower() in ("true", "1", "yes")


async def set_module_setting(
    session: AsyncSession, module: str, key: str, value: str
) -> None:
    """Write a module setting to DB. Creates/updates the row."""
    from sqlalchemy import text

    await session.execute(
        text(
            """
            INSERT INTO core.module_settings (module, key, value, updated_at)
            VALUES (:module, :key, :value, NOW())
            ON CONFLICT (module, key) WHERE is_deleted = false
            DO UPDATE SET value = :value, updated_at = NOW()
            """
        ),
        {"module": module, "key": key, "value": value},
    )
    await session.commit()
