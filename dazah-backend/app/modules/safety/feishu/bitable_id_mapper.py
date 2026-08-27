"""Bitable open_id 映射器。

将 identity.users 中的 employee user_id/name 转换为 Bitable person 字段
所需的 open_id（安全应用视角），解决两个飞书应用 open_id 命名空间不一致的问题。

映射数据源：app/modules/safety/feishu/bitable_open_ids.json
刷新方式：重新运行 scripts/tmp/sync_all_bitable_by_userid.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 映射文件：与当前模块同目录
_MAPPING_PATH = Path(__file__).parent / "bitable_open_ids.json"

# ── 内存缓存 ──────────────────────────────────────────────
_data: dict[str, dict[str, str]] | None = None  # lazy load


def _load() -> dict[str, dict[str, str]]:
    """延迟加载映射数据，构建 {user_id: {name, bitable_open_id, email}} 索引。"""
    global _data
    if _data is not None:
        return _data

    _data = {}
    try:
        raw: Any = json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raw = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            uid = (entry.get("user_id") or "").strip()
            bitable_oid = (entry.get("bitable_open_id") or "").strip()
            if (
                isinstance(uid, str)
                and isinstance(bitable_oid, str)
                and uid
                and bitable_oid
            ):
                _data[uid] = {
                    "name": str(entry.get("name", "")),
                    "bitable_open_id": bitable_oid,
                    "email": str(entry.get("email") or ""),
                }
        logger.info("BitableIdMapper 已加载 %d 条映射（%d 有效）", len(raw), len(_data))
    except Exception:
        logger.exception("BitableIdMapper 加载映射文件失败: %s", _MAPPING_PATH)
        _data = {}
    return _data


def _reload() -> None:
    """强制重新加载（映射文件更新后调用）。"""
    global _data
    _data = None
    _load()


# ── 公开查询接口 ──────────────────────────────────────────


def get_bitable_open_id(
    user_id: str | None = None,
    name: str | None = None,
    fallback_to_identity: str | None = None,
) -> str | None:
    """通过 user_id 或 name 查找 Bitable open_id。

    查找顺序：
      1. user_id 精确匹配（推荐，最可靠）
      2. name 精确匹配（user_id 为空时使用）
      3. fallback_to_identity 回退（映射中找不到时返回此值）

    Returns:
        Bitable open_id 字符串，查不到返回 fallback_to_identity 或 None
    """
    mapping = _load()

    # 策略 1：user_id 精确匹配
    if user_id:
        entry = mapping.get(user_id.strip())
        if entry:
            value = entry.get("bitable_open_id")
            return value if isinstance(value, str) else None

    # 策略 2：name 精确匹配
    if name:
        for uid, entry in mapping.items():
            if entry["name"] == name.strip():
                value = entry.get("bitable_open_id")
                return value if isinstance(value, str) else None

    # 策略 3：回退
    if fallback_to_identity:
        logger.debug(
            "Bitable open_id 未找到(user_id=%s name=%s)，使用 identity open_id 回退",
            user_id,
            name,
        )
        return fallback_to_identity

    logger.warning(
        "Bitable open_id 未找到且无回退值: user_id=%s name=%s",
        user_id,
        name,
    )
    return None


def get_user_id_by_bitable_open_id(bitable_open_id: str) -> str | None:
    """反向查找：安全应用 open_id → employee user_id。

    用于 _resolve_person 中，Bitable person 字段的 open_id 是安全应用命名空间，
    与 identity.users 中存储的全局应用 open_id 不同。通过此函数将安全应用 open_id
    转换为 user_id，再用 user_id 查 identity.users。
    """
    if not bitable_open_id:
        return None
    mapping = _load()
    for uid, entry in mapping.items():
        if entry["bitable_open_id"] == bitable_open_id:
            return uid
    return None


def get_bitable_person_value(
    user_id: str | None = None,
    name: str | None = None,
    fallback_to_identity: str | None = None,
) -> list[dict[str, str]] | None:
    """构造 Bitable person 字段写入值。

    Returns:
        [{"id": "<bitable_open_id>"}] 列表，或 None（查不到时）
    """
    oid = get_bitable_open_id(
        user_id=user_id,
        name=name,
        fallback_to_identity=fallback_to_identity,
    )
    if oid:
        return [{"id": oid}]
    return None
