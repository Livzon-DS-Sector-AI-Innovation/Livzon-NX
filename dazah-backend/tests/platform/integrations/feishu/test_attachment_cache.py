"""飞书附件两级缓存（AttachmentCache）单元测试。

覆盖：命中/未命中、TTL 过期、并发穿透、磁盘持久化、关闭开关与降级。
"""

from __future__ import annotations

import asyncio

import pytest

from app.platform.integrations.feishu.attachment_cache import AttachmentCache


@pytest.fixture
def cache(tmp_path) -> AttachmentCache:
    return AttachmentCache(
        enabled=True,
        cache_dir=str(tmp_path),
        max_memory_mb=2,
        max_disk_mb=5,
        ttl_seconds=3600,
    )


async def _fetch_ok() -> tuple[bytes, str, str]:
    return b"image-bytes", "image/jpeg", "photo.jpg"


async def test_miss_then_hit(cache: AttachmentCache) -> None:
    first = await cache.get_or_fetch("entity", "rec_1", "token_1", _fetch_ok)
    assert first == (b"image-bytes", "image/jpeg", "photo.jpg")
    # 命中：不再调用 fetcher
    calls: list[str] = []

    async def fetcher() -> tuple[bytes, str, str]:
        calls.append("fetch")
        return b"other", "image/png", "a.png"

    second = await cache.get_or_fetch("entity", "rec_1", "token_1", fetcher)
    assert second == (b"image-bytes", "image/jpeg", "photo.jpg")
    assert calls == []


async def test_key_isolation(cache: AttachmentCache) -> None:
    # 不同记录 / 不同附件互不干扰
    await cache.get_or_fetch("entity", "rec_1", "token_1", _fetch_ok)
    calls: list[str] = []

    async def fetcher() -> tuple[bytes, str, str]:
        calls.append("fetch")
        return b"x", "image/png", "x.png"

    assert await cache.get_or_fetch("entity", "rec_1", "token_2", fetcher) == (
        b"x",
        "image/png",
        "x.png",
    )
    assert await cache.get_or_fetch("entity", "rec_2", "token_1", fetcher) == (
        b"x",
        "image/png",
        "x.png",
    )
    assert len(calls) == 2


async def test_ttl_expiry(tmp_path) -> None:
    # TTL=0：写入后立即过期，二次请求必须重新回源
    cache = AttachmentCache(
        enabled=True,
        cache_dir=str(tmp_path),
        max_memory_mb=2,
        max_disk_mb=5,
        ttl_seconds=0,
    )
    calls: list[str] = []

    async def fetcher() -> tuple[bytes, str, str]:
        calls.append("fetch")
        return b"x", "image/png", "x.png"

    await cache.get_or_fetch("entity", "rec_1", "token_1", fetcher)
    await cache.get_or_fetch("entity", "rec_1", "token_1", fetcher)
    assert calls == ["fetch", "fetch"]


async def test_concurrent_penetration_single_fetch(cache: AttachmentCache) -> None:
    calls = 0

    async def slow_fetcher() -> tuple[bytes, str, str]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return b"data", "image/jpeg", "f.jpg"

    results = await asyncio.gather(
        cache.get_or_fetch("entity", "rec_1", "token_1", slow_fetcher),
        cache.get_or_fetch("entity", "rec_1", "token_1", slow_fetcher),
        cache.get_or_fetch("entity", "rec_1", "token_1", slow_fetcher),
    )
    assert all(r == (b"data", "image/jpeg", "f.jpg") for r in results)
    assert calls == 1


async def test_disk_persistence_across_instances(tmp_path) -> None:
    cache1 = AttachmentCache(
        enabled=True,
        cache_dir=str(tmp_path),
        max_memory_mb=2,
        max_disk_mb=5,
        ttl_seconds=3600,
    )
    await cache1.set("entity", "rec_1", "token_1", b"bytes", "image/jpeg", "a.jpg")
    cache2 = AttachmentCache(
        enabled=True,
        cache_dir=str(tmp_path),
        max_memory_mb=2,
        max_disk_mb=5,
        ttl_seconds=3600,
    )
    calls: list[str] = []

    async def fetcher() -> tuple[bytes, str, str]:
        calls.append("fetch")
        return b"other", "image/png", "o.png"

    result = await cache2.get_or_fetch("entity", "rec_1", "token_1", fetcher)
    assert result == (b"bytes", "image/jpeg", "a.jpg")
    assert calls == []


async def test_disabled_bypasses_cache(tmp_path) -> None:
    cache = AttachmentCache(
        enabled=False,
        cache_dir=str(tmp_path),
        max_memory_mb=2,
        max_disk_mb=5,
        ttl_seconds=3600,
    )
    calls = 0

    async def fetcher() -> tuple[bytes, str, str]:
        nonlocal calls
        calls += 1
        return b"x", "image/png", "x.png"

    await cache.get_or_fetch("entity", "rec_1", "token_1", fetcher)
    await cache.get_or_fetch("entity", "rec_1", "token_1", fetcher)
    assert calls == 2
    assert cache.stats()["hits"] == 0


async def test_fetcher_none_not_cached(cache: AttachmentCache) -> None:
    async def failing() -> tuple[bytes, str, str] | None:
        return None

    assert await cache.get_or_fetch("entity", "rec_1", "token_1", failing) is None
    # 未缓存：再次调用仍走 fetcher
    calls = 0

    async def fetcher() -> tuple[bytes, str, str]:
        nonlocal calls
        calls += 1
        return b"x", "image/png", "x.png"

    assert await cache.get_or_fetch("entity", "rec_1", "token_1", fetcher) == (
        b"x",
        "image/png",
        "x.png",
    )
    assert calls == 1


async def test_memory_lru_eviction(tmp_path) -> None:
    cache = AttachmentCache(
        enabled=True,
        cache_dir=str(tmp_path),
        max_memory_mb=1,
        max_disk_mb=10,
        ttl_seconds=3600,
    )
    big = b"a" * (600 * 1024)  # 600KB 单条，两条超 1MB 内存上限则只留最近一条

    async def fetcher_a() -> tuple[bytes, str, str]:
        return big, "image/jpeg", "a.jpg"

    async def fetcher_b() -> tuple[bytes, str, str]:
        return big, "image/jpeg", "b.jpg"

    await cache.get_or_fetch("entity", "rec_1", "t1", fetcher_a)
    await cache.get_or_fetch("entity", "rec_2", "t2", fetcher_b)
    assert cache.stats()["memory_entries"] == 1
    assert cache.stats()["memory_bytes"] <= 1 * 1024 * 1024
