"""巡检飞书交互会话管理 — 基于 Redis 的任务级上下文暂存。

每个用户（open_id）最多有一个活跃会话，存储完整巡检任务上下文：
- 任务信息（task_id, plan_type, route info）
- 设备顺序列表（含地点信息，线路巡检用）
- 当前设备索引
- 已完成/已跳过设备集合
- 当前设备的待确认结果

TTL 2 小时，每次交互自动续期。
"""

import json
import logging

from app.core.redis import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

_SESSION_PREFIX = "inspection:session:"
_SESSION_TTL = 7200  # 2 小时

# ── 会话状态枚举 ──
class SessionState:
    SELECTING = "selecting"   # 多个任务/工单待选择
    GUIDING = "guiding"       # 等待用户发送照片或手动填写
    CONFIRMING = "confirming" # AI 分析完成，等待确认/修改/取消


def _session_key(open_id: str) -> str:
    return f"{_SESSION_PREFIX}{open_id}"


async def _renew_ttl(open_id: str) -> None:
    """续期会话 TTL（每次交互自动调用）。"""
    from app.core.redis import redis_client
    await redis_client.expire(_session_key(open_id), _SESSION_TTL)


# ═══════════ 会话 CRUD ═══════════


async def save_session(
    open_id: str,
    *,
    task_id: str,
    plan_type: str,
    task_no: str,
    route_name: str = "",
    equipment_order: list[dict],
    completed_equipment_ids: list[str] | None = None,
    skipped_equipment_ids: list[str] | None = None,
    current_equipment_index: int = 0,
    state: str = SessionState.GUIDING,
    pending_results: list[dict] | None = None,
) -> None:
    """创建或覆盖巡检会话。

    Args:
        equipment_order: 设备顺序列表，每项:
            {equipment_id, equipment_name, equipment_no, location_name, location_sort_order}
        pending_results: 当前设备的待确认结果，None 表示处于引导状态
    """
    data = {
        "task_id": task_id,
        "plan_type": plan_type,
        "task_no": task_no,
        "route_name": route_name,
        "equipment_order": equipment_order,
        "completed_equipment_ids": completed_equipment_ids or [],
        "skipped_equipment_ids": skipped_equipment_ids or [],
        "current_equipment_index": current_equipment_index,
        "state": state,
        "pending_results": pending_results,
    }
    await cache_set(
        _session_key(open_id),
        json.dumps(data, ensure_ascii=False),
        ex=_SESSION_TTL,
    )
    logger.info(
        "巡检会话已保存: open_id=%s, task=%s, equipment=%d/%d, state=%s",
        open_id, task_no, current_equipment_index + 1,
        len(equipment_order), state,
    )


async def get_session(open_id: str) -> dict | None:
    """读取巡检会话，不存在返回 None。自动续期 TTL。"""
    raw = await cache_get(_session_key(open_id))
    if raw is None:
        return None
    try:
        await _renew_ttl(open_id)
        return json.loads(raw)  # type: ignore[return-value]
    except (json.JSONDecodeError, TypeError):
        logger.warning("巡检会话数据损坏: open_id=%s", open_id)
        await clear_session(open_id)
        return None


async def update_session(open_id: str, **kwargs) -> bool:
    """部分更新会话字段，会话不存在返回 False。自动续期。"""
    session = await get_session(open_id)
    if session is None:
        return False
    session.update(kwargs)
    await cache_set(
        _session_key(open_id),
        json.dumps(session, ensure_ascii=False),
        ex=_SESSION_TTL,
    )
    return True


async def clear_session(open_id: str) -> None:
    """清除巡检会话。"""
    await cache_delete(_session_key(open_id))
    logger.info("巡检会话已清除: open_id=%s", open_id)


# ═══════════ 会话便捷操作 ═══════════


async def set_pending_results(open_id: str, results: list[dict]) -> bool:
    """设置当前设备的待确认结果，状态切换为 confirming。"""
    return await update_session(
        open_id,
        pending_results=results,
        state=SessionState.CONFIRMING,
    )


async def mark_equipment_completed(open_id: str, equipment_id: str) -> bool:
    """标记设备为已完成，清除待确认结果，切换到引导状态。"""
    session = await get_session(open_id)
    if session is None:
        return False
    completed = set(session.get("completed_equipment_ids", []))
    completed.add(equipment_id)
    return await update_session(
        open_id,
        completed_equipment_ids=list(completed),
        pending_results=None,
        state=SessionState.GUIDING,
    )


async def mark_equipment_skipped(open_id: str, equipment_id: str) -> bool:
    """标记设备为已跳过。"""
    session = await get_session(open_id)
    if session is None:
        return False
    skipped = set(session.get("skipped_equipment_ids", []))
    skipped.add(equipment_id)
    return await update_session(
        open_id,
        skipped_equipment_ids=list(skipped),
        pending_results=None,
        state=SessionState.GUIDING,
    )


async def advance_to_next_equipment(open_id: str) -> dict | None:
    """将当前设备索引前进到下一个未完成设备，返回更新后的会话或 None。"""
    session = await get_session(open_id)
    if session is None:
        return None

    order = session.get("equipment_order", [])
    completed = set(session.get("completed_equipment_ids", []))
    skipped = set(session.get("skipped_equipment_ids", []))
    done = completed | skipped

    # 找到下一个未处理的设备
    for i, eq in enumerate(order):
        if eq["equipment_id"] not in done:
            await update_session(
                open_id,
                current_equipment_index=i,
                pending_results=None,
                state=SessionState.GUIDING,
            )
            return await get_session(open_id)

    # 全部完成
    return None


def get_current_equipment(session: dict) -> dict | None:
    """从会话中获取当前设备信息。"""
    order = session.get("equipment_order", [])
    idx = session.get("current_equipment_index", 0)
    if 0 <= idx < len(order):
        return order[idx]
    return None


def get_progress(session: dict) -> dict:
    """从会话中提取进度信息。"""
    order = session.get("equipment_order", [])
    completed = set(session.get("completed_equipment_ids", []))
    skipped = set(session.get("skipped_equipment_ids", []))

    total = len(order)
    done_n = len([e for e in order if e["equipment_id"] in completed])
    skip_n = len([e for e in order if e["equipment_id"] in skipped])
    remaining = total - done_n - skip_n

    # 按地点分组
    locations: list[dict] = []
    current_loc: str | None = None
    for eq in order:
        loc_name = eq.get("location_name", "")
        if loc_name != current_loc:
            current_loc = loc_name
            locations.append({
                "location_name": loc_name,
                "equipment": [],
            })
        eid = eq["equipment_id"]
        status = "completed" if eid in completed else ("skipped" if eid in skipped else "pending")
        locations[-1]["equipment"].append({
            "equipment_id": eid,
            "equipment_name": eq["equipment_name"],
            "equipment_no": eq.get("equipment_no", ""),
            "status": status,
        })

    return {
        "total": total,
        "done": done_n,
        "skipped": skip_n,
        "remaining": remaining,
        "locations": locations,
    }


# ═══════════ 选择会话（多任务/多工单选择）══════════

_SELECTION_PREFIX = "inspection:selection:"
_SELECTION_TTL = 300  # 5 分钟


async def save_selection(
    open_id: str,
    *,
    select_type: str,  # "inspection" | "work_order"
    options: list[dict],
) -> None:
    """暂存选择列表（多个巡检任务或工单时的数字选择）。"""
    data = {
        "state": SessionState.SELECTING,
        "select_type": select_type,
        "options": options,
    }
    await cache_set(
        _SELECTION_PREFIX + open_id,
        json.dumps(data, ensure_ascii=False),
        ex=_SELECTION_TTL,
    )


async def get_selection(open_id: str) -> dict | None:
    """读取选择会话。"""
    raw = await cache_get(_SELECTION_PREFIX + open_id)
    if raw is None:
        return None
    try:
        return json.loads(raw)  # type: ignore[return-value]
    except (json.JSONDecodeError, TypeError):
        await clear_selection(open_id)
        return None


async def clear_selection(open_id: str) -> None:
    """清除选择会话。"""
    await cache_delete(_SELECTION_PREFIX + open_id)
