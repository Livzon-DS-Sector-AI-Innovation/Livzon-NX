import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core import jobs


@pytest.mark.asyncio
async def test_submit_job_persists_optional_status_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_set = AsyncMock()
    monkeypatch.setattr(jobs, "cache_set", cache_set)
    monkeypatch.setattr(jobs, "cache_delete", AsyncMock())
    created: list[Coroutine[Any, Any, Any]] = []

    class _Task:
        def cancel(self) -> None:
            return None

    def create_task(coro: Coroutine[Any, Any, Any]) -> _Task:
        created.append(coro)
        return _Task()

    monkeypatch.setattr(jobs.asyncio, "create_task", create_task)

    async def work() -> str:
        return "done"

    try:
        job_id = await jobs.submit_job(
            work,
            task_id="job-with-owner",
            status_extra={"owner_id": "user-1"},
        )
    finally:
        for coroutine in created:
            coroutine.close()

    assert job_id == "job-with-owner"
    initial_status = json.loads(cache_set.await_args_list[0].args[1])
    assert initial_status["owner_id"] == "user-1"


@pytest.mark.asyncio
async def test_update_job_progress_ignores_missing_or_finished_jobs_and_updates_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_get = AsyncMock(
        side_effect=[
            None,
            json.dumps({"state": "completed", "progress": "完成"}),
            json.dumps({"state": "running", "progress": "启动中..."}),
        ]
    )
    cache_set = AsyncMock()
    monkeypatch.setattr(jobs, "cache_get", cache_get)
    monkeypatch.setattr(jobs, "cache_set", cache_set)

    await jobs.update_job_progress("missing", "忽略")
    await jobs.update_job_progress("completed", "忽略")
    await jobs.update_job_progress("running", "处理中")

    assert cache_set.await_count == 1
    assert cache_set.await_args.args[0] == "running"
    assert json.loads(cache_set.await_args.args[1])["progress"] == "处理中"


def test_jobs_module_keeps_asyncio_available() -> None:
    assert jobs.asyncio is asyncio
