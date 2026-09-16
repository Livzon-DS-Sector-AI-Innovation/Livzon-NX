from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.platform.identity.page_permission_expiry import (
    _already_recorded,
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
