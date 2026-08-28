"""RBAC 权限目录、前缀映射与权限解析。

单一来源：
- PERMISSION_MODULES：全部业务模块清单（生成权限点）
- PREFIX_MODULE_MAP：路径前缀 → 模块映射表（权限中间件据此匹配）
- resolve_user_permissions：解析用户权限（部门映射 + 手动并集，DISTINCT 去重）
- seed_permissions：启动种子（权限点 + super_admin 角色，幂等）
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.menu_seed_data import SEED_MENUS
from app.platform.identity.models import (
    DepartmentRoleRule,
    Menu,
    Permission,
    Role,
    RoleMenu,
    RolePermission,
    UserModuleGrant,
    UserRole,
)

logger = logging.getLogger(__name__)

# 超级管理员角色编码（通配权限）
SUPER_ADMIN_ROLE_CODE = "super_admin"

# 本地开发用户（DEV_BYPASS_AUTH 模式由 get_current_user 创建）：
# 视为管理员，拥有全部权限（通配），不受部门级数据隔离限制
DEV_BYPASS_OPEN_ID = "dev-bypass-open-id"

# ─── 业务模块清单（生成权限点）───────────────────────────────────────
# 与 app/api/router.py 实际挂载前缀对齐；ai_parser/product 未挂载，不生成权限点
PERMISSION_MODULES: list[str] = [
    "production",
    "equipment",
    "safety",
    "environment",
    "energy",
    "warehouse",
    "procurement",
    "administration",
    "hr",
    "research",
    "registration",
    "quality",
    "regulatory_tracker",
    "identity",
    "system",
    "llm",
]

# 各模块生成的权限点（action 列表）
MODULE_ACTIONS: dict[str, list[str]] = {
    module: ["read", "write"] for module in PERMISSION_MODULES
}
# identity 模块额外生成 admin（权限管理）
MODULE_ACTIONS["identity"].append("admin")
# 仓储模块细分编辑权限（按飞书部门映射的子领域，三段码 module:resource:action）：
# 成品 / 五金 / 原辅料及包材 各自独立可编辑；warehouse:write 保留给超管与既有场景
MODULE_ACTIONS["warehouse"] += [
    "product:write",
    "hardware:write",
    "raw:write",
]
# HR 模块细分页面权限：员工档案（员工管理 + 员工档案页）仅人力资源部可见，
# 其他部门通过“人事查看员”角色（hr:read）只读其余人事页面
MODULE_ACTIONS["hr"] += [
    "employee:read",
]

# ─── 路径前缀 → 模块映射表（权限中间件单一来源）──────────────────────
# 注意：regulatory_tracker 无统一前缀，需覆盖 3 处
PREFIX_MODULE_MAP: dict[str, str] = {
    "/api/v1/production": "production",
    "/api/v1/equipment": "equipment",
    "/api/v1/safety": "safety",
    "/api/v1/environment": "environment",
    "/api/v1/energy": "energy",
    "/api/v1/warehouse": "warehouse",
    "/api/v1/procurement": "procurement",
    "/api/v1/administration": "administration",
    "/api/v1/hr": "hr",
    "/api/v1/research": "research",
    "/api/v1/registration": "registration",
    "/api/v1/quality": "quality",
    "/api/v1/regulatory-tracker": "regulatory_tracker",
    "/api/v1/regulatory-documents": "regulatory_tracker",
    "/api/v1/sync-jobs": "regulatory_tracker",
    "/api/v1/llm/configs": "llm",
    "/api/v1/system": "system",
    "/api/v1/identity/admin": "identity",  # identity:admin 特殊处理（见下）
    "/api/v1/identity": "identity",
}

# 公开路径豁免（完全无需登录）
PUBLIC_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/system/modules",
    "/api/v1/identity/auth/",
    "/mcp",
    "/uploads",
)

# identity 子路径策略：
# - /api/v1/identity/auth/* → 公开豁免（已在 PUBLIC_PATH_PREFIXES）
# - /api/v1/identity/me、/departments、/personnel、/menus → 仅要求登录（identity:read）
# - /api/v1/identity/sync/* → identity:write（写操作）
# - /api/v1/identity/admin/* → identity:admin
IDENTITY_READ_ONLY_PREFIXES: tuple[str, ...] = (
    "/api/v1/identity/me",
    "/api/v1/identity/departments",
    "/api/v1/identity/personnel",
    "/api/v1/identity/menus",
)
IDENTITY_SYNC_PREFIX = "/api/v1/identity/sync"
IDENTITY_ADMIN_PREFIX = "/api/v1/identity/admin"


def build_permission_catalog() -> list[dict[str, Any]]:
    """构造权限目录（module x actions）。"""
    catalog: list[dict[str, Any]] = []
    for module in PERMISSION_MODULES:
        for action in MODULE_ACTIONS[module]:
            catalog.append(
                {
                    "code": f"{module}:{action}",
                    "module": module,
                    "action": action,
                    "name": f"{module}.{action}",
                }
            )
    return catalog


def match_module(path: str) -> str | None:
    """按路径前缀匹配模块名。返回 None 表示无需权限控制（未命中任何模块）。"""
    # identity 子路径特殊策略（优先级高于通用前缀匹配）
    if path.startswith(IDENTITY_SYNC_PREFIX):
        return "identity"
    if path.startswith(IDENTITY_ADMIN_PREFIX):
        return "identity"

    # 最长前缀优先匹配
    matched: str | None = None
    matched_len = 0
    for prefix, module in PREFIX_MODULE_MAP.items():
        if path.startswith(prefix) and len(prefix) > matched_len:
            matched = module
            matched_len = len(prefix)
    return matched


def match_action(method: str) -> str:
    """HTTP 方法 → 操作：GET/HEAD → read，其余 → write。"""
    return "read" if method.upper() in {"GET", "HEAD"} else "write"


def is_public_path(path: str) -> bool:
    """公开路径豁免判断。"""
    return any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES)


def is_identity_read_only(path: str) -> bool:
    """identity 仅要求登录的子路径（不需要模块权限，只要登录即可）。"""
    return any(path.startswith(p) for p in IDENTITY_READ_ONLY_PREFIXES)


# ─── 权限解析 ─────────────────────────────────────────────────────────


async def resolve_user_roles(db: AsyncSession, user_id: Any) -> list[Role]:
    """解析用户全部角色（部门映射 + 手动并集，DISTINCT 去重）。

    部门映射规则按“飞书部门 ID 精确匹配”或“部门名精确匹配”任一命中即授予
    （双条件独立，不再要求用户无部门 ID，避免登录补全部门后部门名匹配失效）。
    """
    from app.platform.identity.models import User

    # 手动分配角色
    manual_stmt = (
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.source == "manual",
            UserRole.is_deleted == False,  # noqa: E712
            Role.is_deleted == False,  # noqa: E712
        )
    )
    manual_result = await db.execute(manual_stmt)
    manual_roles = list(manual_result.scalars().all())

    # 部门映射角色
    user_result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
    )
    user = user_result.scalar_one_or_none()
    dept_role_ids: list[Any] = []
    if user is not None:
        dept_ids: list[str] = []
        if user.feishu_department_ids:
            try:
                dept_ids = json.loads(user.feishu_department_ids)
            except (json.JSONDecodeError, TypeError):
                dept_ids = []

        rule_stmt = select(DepartmentRoleRule).where(
            DepartmentRoleRule.is_deleted == False  # noqa: E712
        )
        rule_result = await db.execute(rule_stmt)
        rules = list(rule_result.scalars().all())

        for rule in rules:
            # 双条件独立匹配（任一命中即授予）：
            # 1) 飞书部门 ID 精确匹配（规则配置了 od-xxx 且用户部门数组包含）
            # 2) 部门名精确匹配（规则仅配置部门名时也生效）
            #    —— 不再要求"用户无部门 ID"：登录时 _complete_department_info 会
            #    补全 feishu_department_ids，若部门名匹配依赖其为空，该方式将永久失效。
            if rule.feishu_department_id and rule.feishu_department_id in dept_ids:
                dept_role_ids.append(rule.role_id)
            elif (
                rule.department_name
                and user.department
                and user.department == rule.department_name
            ):
                dept_role_ids.append(rule.role_id)

    dept_roles: list[Role] = []
    if dept_role_ids:
        dept_stmt = select(Role).where(
            Role.id.in_(dept_role_ids),
            Role.is_deleted == False,  # noqa: E712
        )
        dept_result = await db.execute(dept_stmt)
        dept_roles = list(dept_result.scalars().all())

    # 并集去重（按 id）
    seen: set[Any] = set()
    merged: list[Role] = []
    for role in [*manual_roles, *dept_roles]:
        if role.id not in seen:
            seen.add(role.id)
            merged.append(role)
    return merged


async def resolve_user_permissions(db: AsyncSession, user_id: Any) -> list[str]:
    """解析用户权限 code 列表。

    super_admin 角色返回通配符 ["*"]；
    DEV_BYPASS_AUTH 本地开发用户同样返回通配符 ["*"]（开发环境视为管理员，
    不参与部门级数据隔离等权限限制）。
    """
    from app.platform.identity.models import User

    # 本地开发用户：全部权限
    dev_result = await db.execute(
        select(User.id).where(
            User.id == user_id,
            User.feishu_open_id == DEV_BYPASS_OPEN_ID,
            User.is_deleted.is_(False),
        )
    )
    if dev_result.scalar_one_or_none() is not None:
        return ["*"]

    user_result = await db.execute(
        select(User).where(User.id == user_id, User.is_deleted.is_(False))
    )
    user = user_result.scalar_one_or_none()
    if user is not None and user.role == "admin":
        return ["*"]

    roles = await resolve_user_roles(db, user_id)
    if any(r.code == SUPER_ADMIN_ROLE_CODE for r in roles):
        return ["*"]

    codes: list[str] = []
    role_ids = [r.id for r in roles]
    if role_ids:
        rp_stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(
                RolePermission.role_id.in_(role_ids),
                RolePermission.is_deleted == False,  # noqa: E712
                Permission.is_deleted == False,  # noqa: E712
            )
        )
        result = await db.execute(rp_stmt)
        codes.extend(result.scalars().all())

    # Legacy module grants remain a read-only compatibility fact source. The
    # old module.view flag maps to module:read only; Agent flags and any
    # future write flags are intentionally not promoted here.
    grant_result = await db.execute(
        select(UserModuleGrant.module_code, UserModuleGrant.permissions).where(
            UserModuleGrant.user_id == user_id,
            UserModuleGrant.status == "active",
            UserModuleGrant.is_deleted.is_(False),
        )
    )
    for module_code, grant_permissions in grant_result.all():
        if isinstance(grant_permissions, list) and "module.view" in grant_permissions:
            codes.append(f"{module_code}:read")

    codes = list(dict.fromkeys(codes))

    # ── 按钮级权限（菜单 permission_code，模块:资源:操作）──
    # 1. 角色勾选的按钮菜单权限码直接并入
    # 2. 兼容规则：持 `{module}:write` 自动拥有该模块全部按钮码
    #    （旧角色仅配模块读/写权限时，按钮无需二次勾选即可用）
    button_codes = await _resolve_role_button_codes(db, role_ids)
    if button_codes:
        codes.extend(button_codes)
    code_set = set(codes)
    all_button_codes = await _load_all_button_codes(db)
    for module, module_buttons in all_button_codes.items():
        if f"{module}:write" in code_set:
            for btn in module_buttons:
                if btn not in code_set:
                    codes.append(btn)
                    code_set.add(btn)
    return codes


async def _resolve_role_button_codes(
    db: AsyncSession, role_ids: list[Any]
) -> list[str]:
    """角色勾选按钮菜单的 permission_code（去重保序）。"""
    if not role_ids:
        return []
    stmt = (
        select(Menu.permission_code)
        .join(RoleMenu, RoleMenu.menu_id == Menu.id)
        .where(
            RoleMenu.role_id.in_(role_ids),
            RoleMenu.is_deleted == False,  # noqa: E712
            Menu.is_deleted == False,  # noqa: E712
            Menu.permission_code.is_not(None),
        )
    )
    result = await db.execute(stmt)
    codes = [code for code in result.scalars().all() if code is not None]
    return list(dict.fromkeys(codes))


async def _load_all_button_codes(db: AsyncSession) -> dict[str, list[str]]:
    """全量按钮权限码按模块分组（模块=权限码首段）。"""
    stmt = select(Menu.permission_code).where(
        Menu.is_deleted == False,  # noqa: E712
        Menu.permission_code.is_not(None),
    )
    result = await db.execute(stmt)
    grouped: dict[str, list[str]] = {}
    for code in result.scalars().all():
        if code is None:
            continue
        module = str(code).split(":", 1)[0]
        grouped.setdefault(module, []).append(code)
    return grouped


async def resolve_user_menu_ids(
    db: AsyncSession,
    user_id: Any,
    roles: list[Role] | None = None,
) -> list[Any]:
    """用户可见菜单 ids：多角色关联菜单并集 + 祖先补全（保证树完整）。

    super_admin 由调用方直接返回全量菜单，不进入本函数。
    """
    if roles is None:
        roles = await resolve_user_roles(db, user_id)
    if not roles:
        return []
    role_ids = [r.id for r in roles]
    stmt = select(RoleMenu.menu_id).where(
        RoleMenu.role_id.in_(role_ids),
        RoleMenu.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    menu_ids = set(result.scalars().all())
    if not menu_ids:
        return []

    # 祖先补全：勾选子节点时保证其祖先目录挂在树上
    all_stmt = select(Menu.id, Menu.parent_id).where(
        Menu.is_deleted == False  # noqa: E712
    )
    all_result = await db.execute(all_stmt)
    parent_map = {mid: pid for mid, pid in all_result.all()}

    for mid in list(menu_ids):
        cursor = parent_map.get(mid)
        while cursor is not None and cursor not in menu_ids:
            menu_ids.add(cursor)
            cursor = parent_map.get(cursor)
    return list(menu_ids)


# ─── 启动种子 ─────────────────────────────────────────────────────────


async def seed_permissions(db: AsyncSession) -> None:
    """权限目录 + super_admin 角色种子（幂等）。"""
    # 权限点
    catalog = build_permission_catalog()
    existing_stmt = select(Permission.code).where(
        Permission.is_deleted == False  # noqa: E712
    )
    existing_result = await db.execute(existing_stmt)
    existing_codes = set(existing_result.scalars().all())

    created_perms: list[Permission] = []
    for item in catalog:
        if item["code"] not in existing_codes:
            perm = Permission(
                code=item["code"],
                module=item["module"],
                action=item["action"],
                name=item["name"],
            )
            db.add(perm)
            created_perms.append(perm)
    if created_perms:
        await db.flush()
        logger.info("Seeded %d permission points", len(created_perms))

    # super_admin 角色
    role_stmt = select(Role).where(
        Role.code == SUPER_ADMIN_ROLE_CODE,
        Role.is_deleted == False,  # noqa: E712
    )
    role_result = await db.execute(role_stmt)
    role = role_result.scalar_one_or_none()
    if role is None:
        role = Role(
            name="超级管理员",
            code=SUPER_ADMIN_ROLE_CODE,
            description="拥有全部权限（通配）",
            is_system=True,
        )
        db.add(role)
        await db.flush()
        logger.info("Seeded super_admin role")

    # super_admin 绑定全部权限点（幂等）
    all_perms_stmt = select(Permission).where(
        Permission.is_deleted == False  # noqa: E712
    )
    all_perms_result = await db.execute(all_perms_stmt)
    all_perms = list(all_perms_result.scalars().all())

    rp_stmt = select(RolePermission.permission_id).where(
        RolePermission.role_id == role.id,
        RolePermission.is_deleted == False,  # noqa: E712
    )
    rp_result = await db.execute(rp_stmt)
    bound_ids = set(rp_result.scalars().all())

    for perm in all_perms:
        if perm.id not in bound_ids:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))
    await db.flush()
    await db.commit()


# ─── 菜单种子 ─────────────────────────────────────────────────────────


def _menu_type(node: dict[str, Any]) -> str:
    """种子节点类型推断：有 children → directory，叶子 → menu。"""
    return "directory" if node.get("children") else "menu"


def _flatten_seed_menus(
    nodes: list[dict[str, Any]],
    parent_key: str | None = None,
) -> list[dict[str, Any]]:
    """打平种子树，key 按 `父key:子key` 拼接保证全局唯一；
    _sort_order 记录同级顺序（供种子菜单排序）。"""
    flat: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        key = f"{parent_key}:{node['key']}" if parent_key else node["key"]
        flat.append({**node, "key": key, "_sort_order": index})
        if node.get("children"):
            flat.extend(_flatten_seed_menus(node["children"], parent_key=key))
    return flat


async def seed_menus(db: AsyncSession) -> None:
    """菜单种子（幂等）：按 key 匹配，缺失的目录/菜单插入，已存在的不覆盖。

    种子仅补充缺失项，不修改用户已在管理页调整过的菜单；
    用户自定义菜单（key 为空）不受影响。
    """
    existing_stmt = select(Menu.key).where(
        Menu.key.is_not(None),
        Menu.is_deleted == False,  # noqa: E712
    )
    existing_result = await db.execute(existing_stmt)
    existing_keys = set(existing_result.scalars().all())

    created = 0
    for node in _flatten_seed_menus(SEED_MENUS):
        if node["key"] in existing_keys:
            continue
        menu = Menu(
            key=node["key"],
            name=node["name"],
            type=_menu_type(node),
            route_path=node.get("path") or None,
            icon=node.get("icon"),
            permission_code=node.get("permission_code"),
            sort_order=node.get("_sort_order", 0),
            status=("disabled" if node.get("disabled") else "active"),
        )
        db.add(menu)
        created += 1
    if created:
        await db.flush()

        # 建立父子关系（按 key 查找父节点）
        keyed: dict[str, Menu] = {}
        all_stmt = select(Menu).where(
            Menu.is_deleted == False  # noqa: E712
        )
        all_result = await db.execute(all_stmt)
        for m in all_result.scalars().all():
            if m.key:
                keyed[m.key] = m
        for node in _flatten_seed_menus(SEED_MENUS):
            menu = keyed[node["key"]]
            if ":" in node["key"]:
                parent_key = node["key"].rsplit(":", 1)[0]
                parent = keyed.get(parent_key)
                if parent is not None:
                    menu.parent_id = parent.id
        await db.flush()
        logger.info("Seeded %d menu nodes", created)
    await db.commit()
