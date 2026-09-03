"""部门数据范围（Department Data Scope）：平台级行级数据隔离机制。

可见部门范围解析优先级：
1. super_admin 角色 / DEV_BYPASS 本地开发用户 → 全部部门
2. 用户级配置（DataScopeRule.user_id 匹配）→ 全部或指定部门（覆盖）
3. 角色级配置（用户全部角色关联的 DataScopeRule）→ 并集；任一全部 → 全部
4. 默认：本部门 + 全部子部门（identity.departments 部门树向下展开）

配置由超级管理员在后台维护（角色管理/用户角色页），不写死在代码中。
HR/质量/仓储等业务模块在 API 层调用本工具过滤数据行，未来新增模块
复用同一机制（禁止各模块自行实现）。

结果缓存：Redis `identity:data-scope:{user_id}`，TTL 5 分钟；
配置变更时发布事件清对应缓存。
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import event_bus
from app.core.redis import cache_delete, cache_get, cache_set
from app.platform.identity.models import DataScopeRule, Department, User
from app.platform.identity.rbac import (
    DEV_BYPASS_OPEN_ID,
    SUPER_ADMIN_ROLE_CODE,
    resolve_user_roles,
)

logger = logging.getLogger(__name__)

DATA_SCOPE_CACHE_TTL = 300  # 5 分钟
DATA_SCOPE_CACHE_PREFIX = "identity:data-scope:"
DATA_SCOPE_CHANGED_EVENT = "identity.data_scope.changed"
current_page_data_scope: ContextVar[dict[str, Any] | None] = ContextVar(
    "current_page_data_scope", default=None
)
current_page_actor: ContextVar[User | None] = ContextVar(
    "current_page_actor", default=None
)
current_page_key: ContextVar[str | None] = ContextVar("current_page_key", default=None)


@dataclass
class DepartmentScope:
    """用户可见部门范围。"""

    is_all: bool = False
    department_names: set[str] = field(default_factory=set)

    def allows(self, department: str | None) -> bool:
        """判断某数据行的部门名是否在可见范围内。"""
        if self.is_all:
            return True
        if not department:
            return False
        return department in self.department_names


def _parse_department_ids(raw: str | None) -> list[str]:
    """解析 feishu_department_ids（JSON 数组字符串）。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str) and v]
    return []


def _build_children_map(
    departments: list[Department],
) -> dict[str, list[Department]]:
    children: dict[str, list[Department]] = {}
    for dept in departments:
        if dept.parent_feishu_department_id:
            children.setdefault(dept.parent_feishu_department_id, []).append(dept)
    return children


def _collect_subtree_names(
    root_id: str,
    by_feishu_id: dict[str, Department],
    children_map: dict[str, list[Department]],
    names: set[str],
) -> None:
    """从部门节点向下收集自身 + 全部子孙部门名。"""
    root = by_feishu_id.get(root_id)
    if root is None:
        return
    names.add(root.name)
    for child in children_map.get(root_id, []):
        _collect_subtree_names(
            child.feishu_department_id, by_feishu_id, children_map, names
        )


async def _resolve_department_scope(db: AsyncSession, user: User) -> DepartmentScope:
    """解析用户可见部门范围（不查缓存）。

    优先级：super_admin/DEV_BYPASS > 用户级配置 > 角色级配置 > 默认部门树。
    """
    if getattr(user, "role", None) == "admin":
        return DepartmentScope(is_all=True)
    roles = await resolve_user_roles(db, user.id)
    if any(r.code == SUPER_ADMIN_ROLE_CODE for r in roles):
        return DepartmentScope(is_all=True)
    if str(user.feishu_open_id) == DEV_BYPASS_OPEN_ID:
        return DepartmentScope(is_all=True)

    # 用户级配置（个例覆盖，如高管）
    user_rule = await _load_rule(db, user_id=user.id)
    if user_rule is not None:
        return _rule_to_scope(user_rule)

    # 角色级配置（批量，并集；任一全部 → 全部）
    role_ids = [r.id for r in roles]
    if role_ids:
        role_scope = await _resolve_role_rules_scope(db, role_ids)
        if role_scope is not None:
            return role_scope

    # 默认：本部门 + 全部子部门
    names: set[str] = set()
    dept_ids = _parse_department_ids(user.feishu_department_ids)
    if dept_ids:
        result = await db.execute(select(Department))
        departments = list(result.scalars().all())
        by_feishu_id = {d.feishu_department_id: d for d in departments}
        children_map = _build_children_map(departments)
        for dept_id in dept_ids:
            _collect_subtree_names(dept_id, by_feishu_id, children_map, names)
    # 部门名兜底：无飞书部门 ID 或部门不在树中时，仍可见自身部门名
    if user.department:
        names.add(user.department)
    return DepartmentScope(is_all=False, department_names=names)


def _parse_department_names(raw: str | None) -> list[str]:
    """解析 department_names（JSON 数组字符串）。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return []


def _rule_to_scope(rule: DataScopeRule) -> DepartmentScope:
    """规则 → 范围。"""
    if rule.scope_type == "all":
        return DepartmentScope(is_all=True)
    return DepartmentScope(
        is_all=False,
        department_names=set(_parse_department_names(rule.department_names)),
    )


async def _load_rule(
    db: AsyncSession,
    *,
    user_id: Any = None,
    role_id: Any = None,
) -> DataScopeRule | None:
    stmt = select(DataScopeRule).where(
        DataScopeRule.is_deleted == False  # noqa: E712
    )
    if user_id is not None:
        stmt = stmt.where(DataScopeRule.user_id == user_id)
    if role_id is not None:
        stmt = stmt.where(DataScopeRule.role_id == role_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def _resolve_role_rules_scope(
    db: AsyncSession,
    role_ids: list[Any],
) -> DepartmentScope | None:
    """角色级规则并集；无规则返回 None（走默认）。"""
    if not role_ids:
        return None
    result = await db.execute(
        select(DataScopeRule).where(
            DataScopeRule.role_id.in_(role_ids),
            DataScopeRule.is_deleted == False,  # noqa: E712
        )
    )
    rules = list(result.scalars().all())
    if not rules:
        return None
    if any(r.scope_type == "all" for r in rules):
        return DepartmentScope(is_all=True)
    names: set[str] = set()
    for rule in rules:
        names.update(_parse_department_names(rule.department_names))
    return DepartmentScope(is_all=False, department_names=names)


async def resolve_user_department_scope(
    db: AsyncSession,
    user: User,
) -> DepartmentScope:
    """解析用户可见部门范围（Redis 缓存 5 分钟）。"""
    if getattr(user, "role", None) == "admin":
        return DepartmentScope(is_all=True)
    page_scope = current_page_data_scope.get()
    if page_scope is not None:
        scope_type = page_scope.get("scope_type")
        if scope_type in {"all", "not_applicable"}:
            return DepartmentScope(is_all=True)
        if scope_type not in {"departments", "department_tree"}:
            # A self scope requires an owner adapter; never widen it to a department.
            return DepartmentScope(is_all=False)
        department_ids = (
            page_scope.get("department_ids", [])
            if scope_type == "departments"
            else _parse_department_ids(user.feishu_department_ids)
        )
        result = await db.execute(select(Department))
        return page_department_scope(list(result.scalars().all()), department_ids)
    cache_key = f"{DATA_SCOPE_CACHE_PREFIX}{user.id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        try:
            payload = json.loads(cached)
            if payload.get("is_all"):
                return DepartmentScope(is_all=True)
            return DepartmentScope(
                is_all=False,
                department_names=set(payload.get("names", [])),
            )
        except (json.JSONDecodeError, TypeError):
            logger.warning("Corrupted data scope cache for user %s", user.id)

    scope = await _resolve_department_scope(db, user)
    payload = {"is_all": scope.is_all, "names": sorted(scope.department_names)}
    await cache_set(
        cache_key,
        json.dumps(payload, ensure_ascii=False),
        ex=DATA_SCOPE_CACHE_TTL,
    )
    return scope


def page_department_scope(
    departments: list[Department], root_ids: list[str]
) -> DepartmentScope:
    """Resolve stable IDs without widening name-based business adapters.

    Missing mappings fail closed. A department name shared with an ungranted
    (including retired) ID is ambiguous and must not authorize those rows.
    """
    active = [
        item
        for item in departments
        if not item.is_deleted and not item.status_is_deleted
    ]
    by_id = {item.feishu_department_id: item for item in active}
    children = _build_children_map(active)
    selected: set[str] = set()
    pending = list(root_ids)
    while pending:
        department_id = pending.pop()
        if department_id in selected or department_id not in by_id:
            continue
        selected.add(department_id)
        pending.extend(
            item.feishu_department_id for item in children.get(department_id, [])
        )
    names = {by_id[item].name for item in selected}
    if any(
        item.name in names and item.feishu_department_id not in selected
        for item in departments
    ):
        raise HTTPException(
            403, "部门名称存在歧义，无法安全确定页面数据范围，请联系管理员"
        )
    return DepartmentScope(is_all=False, department_names=names)


def filter_rows_by_department(
    rows: list[Any],
    dept_getter: Any,
    scope: DepartmentScope,
) -> list[Any]:
    """内存过滤数据行（飞书 Base 数据行等非 ORM 数据）。"""
    if scope.is_all:
        return rows
    return [row for row in rows if scope.allows(dept_getter(row))]


def department_in_clause(column: Any, scope: DepartmentScope) -> Any:
    """构造 SQL 部门过滤条件（ORM 用）；is_all 时返回 None 表示不过滤。"""
    if scope.is_all:
        return None
    if not scope.department_names:
        return false()
    return column.in_(list(scope.department_names))


# ─── 配置变更缓存失效（事件总线）──────────────────────────────────────


async def _on_data_scope_changed(data: Any) -> None:
    """事件监听器：data={"target_type": "user"|"role", "target_id": ...}。

    user → 清该用户缓存；role/其他 → 清全部（角色影响面不可枚举，
    配置变更低频，全量清扫简单可靠）。
    """
    if not isinstance(data, dict):
        return
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    if target_type == "user" and target_id:
        await cache_delete(f"{DATA_SCOPE_CACHE_PREFIX}{target_id}")
        logger.info("Data scope cache invalidated for user %s", target_id)
        return
    deleted = 0
    try:
        from app.core.redis import redis_client

        async for key in redis_client.scan_iter(f"{DATA_SCOPE_CACHE_PREFIX}*"):
            await redis_client.delete(key)
            deleted += 1
    except Exception:
        logger.exception("Data scope cache sweep failed (non-fatal)")
    if deleted:
        logger.info("Data scope cache swept: %d keys", deleted)


event_bus.subscribe(DATA_SCOPE_CHANGED_EVENT, _on_data_scope_changed)


async def publish_data_scope_changed(target_type: str, target_id: Any) -> None:
    """发布数据范围配置变更事件（管理 API 保存规则后调用）。"""
    await event_bus.publish(
        DATA_SCOPE_CHANGED_EVENT,
        {"target_type": target_type, "target_id": str(target_id)},
    )
