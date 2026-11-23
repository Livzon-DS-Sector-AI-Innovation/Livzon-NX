"""附件缓存预热任务单元测试。

覆盖：cron 转换、cells 附件 token 提取、预热关闭跳过、Generator 的
find_due 开关行为（避免真实预热连接飞书/数据库）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings
from app.modules.quality.scheduled import AttachmentCacheWarmupGenerator
from app.modules.quality.service import feishu_attachment_warmup as warmup_mod
from app.modules.quality.service.feishu_attachment_warmup import (
    _cron_to_time_of_day,
    _extract_file_tokens,
    warmup_attachment_cache,
)


def test_cron_to_time_of_day() -> None:
    assert _cron_to_time_of_day("0 2 * * *") == "02:00"
    assert _cron_to_time_of_day("30 9 * * *") == "09:30"
    assert _cron_to_time_of_day("5 23 * * *") == "23:05"
    assert _cron_to_time_of_day("bad") == "02:00"


def test_extract_file_tokens_nested() -> None:
    cells = {
        "批号": "B-1",
        "附件": [
            {"name": "a.jpg", "file_token": "tok-a"},
            {"name": "b.pdf", "file_token": "tok-b"},
        ],
        "嵌套": {"内层": [{"file_token": "tok-c"}]},
    }
    tokens = _extract_file_tokens(cells)
    assert sorted(tokens) == ["tok-a", "tok-b", "tok-c"]


def test_extract_file_tokens_ignores_plain_values() -> None:
    assert _extract_file_tokens({"批号": "B-1", "数量": 3, "备注": None}) == []


async def test_warmup_disabled_returns_skipped() -> None:
    with patch.object(
        get_settings(), "QUALITY_ATTACHMENT_WARMUP_ENABLED", False
    ):
        result = await warmup_attachment_cache()
    assert result["enabled"] is False
    assert result["collected"] == 0


async def test_warmup_generator_find_due_respects_enabled() -> None:
    gen = AttachmentCacheWarmupGenerator()
    with patch.object(
        get_settings(), "QUALITY_ATTACHMENT_WARMUP_ENABLED", True
    ):
        due = await gen.find_due(None)
    assert due == [True]
    with patch.object(
        get_settings(), "QUALITY_ATTACHMENT_WARMUP_ENABLED", False
    ):
        due = await gen.find_due(None)
    assert due == []


async def test_warmup_execute_calls_service() -> None:
    gen = AttachmentCacheWarmupGenerator()
    with patch(
        "app.modules.quality.scheduled.warmup_attachment_cache",
        AsyncMock(return_value={"enabled": True, "warmed": 0}),
    ) as mock_warm:
        await gen.execute_one(None, True)
    mock_warm.assert_awaited_once()


@pytest.fixture(autouse=True)
def _mock_cache_disk(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(warmup_mod, "get_attachment_cache", lambda: MagicMock(
        enabled=True, prepare_disk=check,
    ), raising=False)
    return check


async def test_warmup_skips_unwritable_disk_before_querying(
    monkeypatch: pytest.MonkeyPatch, _mock_cache_disk: AsyncMock,
) -> None:
    _mock_cache_disk.return_value = False
    session = MagicMock(side_effect=AssertionError("disk unavailable"))
    monkeypatch.setattr(warmup_mod, "async_session_factory", session)
    result = await warmup_attachment_cache()
    assert result["collected"] == 0
    assert result["warmed"] == 0
    session.assert_not_called()


def _fake_session_for_rows(rows):
    exec_result = MagicMock(close=AsyncMock())
    exec_result.__aiter__.return_value = iter(rows)
    session = AsyncMock()
    session.stream = AsyncMock(return_value=exec_result)
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return lambda: ctx


async def test_warmup_respects_total_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """总预算超时即提前结束并置 budget_hit，保留已预热统计。"""
    monkeypatch.setattr(warmup_mod, "_TOTAL_BUDGET_SECONDS", 0.05)
    monkeypatch.setattr(warmup_mod, "_SINGLE_WARMUP_TIMEOUT_SECONDS", 10)
    rows = [
        ("rec1", {"附件": [{"file_token": "t1"}]}, "qc_solid_ys008"),
        ("rec2", {"附件": [{"file_token": "t2"}]}, "qc_solid_ys008"),
    ]
    monkeypatch.setattr(
        warmup_mod, "async_session_factory", _fake_session_for_rows(rows)
    )

    async def _slow(*_args, **_kwargs):
        await asyncio.sleep(0.5)
        return (b"thumb", "image/jpeg", "a.jpg")

    monkeypatch.setattr(warmup_mod, "get_attachment_thumbnail", _slow)
    with patch.object(get_settings(), "QUALITY_ATTACHMENT_WARMUP_ENABLED", True):
        result = await warmup_attachment_cache()
    assert result["collected"] == 2
    assert result["budget_hit"] is True


async def test_warmup_single_timeout_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """单条回源超 _SINGLE_WARMUP_TIMEOUT_SECONDS 计入 timed_out，不阻塞其它。"""
    monkeypatch.setattr(warmup_mod, "_SINGLE_WARMUP_TIMEOUT_SECONDS", 0.02)
    monkeypatch.setattr(warmup_mod, "_TOTAL_BUDGET_SECONDS", 5)
    rows = [
        ("rec1", {"附件": [{"file_token": "slow"}]}, "qc_solid_ys008"),
        ("rec2", {"附件": [{"file_token": "fast"}]}, "qc_solid_ys008"),
    ]
    monkeypatch.setattr(
        warmup_mod, "async_session_factory", _fake_session_for_rows(rows)
    )

    async def _maybe_slow(_db, _entity, _record, file_token, *, disk_only):
        assert disk_only is True
        if file_token == "slow":
            await asyncio.sleep(1)
            return (b"", "image/jpeg", "x")
        return (b"ok", "image/jpeg", "x")

    monkeypatch.setattr(warmup_mod, "get_attachment_thumbnail", _maybe_slow)
    with patch.object(get_settings(), "QUALITY_ATTACHMENT_WARMUP_ENABLED", True):
        result = await warmup_attachment_cache()
    assert result["timed_out"] >= 1
    assert result["budget_hit"] is False


async def test_warmup_stops_stream_at_unique_target_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def rows():
        yield "r1", {"附件": [{"file_token": "f1"}, {"file_token": "f1"}]}, "entity"
        yield "r2", {"附件": [{"file_token": "f2"}]}, "entity"
        pytest.fail("镜像扫描应在达到附件上限时停止")

    result = MagicMock(close=AsyncMock())
    result.__aiter__.side_effect = rows
    session = MagicMock(stream=AsyncMock(return_value=result))
    ctx = MagicMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock())
    monkeypatch.setattr(warmup_mod, "async_session_factory", lambda: ctx)
    thumb = AsyncMock(side_effect=[None, (b"thumb", "image/jpeg", "a.jpg")])
    monkeypatch.setattr(warmup_mod, "get_attachment_thumbnail", thumb)

    stats = await warmup_attachment_cache(max_tokens=2)

    assert stats["collected"] == 2
    assert stats["warmed"] == 1
    assert stats["skipped"] == 1
    assert session.stream.call_args.args[0].get_execution_options()["yield_per"] == 128
    result.close.assert_awaited_once()
    assert [call.kwargs for call in thumb.await_args_list] == [{"disk_only": True}] * 2
