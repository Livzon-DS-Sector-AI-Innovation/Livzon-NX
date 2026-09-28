"""submit_job 失败分支的可观测性回归测试。

生产曾出现 Job 失败日志与任务状态只剩「失败: 」空文案（TimeoutError 等
异常 str 为空），且 logger.error 不带堆栈无法定位根因。回归锁定：
- 失败状态文案对空消息异常回退异常类名；
- 失败日志通过 logger.exception 携带完整堆栈；
- 心跳键在任务结束后清理，成功路径状态与结果完整。
"""

from __future__ import annotations

import asyncio
import logging

import pytest

import app.core.jobs as jobs


class _FakeCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture
def fake_cache(monkeypatch: pytest.MonkeyPatch) -> _FakeCache:
    cache = _FakeCache()
    monkeypatch.setattr(jobs, "cache_set", cache.set)
    monkeypatch.setattr(jobs, "cache_get", cache.get)
    monkeypatch.setattr(jobs, "cache_delete", cache.delete)
    return cache


async def _wait_terminal(job_id: str) -> dict[str, object]:
    for _ in range(200):
        status = await jobs.get_job_status(job_id)
        if status and status.get("state") != "running":
            return status
        await asyncio.sleep(0.01)
    raise AssertionError("后台任务未在预期时间内进入终态")


async def test_failed_job_reports_exception_class_and_traceback(
    fake_cache: _FakeCache, caplog: pytest.LogCaptureFixture
):
    async def _boom() -> None:
        raise TimeoutError()

    with caplog.at_level(logging.ERROR, logger="app.core.jobs"):
        job_id = await jobs.submit_job(_boom, task_id="test:boom")

    status = await _wait_terminal(job_id)
    assert status["state"] == "failed"
    assert status["progress"] == "失败: TimeoutError"
    assert status["result"] is None
    # 心跳键必须在任务结束后清理，否则 is_job_running 误判孤儿状态
    assert jobs._heartbeat_key(job_id) not in fake_cache.store
    failed_logs = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and "test:boom" in record.getMessage()
    ]
    assert failed_logs, "失败任务必须记录 ERROR 日志"
    assert any(record.exc_info for record in failed_logs), "失败日志必须携带堆栈"


async def test_failed_job_keeps_exception_message_when_present(fake_cache):
    async def _boom() -> None:
        raise RuntimeError("飞书连接超时")

    job_id = await jobs.submit_job(_boom, task_id="test:boom-message")
    status = await _wait_terminal(job_id)
    assert status["progress"] == "失败: 飞书连接超时"


async def test_completed_job_reports_result(fake_cache):
    async def _ok() -> dict[str, int]:
        return {"synced": 3}

    job_id = await jobs.submit_job(_ok, task_id="test:ok")
    status = await _wait_terminal(job_id)
    assert status["state"] == "completed"
    assert status["result"] == {"synced": 3}
    assert jobs._heartbeat_key(job_id) not in fake_cache.store
