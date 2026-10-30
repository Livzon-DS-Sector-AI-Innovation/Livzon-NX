"""事件驱动的镜像即时刷新测试：去抖、单页串行 rerun、撞锁退避、绑定匹配。"""

import asyncio
import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.safety.service import page_mirror_refresh as pmr


@contextlib.asynccontextmanager
async def _fake_factory():
    yield SimpleNamespace()


def _install(monkeypatch: pytest.MonkeyPatch, sync_mock: AsyncMock) -> None:
    monkeypatch.setattr(pmr, "async_session_factory", _fake_factory)
    monkeypatch.setattr(pmr, "sync_page_table_mirror", sync_mock)
    monkeypatch.setattr(pmr, "sync_special_operation_ledger", AsyncMock())
    monkeypatch.setattr(pmr, "DEBOUNCE_SECONDS", 0.05)
    monkeypatch.setattr(pmr, "RETRY_LOCK_WAIT_SECONDS", 0.05)
    for page_key in list(pmr._task):
        pmr._task[page_key].cancel()
    pmr._task.clear()
    pmr._state.clear()
    pmr._rerun.clear()


async def _drain() -> None:
    for _ in range(20):
        await asyncio.sleep(0.05)
        if not any(not t.done() for t in pmr._task.values()):
            return


@pytest.mark.asyncio
async def test_debounce_merges_burst_events(monkeypatch) -> None:
    """短时间多次变更合并为一次同步。"""
    sync_mock = AsyncMock(return_value=1)
    _install(monkeypatch, sync_mock)

    for _ in range(5):
        pmr.schedule_page_mirror_refresh("safety:ops-safety:feeding-inspection")
        await asyncio.sleep(0.01)

    await _drain()
    assert sync_mock.await_count == 1


@pytest.mark.asyncio
async def test_syncing_page_reruns_for_new_events(monkeypatch) -> None:
    """同步进行中收到新事件：本轮完成后自动补跑一轮。"""
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_sync(session, page_key):
        started.set()
        await release.wait()
        return 1

    sync_mock = AsyncMock(side_effect=_slow_sync)
    _install(monkeypatch, sync_mock)

    pmr.schedule_page_mirror_refresh("safety:ops-safety:feeding-inspection")
    await asyncio.wait_for(started.wait(), timeout=2)
    # 同步进行中再触发两次 → 合并为一次 rerun
    pmr.schedule_page_mirror_refresh("safety:ops-safety:feeding-inspection")
    pmr.schedule_page_mirror_refresh("safety:ops-safety:feeding-inspection")
    release.set()
    await _drain()

    assert sync_mock.await_count == 2  # 首轮 + rerun 一轮


@pytest.mark.asyncio
async def test_lock_conflict_retries_then_succeeds(monkeypatch) -> None:
    """撞上定时同步的锁（409）时退避重试，成功后正常结束。"""
    call_results = [
        AppException(message="该页面的镜像同步正在执行，请稍后再试", status_code=409),
        AppException(message="该页面的镜像同步正在执行，请稍后再试", status_code=409),
        3,
    ]

    async def _flaky_sync(session, page_key):
        result = call_results.pop(0)
        if isinstance(result, AppException):
            raise result
        return result

    sync_mock = AsyncMock(side_effect=_flaky_sync)
    _install(monkeypatch, sync_mock)

    pmr.schedule_page_mirror_refresh("safety:ops-safety:feeding-inspection")
    await _drain()

    assert sync_mock.await_count == 3


@pytest.mark.asyncio
async def test_special_danger_page_triggers_transcription(monkeypatch) -> None:
    """特殊危险作业页同步成功后自动转录台账。"""
    sync_mock = AsyncMock(return_value=1)
    _install(monkeypatch, sync_mock)
    transcribe = pmr.sync_special_operation_ledger

    pmr.schedule_page_mirror_refresh("safety:ops-safety:special-danger-work")
    await _drain()

    assert sync_mock.await_count == 1
    assert transcribe.await_count == 1

    # 其它页面不触发转录
    pmr.schedule_page_mirror_refresh("safety:ops-safety:feeding-inspection")
    await _drain()
    assert transcribe.await_count == 1


@pytest.mark.asyncio
async def test_handler_schedules_bound_pages(monkeypatch) -> None:
    """事件处理器按 (app_token, table_id) 匹配镜像页绑定并调度刷新。"""
    scheduled: list[str] = []

    @contextlib.asynccontextmanager
    async def _fake_factory():
        yield SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    scalars=lambda: SimpleNamespace(
                        all=lambda: ["safety:ops-safety:feeding-inspection"]
                    )
                )
            )
        )

    import app.core.database as core_database
    import app.modules.safety.service.page_mirror_refresh as refresh_module

    monkeypatch.setattr(core_database, "async_session_factory", _fake_factory)
    monkeypatch.setattr(
        refresh_module,
        "schedule_page_mirror_refresh",
        lambda page_key: scheduled.append(page_key),
    )

    from app.modules.safety.feishu.bitable_handler import (
        handle_mirror_page_record_changed,
    )

    await handle_mirror_page_record_changed(
        {"file_token": "bascnOps", "table_id": "tblFeed"}
    )

    assert scheduled == ["safety:ops-safety:feeding-inspection"]
