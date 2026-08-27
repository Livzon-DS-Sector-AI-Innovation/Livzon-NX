"""权限缓存：Redis 缓存用户权限集合 + 事件总线失效。

Key: identity:permissions:{user_id}
Value: JSON 数组 ["production:read","hr:write",...]
TTL: 5 分钟

角色/权限变更时通过事件总线发布 identity.permissions.changed，
监听器删除对应缓存，用户下次请求重新从 DB 加载。
"""

import json
import logging
from typing import Any

from app.core.events import event_bus
from app.core.redis import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

PERMISSION_CACHE_TTL = 300  # 5 分钟
PERMISSION_CACHE_PREFIX = "identity:permissions:"
PERMISSIONS_CHANGED_EVENT = "identity.permissions.changed"
PERMISSIONS_CHANGED_ALL_EVENT = "identity.permissions.changed_all"


def _cache_key(user_id: Any) -> str:
    return f"{PERMISSION_CACHE_PREFIX}{user_id}"


def _cache_ts_key(user_id: Any) -> str:
    """缓存写入时间戳 key（与权限缓存同 TTL，记录“生效时间”供权限验证台预览）。"""
    return f"{PERMISSION_CACHE_PREFIX}ts:{user_id}"


async def get_cached_permissions(user_id: Any) -> list[str] | None:
    """读取缓存权限。未命中返回 None。"""
    raw = await cache_get(_cache_key(user_id))
    if raw is None:
        return None
    try:
        value = json.loads(raw)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return value
        raise TypeError("permission cache is not a string list")
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupted permission cache for user %s", user_id)
        await cache_delete(_cache_key(user_id))
        return None


async def get_cached_permissions_with_time(
    user_id: Any,
) -> tuple[list[str] | None, str | None]:
    """读取缓存权限 + 缓存生成时间（ISO 字符串）。

    时间戳由 set_cached_permissions 写入；无时间戳（旧数据）返回 None，
    由调用方回退为当前时间。未命中或损坏时 (None, None)。
    """
    cached = await get_cached_permissions(user_id)
    if cached is None:
        return None, None
    ts = await cache_get(_cache_ts_key(user_id))
    return cached, ts


async def set_cached_permissions(user_id: Any, permissions: list[str]) -> None:
    """写入缓存权限（同时记录写入时间戳，TTL 与权限缓存一致）。"""
    from datetime import UTC, datetime

    await cache_set(
        _cache_key(user_id),
        json.dumps(permissions, ensure_ascii=False),
        ex=PERMISSION_CACHE_TTL,
    )
    await cache_set(
        _cache_ts_key(user_id),
        datetime.now(UTC).isoformat(),
        ex=PERMISSION_CACHE_TTL,
    )


async def invalidate_permissions(user_id: Any) -> None:
    """删除用户权限缓存（含写入时间戳）。"""
    await cache_delete(_cache_key(user_id))
    await cache_delete(_cache_ts_key(user_id))


async def invalidate_all_permissions() -> int:
    """清空全部用户权限缓存（菜单/角色菜单变更时调用），返回删除条数。"""
    deleted = 0
    try:
        from app.core.redis import redis_client

        async for key in redis_client.scan_iter(f"{PERMISSION_CACHE_PREFIX}*"):
            await redis_client.delete(key)
            deleted += 1
    except Exception:
        logger.exception("Menu change cache sweep failed (non-fatal)")
    if deleted:
        logger.info("Permission cache swept: %d keys", deleted)
    return deleted


async def _on_permissions_changed(data: Any) -> None:
    """事件监听器：data 为 user_id 或 {"user_id": ...}。"""
    user_id = data.get("user_id") if isinstance(data, dict) else data
    if not user_id:
        return
    await invalidate_permissions(user_id)
    logger.info("Permission cache invalidated for user %s", user_id)


async def _on_permissions_changed_all(data: Any) -> None:
    """事件监听器：菜单/角色菜单变更，清空全部用户权限缓存。"""
    await invalidate_all_permissions()


event_bus.subscribe(PERMISSIONS_CHANGED_EVENT, _on_permissions_changed)
event_bus.subscribe(PERMISSIONS_CHANGED_ALL_EVENT, _on_permissions_changed_all)


async def publish_permissions_changed(user_id: Any) -> None:
    """发布权限变更事件（admin API 变更角色/规则后调用）。"""
    await event_bus.publish(PERMISSIONS_CHANGED_EVENT, {"user_id": str(user_id)})


async def publish_permissions_changed_all() -> None:
    """发布全量权限缓存失效事件（菜单/角色菜单绑定变更后调用）。"""
    await event_bus.publish(PERMISSIONS_CHANGED_ALL_EVENT, None)
