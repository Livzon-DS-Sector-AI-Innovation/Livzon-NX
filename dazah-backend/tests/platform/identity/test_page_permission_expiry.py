from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.platform.identity import page_permission_expiry
from app.platform.identity.page_permission_expiry import (
    _already_recorded,
    scan_sensitive_page_permission_expiry,
    sensitive_page_permission_expiry_task,
)
from app.platform.scheduler import ScheduleStrategy


@pytest.mark.asyncio
async def test_expiry_event_deduplicates_the_same_grant_version() -> None:
    expiry = datetime(2026, 10, 1, tzinfo=UTC)
    result = SimpleNamespace(
        scalars=lambda: [
            {"expires_at": expiry.isoformat()},
            {"expires_at": datetime(2026, 9, 1, tzinfo=UTC).isoformat()},
        ]
    )
    db = AsyncMock()
    db.execute.return_value = result

    assert await _already_recorded(
        db,
        action="page_permission_expiry_notice",
        resource_id=uuid4(),
        expiry=expiry,
    )


def test_sensitive_permission_expiry_scan_runs_daily() -> None:
    assert sensitive_page_permission_expiry_task.schedule.strategy == (
        ScheduleStrategy.FIXED_TIME
    )
    assert sensitive_page_permission_expiry_task.schedule.time_of_day == "09:00"


@pytest.mark.asyncio
async def test_upcoming_expiry_is_recorded_without_notification_credentials(
    monkeypatch,
) -> None:
    expiry = datetime(2026, 10, 1, tzinfo=UTC)
    grant = SimpleNamespace(
        id=uuid4(), role_id=uuid4(), page_key="quality:documents",
        sensitive_actions=["delete"], sensitive_actions_expires_at=expiry,
    )
    db = SimpleNamespace(execute=AsyncMock(), add=Mock(), commit=AsyncMock())
    db.execute.side_effect = [
        SimpleNamespace(scalars=lambda: [grant]),
        SimpleNamespace(scalars=lambda: []),
        SimpleNamespace(
            scalars=lambda: [SimpleNamespace(id=grant.role_id, name="质量角色")]
        ),
        SimpleNamespace(scalars=lambda: []),
        SimpleNamespace(scalars=lambda: []),
    ]

    @asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(page_permission_expiry, "async_session_factory", session)
    monkeypatch.setattr(
        page_permission_expiry, "datetime",
        SimpleNamespace(now=lambda _: datetime(2026, 9, 16, tzinfo=UTC)),
    )
    await scan_sensitive_page_permission_expiry()

    event = db.add.call_args.args[0]
    assert event.action == "page_permission_expiry_notice"
    assert event.resource_id == grant.id
    assert event.new_value["expires_at"] == expiry.isoformat()
    assert event.new_value["recipient_count"] == 0
    db.commit.assert_awaited_once()
