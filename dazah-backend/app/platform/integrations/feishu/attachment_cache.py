"""飞书附件字节两级缓存（内存 LRU + 磁盘持久化）。

质量模块附件代理下载共用此缓存，避免同一附件反复回源飞书
（每次回源至少 2 次飞书 HTTP：get_record + 下载字节）。

特性：
- 内存 LRU 快速命中 + 磁盘持久化（进程重启后冷数据仍在）；
- TTL 过期自动失效（与飞书临时链接时效对齐，附件更新后自然失效）；
- 缓存键 = 实体 + 记录 + 附件三元组，保留附件归属校验的安全边界；
- 并发穿透控制：同一缓存键同时只有一次回源（per-key asyncio.Lock）；
- 降级：缓存读写异常只记日志返回 None，调用方走原链路，不影响可用性。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

Fetcher = Callable[[], Awaitable[tuple[bytes, str, str] | None]]

# 磁盘超过上限后清理的触发间隔（避免每次写入都全量扫描）
_DISK_EVICT_EVERY = 20
# 清理到上限的 80%，减少频繁触发
_DISK_EVICT_TARGET_RATIO = 0.8


@dataclass(slots=True)
class _MemoryEntry:
    content: bytes
    content_type: str
    filename: str
    expires_at: float  # wall-clock，与磁盘 st_mtime 语义一致


class AttachmentCache:
    """飞书附件字节缓存。仅用于协程上下文（per-key asyncio.Lock）。"""

    def __init__(
        self,
        *,
        enabled: bool,
        cache_dir: str,
        max_memory_mb: int,
        max_disk_mb: int,
        ttl_seconds: int,
    ) -> None:
        self._enabled = enabled
        self._cache_dir = Path(cache_dir)
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._max_disk_bytes = max_disk_mb * 1024 * 1024
        self._ttl_seconds = ttl_seconds
        self._memory: OrderedDict[str, _MemoryEntry] = OrderedDict()
        self._memory_bytes = 0
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = asyncio.Lock()
        self._disk_writes_since_evict = 0
        self._hits = 0
        self._misses = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def _cache_key(
        entity_code: str,
        record_id: str,
        file_token: str,
        key_suffix: str = "",
    ) -> str:
        # 三元组隔离：缓存命中前提是该附件确实属于该记录
        # key_suffix 用于区分同一附件的派生内容（如缩略图尺寸），默认空 = 原图
        return f"{entity_code}\x1f{record_id}\x1f{file_token}\x1f{key_suffix}"

    def _disk_path(self, cache_key: str) -> Path:
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return self._cache_dir / digest[:2] / digest

    def _meta_path(self, cache_key: str) -> Path:
        return self._disk_path(cache_key).with_suffix(".meta")

    @staticmethod
    def _is_expired(expires_at: float) -> bool:
        return expires_at < time.time()

    # ---- 内存层 ----

    def _memory_get(self, cache_key: str) -> _MemoryEntry | None:
        entry = self._memory.get(cache_key)
        if entry is None:
            return None
        if self._is_expired(entry.expires_at):
            self._memory_pop(cache_key)
            return None
        self._memory.move_to_end(cache_key)
        return entry

    def _memory_pop(self, cache_key: str) -> None:
        entry = self._memory.pop(cache_key, None)
        if entry is not None:
            self._memory_bytes -= len(entry.content)

    def _memory_put(self, cache_key: str, entry: _MemoryEntry) -> None:
        old = self._memory.get(cache_key)
        if old is not None:
            self._memory_bytes -= len(old.content)
        self._memory[cache_key] = entry
        self._memory_bytes += len(entry.content)
        while self._memory_bytes > self._max_memory_bytes and self._memory:
            self._memory_pop(next(iter(self._memory)))

    # ---- 磁盘层 ----

    async def _disk_read(self, cache_key: str) -> tuple[bytes, str, str] | None:
        path = self._disk_path(cache_key)
        meta_path = self._meta_path(cache_key)
        try:
            if not await asyncio.to_thread(path.exists):
                return None
            stat = await asyncio.to_thread(path.stat)
            if stat.st_mtime + self._ttl_seconds < time.time():
                await asyncio.to_thread(path.unlink, missing_ok=True)
                await asyncio.to_thread(meta_path.unlink, missing_ok=True)
                return None
            meta = await asyncio.to_thread(self._read_meta, meta_path)
            if meta is None:
                await asyncio.to_thread(path.unlink, missing_ok=True)
                await asyncio.to_thread(meta_path.unlink, missing_ok=True)
                return None
            content = await asyncio.to_thread(path.read_bytes)
            return content, meta["content_type"], meta["filename"]
        except OSError:
            logger.warning("飞书附件磁盘缓存读取失败: %s", path, exc_info=True)
            return None

    async def _disk_write(
        self,
        cache_key: str,
        content: bytes,
        content_type: str,
        filename: str,
    ) -> None:
        path = self._disk_path(cache_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        meta = {"content_type": content_type, "filename": filename}
        await asyncio.to_thread(path.write_bytes, content)
        await asyncio.to_thread(self._write_meta, self._meta_path(cache_key), meta)

    async def _evict_disk(self) -> None:
        """磁盘总量超限时按 mtime 从最旧开始清理（低频触发，不阻塞写入）。"""
        if not await asyncio.to_thread(self._cache_dir.exists):
            return
        files = [
            p
            for p in await asyncio.to_thread(
                lambda: list(self._cache_dir.rglob("*"))
            )
            if await asyncio.to_thread(p.is_file)
            and p.suffix != ".meta"
        ]
        if not files:
            return
        sizes = await asyncio.to_thread(
            lambda: {p: p.stat().st_size for p in files}
        )
        total = sum(sizes.values())
        if total <= self._max_disk_bytes:
            return
        target = self._max_disk_bytes * _DISK_EVICT_TARGET_RATIO
        for p in sorted(files, key=lambda p: sizes[p]):
            if total <= target:
                break
            meta = p.with_suffix(".meta")
            await asyncio.to_thread(p.unlink, missing_ok=True)
            await asyncio.to_thread(meta.unlink, missing_ok=True)
            total -= sizes[p]

    @staticmethod
    def _read_meta(meta_path: Path) -> dict[str, str] | None:
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("content_type"):
                return data
            return None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _write_meta(meta_path: Path, meta: dict[str, str]) -> None:
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    # ---- 对外接口 ----

    async def get(
        self,
        entity_code: str,
        record_id: str,
        file_token: str,
        key_suffix: str = "",
    ) -> tuple[bytes, str, str] | None:
        """返回 (content, content_type, filename) 或 None（未命中/过期/异常）。"""
        if not self._enabled:
            return None
        cache_key = self._cache_key(entity_code, record_id, file_token, key_suffix)
        entry = self._memory_get(cache_key)
        if entry is not None:
            self._hits += 1
            return entry.content, entry.content_type, entry.filename
        disk = await self._disk_read(cache_key)
        if disk is not None:
            content, content_type, filename = disk
            self._memory_put(
                cache_key,
                _MemoryEntry(
                    content,
                    content_type,
                    filename,
                    time.time() + self._ttl_seconds,
                ),
            )
            self._hits += 1
            return disk
        self._misses += 1
        return None

    async def set(
        self,
        entity_code: str,
        record_id: str,
        file_token: str,
        content: bytes,
        content_type: str,
        filename: str,
        key_suffix: str = "",
    ) -> None:
        if not self._enabled or not content:
            return
        cache_key = self._cache_key(entity_code, record_id, file_token, key_suffix)
        self._memory_put(
            cache_key,
            _MemoryEntry(
                content,
                content_type,
                filename,
                time.time() + self._ttl_seconds,
            ),
        )
        try:
            await self._disk_write(cache_key, content, content_type, filename)
            self._disk_writes_since_evict += 1
            if self._disk_writes_since_evict >= _DISK_EVICT_EVERY:
                self._disk_writes_since_evict = 0
                await self._evict_disk()
        except OSError:
            logger.warning("飞书附件磁盘缓存写入失败", exc_info=True)

    async def get_or_fetch(
        self,
        entity_code: str,
        record_id: str,
        file_token: str,
        fetcher: Fetcher,
        key_suffix: str = "",
    ) -> tuple[bytes, str, str] | None:
        """未命中时持锁回源并写缓存；并发请求同一附件只回源一次。"""
        if not self._enabled:
            return await fetcher()
        cached = await self.get(entity_code, record_id, file_token, key_suffix)
        if cached is not None:
            return cached
        lock = await self._lock_for(entity_code, record_id, file_token, key_suffix)
        async with lock:
            cached = await self.get(entity_code, record_id, file_token, key_suffix)
            if cached is not None:
                return cached
            result = await fetcher()
            if result is not None:
                await self.set(
                    entity_code,
                    record_id,
                    file_token,
                    *result,
                    key_suffix=key_suffix,
                )
            return result

    async def _lock_for(
        self,
        entity_code: str,
        record_id: str,
        file_token: str,
        key_suffix: str = "",
    ) -> asyncio.Lock:
        cache_key = self._cache_key(entity_code, record_id, file_token, key_suffix)
        async with self._locks_guard:
            lock = self._locks.get(cache_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[cache_key] = lock
            return lock

    def stats(self) -> dict[str, int | bool]:
        return {
            "enabled": self._enabled,
            "memory_entries": len(self._memory),
            "memory_bytes": self._memory_bytes,
            "hits": self._hits,
            "misses": self._misses,
        }


_attachment_cache: AttachmentCache | None = None


def get_attachment_cache() -> AttachmentCache:
    """应用级共享单例（配置变更需重启生效）。"""
    global _attachment_cache
    if _attachment_cache is None:
        settings = get_settings()
        _attachment_cache = AttachmentCache(
            enabled=settings.QUALITY_ATTACHMENT_CACHE_ENABLED,
            cache_dir=settings.QUALITY_ATTACHMENT_CACHE_DIR,
            max_memory_mb=settings.QUALITY_ATTACHMENT_CACHE_MAX_MEMORY_MB,
            max_disk_mb=settings.QUALITY_ATTACHMENT_CACHE_MAX_DISK_MB,
            ttl_seconds=settings.QUALITY_ATTACHMENT_CACHE_TTL_SECONDS,
        )
    return _attachment_cache
