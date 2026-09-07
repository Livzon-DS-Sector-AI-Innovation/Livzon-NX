"""仓储定时同步任务测试：窗口守卫、全量标志、增量跳过与逐页容错。

scheduled.py 是每日全量对账正确性的全部保障（防止 00:00 后重启误触发、
防止增量与全量同时写库），此处对守卫与标志生命周期做单元级锁定。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.modules.warehouse import scheduled
from app.modules.warehouse.feishu_material_pages import FEISHU_WAREHOUSE_MATERIAL_PAGES


def _cn(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 29, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_full_sync_window_boundaries() -> None:
    """全量窗口为北京时间 [00:00, 06:00)，含 00:00 不含 06:00。"""
    assert scheduled._in_full_sync_window(_cn(0)) is True
    assert scheduled._in_full_sync_window(_cn(5, 59)) is True
    assert scheduled._in_full_sync_window(_cn(6)) is False
    assert scheduled._in_full_sync_window(_cn(23)) is False


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_incremental_skips_while_full_sync_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全量执行期间，增量轮次直接跳过且不创建数据库会话。"""
    monkeypatch.setattr(scheduled, "_full_sync_running", True)
    factory = MagicMock(side_effect=AssertionError("全量执行期间不应创建会话"))
    monkeypatch.setattr(scheduled, "async_session_factory", factory)

    await scheduled._run_warehouse_sync()

    factory.assert_not_called()
    # 增量跳过不得复位全量标志
    assert scheduled._full_sync_running is True


@pytest.mark.asyncio
async def test_full_sync_skips_outside_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """窗口外（如中午重启后 FIXED_TIME 误触发）不执行、不建会话。"""

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object | None = None) -> datetime:  # noqa: ARG003
            return _cn(12)

    monkeypatch.setattr(scheduled, "datetime", _FixedDatetime)
    factory = MagicMock(side_effect=AssertionError("窗口外不应创建会话"))
    monkeypatch.setattr(scheduled, "async_session_factory", factory)

    await scheduled._run_warehouse_full_sync()

    factory.assert_not_called()
    assert scheduled._full_sync_running is False


@pytest.mark.asyncio
async def test_full_sync_runs_in_window_and_resets_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """窗口内执行全量：逐页全量（单页失败不阻断）、标志复位。

    内存安全语义（2C4G 部署 OOM 教训）：每张表独立 session + 每表提交后
    关闭，表间执行 gc.collect() 与缓冲 sleep——禁止回退为单 session 跑
    全部页面（identity map 累积 4 万+ 行会把 app 进程推到 OOM）。
    """
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object | None = None) -> datetime:  # noqa: ARG003
            return _cn(1)

    monkeypatch.setattr(scheduled, "datetime", _FixedDatetime)

    first_key = next(iter(FEISHU_WAREHOUSE_MATERIAL_PAGES))
    total_pages = len(FEISHU_WAREHOUSE_MATERIAL_PAGES)
    sessions: list[_FakeSession] = []
    commits = 0

    class _CountingSession(_FakeSession):
        async def commit(self) -> None:
            nonlocal commits
            commits += 1
            self.committed = True

    def _session_factory() -> _CountingSession:
        session = _CountingSession()
        sessions.append(session)
        return session

    monkeypatch.setattr(scheduled, "async_session_factory", _session_factory)

    calls: list[tuple[str, bool]] = []

    class _FakeService:
        def __init__(self, session: object) -> None:
            pass

        async def sync_material_page_to_local(
            self, page_key: str, *, incremental: bool = True
        ) -> None:
            calls.append((page_key, incremental))
            if page_key == first_key:
                raise RuntimeError("boom")

    monkeypatch.setattr(scheduled, "WarehouseService", _FakeService)

    # mock 缓冲与 gc：断言每表之后都缓冲（47 页 × 3s 真实 sleep 会拖垮测试）
    sleeps: list[float] = []
    gc_calls: list[bool] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(scheduled.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(scheduled.gc, "collect", lambda: gc_calls.append(True))

    await scheduled._run_warehouse_full_sync()

    # 逐页全量、单页失败不阻断
    assert len(calls) == total_pages
    assert all(incremental is False for _, incremental in calls)
    # 每表独立 session、成功页各自 commit（失败页不 commit）
    assert len(sessions) == total_pages
    assert commits == total_pages - 1
    # 每表之后都有 gc 回收 + 缓冲
    assert len(gc_calls) == total_pages
    assert sleeps == [scheduled._FULL_SYNC_TABLE_GAP_SECONDS] * total_pages
    assert scheduled._full_sync_running is False


@pytest.mark.asyncio
async def test_incremental_round_covers_pages_and_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """增量轮次：逐页增量同步 + 库存表同步 + 提交一次。"""
    monkeypatch.setattr(scheduled, "_full_sync_running", False)
    fake_session = _FakeSession()
    monkeypatch.setattr(scheduled, "async_session_factory", lambda: fake_session)

    calls: list[str] = []

    class _FakeService:
        def __init__(self, session: object) -> None:
            pass

        async def sync_material_page_to_local(
            self, page_key: str, *, incremental: bool = True
        ) -> None:
            calls.append(page_key)

        async def sync_inventory_from_feishu(self) -> None:
            calls.append("inventory")

    monkeypatch.setattr(scheduled, "WarehouseService", _FakeService)

    await scheduled._run_warehouse_sync()

    assert calls[0] == next(iter(FEISHU_WAREHOUSE_MATERIAL_PAGES))
    assert calls[-1] == "inventory"
    assert fake_session.committed is True
