"""Database safety helpers for pytest.

Tests in this project may commit fixture setup and cleanup statements. Refuse to
run them against a database that does not look like a dedicated test database.
"""

from __future__ import annotations

import os
from typing import Protocol
from urllib.parse import urlsplit

import pytest


class _SettingsWithDatabaseUrl(Protocol):
    DATABASE_URL: str


_SAFE_DATABASE_NAME_MARKERS = ("test", "testing", "pytest")


def get_pytest_database_url(settings: _SettingsWithDatabaseUrl) -> str:
    """Return the database URL pytest is allowed to use."""
    database_url = os.getenv("TEST_DATABASE_URL") or settings.DATABASE_URL
    _assert_safe_pytest_database_url(database_url)
    return database_url


def _assert_safe_pytest_database_url(database_url: str) -> None:
    if os.getenv("PYTEST_ALLOW_UNSAFE_DATABASE_URL") == "1":
        return

    database_name = _extract_database_name(database_url)
    normalized_name = database_name.lower()
    if any(marker in normalized_name for marker in _SAFE_DATABASE_NAME_MARKERS):
        return

    pytest.exit(
        "Refusing to run pytest against a non-test database. "
        f"Database name is {database_name!r}. Set TEST_DATABASE_URL to a "
        "dedicated test database such as postgresql+asyncpg://.../dazah_test, "
        "or set PYTEST_ALLOW_UNSAFE_DATABASE_URL=1 only for an intentional "
        "one-off run.",
        returncode=2,
    )


def _extract_database_name(database_url: str) -> str:
    parsed = urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    database_name = parsed.path.rsplit("/", 1)[-1]
    return database_name or "<unknown>"
