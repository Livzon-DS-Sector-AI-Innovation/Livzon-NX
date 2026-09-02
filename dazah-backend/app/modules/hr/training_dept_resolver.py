"""培训模块部门解析规则（适用于培训管理全部页面）.

映射配置统一存放于 hr.training_dept_mappings（HR 设置"培训部门映射"维护），
本模块从配置表加载，不再维护硬编码字典。

解析规则：
1. 二级部门命中映射（match_level=second/both）→ 使用目标名（201 家族优先）；
2. 一级部门命中映射（match_level=first/both）→ 使用目标名；
3. 一级部门在培训部门列表中存在 → 使用一级部门；
4. 否则回退二级部门。
"""

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# 进程内缓存：配置快照（HR 设置写操作后调用
# invalidate_training_dept_mapping_cache()
# 失效）
# 多 worker 部署下通过 TTL 自动过期保证最终一致性（默认 60 秒）
_MAPPING_CACHE: list[dict[str, Any]] | None = None
_MAPPING_CACHE_LOCK = asyncio.Lock()
_CACHE_LOADED_AT: float = 0
_CACHE_TTL_SECONDS = 60

# 参与部门名解析的映射类型
_RESOLVE_TYPES = ("special", "alias")


async def _load_mappings(session: AsyncSession) -> list[dict[str, Any]]:
    """加载全部启用的映射配置（进程内缓存 + TTL 自动过期）."""
    global _MAPPING_CACHE, _CACHE_LOADED_AT
    now = time.monotonic()
    if _MAPPING_CACHE is not None and (now - _CACHE_LOADED_AT) < _CACHE_TTL_SECONDS:
        return _MAPPING_CACHE
    async with _MAPPING_CACHE_LOCK:
        # 双重检查：锁内再次判断 TTL
        now2 = time.monotonic()
        if (
            _MAPPING_CACHE is not None
            and (now2 - _CACHE_LOADED_AT) < _CACHE_TTL_SECONDS
        ):
            return _MAPPING_CACHE
        from app.modules.hr.repository import TrainingLedgerRepository

        mappings = await TrainingLedgerRepository(session).list_dept_mappings()
        _MAPPING_CACHE = [
            {
                "source_name": m.source_name,
                "target_name": m.target_name,
                "match_level": m.match_level,
                "mapping_type": m.mapping_type,
                "priority": m.priority,
            }
            for m in mappings
            if m.enabled
        ]
        _CACHE_LOADED_AT = time.monotonic()
        return _MAPPING_CACHE


def invalidate_training_dept_mapping_cache() -> None:
    """HR 设置写操作后失效缓存，下次解析自动重载."""
    global _MAPPING_CACHE
    _MAPPING_CACHE = None


def _resolve_mappings(mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """解析用映射（special/alias），按优先级升序."""
    return sorted(
        (m for m in mappings if m["mapping_type"] in _RESOLVE_TYPES),
        key=lambda m: (m["priority"], m["source_name"]),
    )


async def resolve_training_department(
    session: AsyncSession,
    department: str | None,
    sub_department: str | None = None,
) -> str | None:
    """将员工档案部门解析为培训管理使用的部门名（配置表驱动）."""
    mappings = _resolve_mappings(await _load_mappings(session))
    # 1. 二级部门优先（201 家族 both 条目优先命中）
    if sub_department:
        for m in mappings:
            if (
                m["match_level"] in ("second", "both")
                and m["source_name"] == sub_department
            ):
                target_name = m.get("target_name")
                return str(target_name) if target_name is not None else None
    # 2. 一级部门命中映射
    if department:
        for m in mappings:
            if m["match_level"] in ("first", "both") and m["source_name"] == department:
                target_name = m.get("target_name")
                return str(target_name) if target_name is not None else None
    if not department:
        return sub_department or department
    # 3. 一级部门在培训部门列表中存在 → 使用一级部门
    from app.modules.hr.repository import TrainingLedgerRepository

    depts = await TrainingLedgerRepository(session).list_all_training_departments()
    if department in depts:
        return department
    # 4. 回退二级部门
    return sub_department or department


async def training_dept_aliases_of(session: AsyncSession, norm: str) -> list[str]:
    "规范名的全部别名（含自身），用于 SQL IN 匹配（如 2"
    "01二车间（MC）→ 裸名/霉酚酸/201三车间）."
    aliases = {norm}
    for m in _resolve_mappings(await _load_mappings(session)):
        # 仅使用 resolve 类型（special/alias），排除 split/exclude/candidate_source
        # split 是一对多拆分关系，不是别名；若纳入会导致裸名同时出现在 MC 和 DR 的别名集中
        if m["target_name"] == norm and m["mapping_type"] in _RESOLVE_TYPES:
            aliases.add(m["source_name"])
    return sorted(aliases)


async def split_ledger_departments(session: AsyncSession, name: str) -> list[str]:
    """台账拆副本时把涉及部门名展开为规范归属部门列表；映射外名称原样返回.

    排序规则：MC 优先（裸名主记录归 MC），其余按字母序。
    """
    targets = [
        m["target_name"]
        for m in await _load_mappings(session)
        if m["mapping_type"] == "split"
        and m["source_name"] == name
        and m["target_name"]
    ]
    if not targets:
        return [name]
    # MC 优先，其余按字母序
    return sorted(targets, key=lambda t: (0 if "（MC）" in t else 1, t))


async def ledger_dept_read_family(session: AsyncSession, selected: str) -> list[str]:
    """读端（台账列表/ESG同步）选中部门命中的归属部门集合.

    201二车间 家族（由 split 目标 + exclude 的 201 源推导）：MC/DR 各自只见
    「自身规范名+历史别名」，MC/DR 之间不互见（拆分副本只归各自 Tab）。
    裸名「201二车间」总副本的归属由 list_by_department 通过 trainees 的
    飞书联系人部门动态判定，不再在此处加入别名集（否则 MC/DR 都会命中裸名记录）。
    其他部门仅含自身别名，控制影响面。
    """
    values = set(await training_dept_aliases_of(session, selected))
    # 不再将裸名 "201二车间" 加入 alias 集；
    # 裸名总副本按 trainees 的飞书部门归属到 MC 或 DR，见 repository.list_by_department
    return sorted(values)


# ─── 部门级数据隔离：用户可见范围解析 ──────────────────────────────────

_HR_WRITE_PERMISSIONS = {"hr:write"}


async def _user_is_hr_admin(db: AsyncSession, user: Any) -> bool:
    """管理员判定：super_admin（通配）或 hr:write 权限。"""
    from app.platform.identity.rbac import resolve_user_permissions

    perms = await resolve_user_permissions(db, user.id)
    return "*" in perms or bool(_HR_WRITE_PERMISSIONS & set(perms))


async def _load_user_dept_scope(db: AsyncSession, user: Any) -> set[str] | None:
    """读取配置表 hr_user_dept_scopes 的可见培训部门（规范名）；无配置返回 None。"""
    from sqlalchemy import select

    from app.modules.hr.models import HrUserDeptScope

    stmt = select(HrUserDeptScope).where(
        HrUserDeptScope.user_id == user.id,
        HrUserDeptScope.is_deleted.is_(False),
    )
    scope = (await db.execute(stmt)).scalar_one_or_none()
    if scope is None or not scope.visible_depts:
        return None
    return set(scope.visible_depts)


async def visible_training_dept_names(db: AsyncSession, user: Any) -> set[str] | None:
    """用户可见的培训规范部门名集合；None = 全部可见（管理员）。

    白名单制：管理员（hr:write/通配）→ 全部；否则按配置表指定；
    未配置 → 空集合（什么都看不到，需管理员在「部门权限配置」中授权）。
    """
    if await _user_is_hr_admin(db, user):
        return None
    norms = await _load_user_dept_scope(db, user)
    if norms is not None:
        return norms
    return set()  # 白名单：未配置 = 不可见任何部门


async def resolve_visible_dept_alias_set(
    db: AsyncSession, user: Any
) -> set[str] | None:
    """用户可见部门展开后的全部档案别名集合；None = 全部可见（管理员）。

    过滤时用于 SQL IN 匹配：档案口径表（employees/contracts/offboarding/调动）
    直接匹配 department/sub_department；培训口径表匹配规范名（自身也在别名集合内）。
    """
    norms = await visible_training_dept_names(db, user)
    if norms is None:
        return None
    alias_set: set[str] = set()
    for norm in norms:
        alias_set.update(await training_dept_aliases_of(db, norm))
    return alias_set
