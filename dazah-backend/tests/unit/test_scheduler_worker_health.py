from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.platform.scheduler import worker_health


@pytest.mark.asyncio
async def test_worker_healthcheck_reports_failed_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready_file = tmp_path / "worker-ready"
    monkeypatch.setattr(worker_health, "READY_FILE", ready_file)
    with pytest.raises(FileNotFoundError):
        await worker_health.healthcheck()

    ready_file.write_text("17")
    pids = []
    monkeypatch.setattr(
        worker_health, "os", SimpleNamespace(kill=lambda pid, _: pids.append(pid))
    )
    execute = AsyncMock()
    redis = SimpleNamespace(ping=AsyncMock(return_value=True), aclose=AsyncMock())
    dispose = AsyncMock()

    @asynccontextmanager
    async def probe_session(_engine):
        yield SimpleNamespace(execute=execute)

    monkeypatch.setattr(worker_health, "AsyncSession", probe_session)
    monkeypatch.setattr(worker_health, "redis_client", redis)
    monkeypatch.setattr(worker_health, "engine", SimpleNamespace(dispose=dispose))
    await worker_health.healthcheck()
    assert pids == [17]
    assert str(execute.call_args.args[0]) == "SELECT 1"
    redis.ping.return_value = False
    with pytest.raises(RuntimeError, match="Redis ping failed"):
        await worker_health.healthcheck()
    assert redis.aclose.await_count == dispose.await_count == 2
