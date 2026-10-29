"""批次进度查询必须始终使用绑定参数，禁止把批号拼进 SQL。"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.batch_progress_api import (
    batch_progress,
    build_batch_progress_query,
)

INJECTION_PAYLOAD = (
    "%' UNION SELECT email || ':' || password_hash, 'x' FROM identity.users --"
)


def test_build_query_binds_batch_no_instead_of_interpolating() -> None:
    sql, params = build_batch_progress_query(INJECTION_PAYLOAD)

    assert INJECTION_PAYLOAD not in sql
    assert "ILIKE :batch_no" in sql
    assert params == {"batch_no": f"%{INJECTION_PAYLOAD}%"}


def test_build_query_without_filter_keeps_workshop_parameter_only() -> None:
    sql, params = build_batch_progress_query(None)

    assert "ILIKE" not in sql
    assert params == {}


class _FakeResult:
    def __init__(self, *, rows: list[tuple[str, str]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[tuple[str, str]]:
        return self._rows

    def fetchone(self) -> tuple[int, float] | None:
        return (0, 0)


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((str(statement), dict(params)))
        if len(self.calls) == 1:
            return _FakeResult(rows=[("FA-001", "receive")])
        return _FakeResult()


@pytest.mark.anyio
async def test_endpoint_passes_batch_no_as_bound_parameter() -> None:
    session = _RecordingSession()

    await batch_progress(
        s=INJECTION_PAYLOAD,
        workshop="203",
        session=cast(AsyncSession, session),
    )

    sql, params = session.calls[0]
    assert INJECTION_PAYLOAD not in sql
    assert params["batch_no"] == f"%{INJECTION_PAYLOAD}%"
    assert params["ws"] == "203"
