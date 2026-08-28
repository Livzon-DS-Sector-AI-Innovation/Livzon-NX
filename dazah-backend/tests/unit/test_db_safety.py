from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import pytest
from _pytest.outcomes import Exit

from tests.db_safety import get_pytest_database_url

SimpleNamespace: Any = _SimpleNamespace


def test_pytest_uses_dedicated_url_from_settings(monkeypatch: Any) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    settings: Any = SimpleNamespace(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/dazah",
        TEST_DATABASE_URL=(
            "postgresql+asyncpg://postgres:postgres@localhost:5432/dazah_test"
        ),
    )

    assert get_pytest_database_url(settings).endswith("/dazah_test")


def test_pytest_rejects_shared_database_without_override(monkeypatch: Any) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("PYTEST_ALLOW_UNSAFE_DATABASE_URL", raising=False)
    settings: Any = SimpleNamespace(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/dazah",
        TEST_DATABASE_URL=None,
    )

    with pytest.raises(Exit):
        get_pytest_database_url(settings)
