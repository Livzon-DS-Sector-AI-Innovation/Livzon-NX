from datetime import UTC, datetime, timedelta, tzinfo
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.platform.integrations.feishu import read_scheduler
from app.platform.scheduler import SchedulerRegistry


def test_quality_mirror_registration_switch_and_rollback() -> None:
    settings = Settings(_env_file=None)
    generator = read_scheduler.QualityFeishuReadDailySyncGenerator

    def registrations() -> tuple[set[str], set[str]]:
        api, worker = SchedulerRegistry(), SchedulerRegistry()
        read_scheduler.register_quality_read_mirror(api, settings, owner="api")
        read_scheduler.register_quality_read_mirror(worker, settings, owner="worker")
        return set(api.generators), set(worker.generators)

    assert registrations() == ({generator.name}, set())
    settings.QUALITY_READ_MIRROR_SCHEDULER = "worker"
    assert registrations() == (set(), {generator.name})
    settings.QUALITY_READ_MIRROR_SCHEDULER = "api"
    assert registrations() == ({generator.name}, set())


@pytest.mark.asyncio
async def test_quality_mirror_scans_shanghai_start_and_utc_rollover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # At 02:00 Shanghai it is still the previous UTC day.
    utc_rollover = datetime(2026, 11, 24, tzinfo=UTC)
    completed = SimpleNamespace(
        id=uuid4(), last_complete_sync_at=utc_rollover - timedelta(hours=8)
    )
    never_synced = SimpleNamespace(id=uuid4(), last_complete_sync_at=None)
    now = utc_rollover - timedelta(hours=6, minutes=1)

    class Clock:
        @staticmethod
        def now(tz: tzinfo) -> datetime:
            return now.astimezone(tz)

    monkeypatch.setattr(read_scheduler, "datetime", Clock)
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [completed, never_synced])
            )
        )
    )
    generator = read_scheduler.QualityFeishuReadDailySyncGenerator()
    assert await generator.find_due(session) == []
    now += timedelta(minutes=1)
    assert await generator.find_due(session) == [str(never_synced.id)]
    now = utc_rollover
    assert await generator.find_due(session) == [
        str(completed.id),
        str(never_synced.id),
    ]
