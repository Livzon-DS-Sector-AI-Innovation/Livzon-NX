from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import ProgrammingError

from app.core import schema_guard


@pytest.mark.asyncio
async def test_schema_guard_accepts_current_database(monkeypatch) -> None:
    monkeypatch.setattr(schema_guard, "expected_alembic_heads", lambda: {"head-2"})
    result = MagicMock()
    result.scalars.return_value.all.return_value = ["head-2"]
    session = AsyncMock()
    session.execute.return_value = result

    await schema_guard.assert_database_schema_current(session)


@pytest.mark.asyncio
async def test_schema_guard_explains_required_migration(monkeypatch) -> None:
    monkeypatch.setattr(schema_guard, "expected_alembic_heads", lambda: {"head-2"})
    result = MagicMock()
    result.scalars.return_value.all.return_value = ["head-1"]
    session = AsyncMock()
    session.execute.return_value = result

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        await schema_guard.assert_database_schema_current(session)


@pytest.mark.asyncio
async def test_schema_guard_explains_uninitialized_database() -> None:
    session = AsyncMock()
    session.execute.side_effect = ProgrammingError("statement", {}, Exception())

    with pytest.raises(RuntimeError, match="Alembic 初始化"):
        await schema_guard.assert_database_schema_current(session)
