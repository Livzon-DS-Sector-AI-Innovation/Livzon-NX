from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import Role, User
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_policy import (
    PAGE_DEFINITIONS,
    PAGE_PERMISSION_SET,
    PAGES_BY_KEY,
    PAGES_BY_MODULE,
    PageDefinition,
    api_bindings_for_module,
    api_route_catalog,
    get_page_definition,
    normalize_permissions,
    page_api_catalog_gaps,
    tool_page_bindings,
)
from app.platform.identity.schemas import (
    EffectivePageGrantOut,
    PageDataScopeInput,
    PageGrantInput,
    PagePermissionDefinitionOut,
    PermissionModuleRolloutOut,
    PermissionModuleRolloutPreviewOut,
    RolePagePermissionsOut,
    SensitiveActionDefinitionOut,
    UserPagePermissionsOut,
)
from app.shared.module_registry import MODULES_BY_CODE


def _definition_out(item: PageDefinition) -> PagePermissionDefinitionOut:
    return PagePermissionDefinitionOut(
        page_key=item.page_key,
        module_code=item.module_code,
        page_name=item.page_name,
        route_path=item.route_path,
        supported_scope_types=list(item.supported_scope_types),
        sensitive_actions=[
            SensitiveActionDefinitionOut(
                key=action.key,
                name=action.name,
                category=action.category,
                description=action.description,
            )
            for action in item.sensitive_actions
        ],
    )


class PagePermissionService:
    def __init__(self, repo: PagePermissionRepository | None = None) -> None:
        self.repo = repo or PagePermissionRepository()

    async def is_super_admin(self, db: AsyncSession, *, user_id: UUID) -> bool:
        # Compatibility method name; both former administrator identities are
        # normalized to User.role by the identity merge migration.
        user = await db.get(User, user_id)
        return bool(user and not user.is_deleted and user.role == "admin")

    async def effective_grants(
        self, db: AsyncSession, *, user: User, include_user_overrides: bool = True
    ) -> list[EffectivePageGrantOut]:
        from app.platform.identity.rbac import resolve_user_roles

        roles = await resolve_user_roles(db, user.id)
        active_keys = await self.repo.active_page_keys(db)
        if getattr(user, "role", None) == "admin" or any(
            role.code == "super_admin" for role in roles
        ):
            return [
                EffectivePageGrantOut(
                    page_key=item.page_key,
                    module_code=item.module_code,
                    permissions=["access", "query", "operate"],
                    sensitive_actions=[action.key for action in item.sensitive_actions],
                    data_scope=PageDataScopeInput(
                        scope_type="all"
                        if "all" in item.supported_scope_types
                        else "not_applicable"
                    ),
                    source="super_admin",
                    source_role_names=["系统管理员"],
                )
                for item in PAGE_DEFINITIONS
                if item.page_key in active_keys
            ]

        role_by_id = {role.id: role for role in roles}
        role_grants = await self.repo.list_role_grants(db, role_ids=list(role_by_id))
        merged: dict[str, dict[str, Any]] = {}
        for grant in role_grants:
            definition = get_page_definition(grant.page_key)
            if definition is None or grant.page_key not in active_keys:
                continue
            if (
                grant.scope_type not in definition.supported_scope_types
                or set(grant.permissions or []) - PAGE_PERMISSION_SET
            ):
                continue
            if not grant.permissions and not grant.sensitive_actions:
                continue
            item = merged.setdefault(
                grant.page_key,
                {
                    "permissions": set(),
                    "sensitive_actions": set(),
                    "scope_types": set(),
                    "department_ids": set(),
                    "role_names": set(),
                },
            )
            item["permissions"].update(grant.permissions or [])
            item["sensitive_actions"].update(grant.sensitive_actions or [])
            item["scope_types"].add(grant.scope_type)
            item["department_ids"].update(grant.department_ids or [])
            role = role_by_id.get(grant.role_id)
            if role is not None:
                item["role_names"].add(role.name)

        outputs: dict[str, EffectivePageGrantOut] = {}
        for page_key, value in merged.items():
            definition = PAGES_BY_KEY[page_key]
            permissions = list(normalize_permissions(list(value["permissions"])))
            allowed_actions = {action.key for action in definition.sensitive_actions}
            sensitive_actions = sorted(value["sensitive_actions"] & allowed_actions)
            if sensitive_actions and "operate" not in permissions:
                permissions = list(normalize_permissions([*permissions, "operate"]))
            scope_type, department_ids = self._merge_role_scopes(
                value["scope_types"],
                value["department_ids"],
                own_department_ids=self._user_department_ids(user),
            )
            outputs[page_key] = EffectivePageGrantOut(
                page_key=page_key,
                module_code=definition.module_code,
                permissions=permissions,
                sensitive_actions=sensitive_actions,
                data_scope=PageDataScopeInput(
                    scope_type=scope_type, department_ids=department_ids
                ),
                source="role" if permissions else "none",
                source_role_names=sorted(value["role_names"]),
            )

        overrides = (
            await self.repo.list_user_grants(db, user_id=user.id)
            if include_user_overrides
            else []
        )
        for override in overrides:
            definition = get_page_definition(override.page_key)
            if definition is None or override.page_key not in active_keys:
                continue
            if (
                override.scope_type not in definition.supported_scope_types
                or set(override.permissions or []) - PAGE_PERMISSION_SET
            ):
                # An obsolete custom override must deny, never reveal the role baseline.
                outputs.pop(override.page_key, None)
                continue
            permissions = list(normalize_permissions(list(override.permissions or [])))
            allowed_actions = {action.key for action in definition.sensitive_actions}
            sensitive_actions = sorted(
                set(override.sensitive_actions or []) & allowed_actions
            )
            if sensitive_actions and "operate" not in permissions:
                permissions = list(normalize_permissions([*permissions, "operate"]))
            outputs[override.page_key] = EffectivePageGrantOut(
                page_key=override.page_key,
                module_code=definition.module_code,
                permissions=permissions,
                sensitive_actions=sensitive_actions,
                data_scope=PageDataScopeInput(
                    scope_type=override.scope_type,
                    department_ids=list(override.department_ids or []),
                ),
                source="user" if permissions else "none",
                source_role_names=[],
            )
        return sorted(outputs.values(), key=lambda item: item.page_key)

    async def user_permissions_out(
        self, db: AsyncSession, *, user: User
    ) -> UserPagePermissionsOut:
        effective = await self.effective_grants(db, user=user)
        custom = await self.repo.list_user_grants(db, user_id=user.id)
        rollouts = await self.repo.list_rollouts(db)
        active_keys = await self.repo.active_page_keys(db)
        return UserPagePermissionsOut(
            user_id=user.id,
            grant_version=user.grant_version,
            definitions=[
                _definition_out(item)
                for item in PAGE_DEFINITIONS
                if item.page_key in active_keys
            ],
            grants=effective,
            role_grants=await self.effective_grants(
                db, user=user, include_user_overrides=False
            ),
            custom_page_keys=sorted(grant.page_key for grant in custom),
            module_rollouts={item.module_code: item.status for item in rollouts},
        )

    async def role_permissions_out(
        self, db: AsyncSession, *, role: Role
    ) -> RolePagePermissionsOut:
        grants = await self.repo.list_role_grants(db, role_ids=[role.id])
        active_keys = await self.repo.active_page_keys(db)
        outputs: list[EffectivePageGrantOut] = []
        for grant in grants:
            definition = get_page_definition(grant.page_key)
            if definition is None or grant.page_key not in active_keys:
                continue
            outputs.append(
                EffectivePageGrantOut(
                    page_key=grant.page_key,
                    module_code=definition.module_code,
                    permissions=list(
                        normalize_permissions(list(grant.permissions or []))
                    ),
                    sensitive_actions=sorted(set(grant.sensitive_actions or [])),
                    data_scope=PageDataScopeInput(
                        scope_type=grant.scope_type,
                        department_ids=list(grant.department_ids or []),
                    ),
                    source="role",
                    source_role_names=[role.name],
                )
            )
        return RolePagePermissionsOut(
            role_id=role.id,
            grant_version=role.grant_version,
            definitions=[
                _definition_out(item)
                for item in PAGE_DEFINITIONS
                if item.page_key in active_keys
            ],
            grants=sorted(outputs, key=lambda item: item.page_key),
        )

    def normalize_inputs(
        self, grants: list[PageGrantInput], *, allow_inherit: bool
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for grant in grants:
            if grant.page_key in seen:
                raise HTTPException(400, f"页面授权重复：{grant.page_key}")
            seen.add(grant.page_key)
            definition = get_page_definition(grant.page_key)
            if definition is None:
                raise HTTPException(400, f"未知菜单页面：{grant.page_key}")
            if grant.mode == "inherit":
                if not allow_inherit:
                    raise HTTPException(400, "角色授权不支持继承模式")
                continue
            try:
                permissions = list(normalize_permissions(grant.permissions))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            allowed_actions = {action.key for action in definition.sensitive_actions}
            unknown_actions = set(grant.sensitive_actions) - allowed_actions
            if unknown_actions:
                raise HTTPException(
                    400,
                    f"{definition.page_name} 不支持操作："
                    f"{', '.join(sorted(unknown_actions))}",
                )
            if grant.sensitive_actions:
                permissions = list(normalize_permissions([*permissions, "operate"]))
            if grant.data_scope.scope_type not in definition.supported_scope_types:
                raise HTTPException(
                    400,
                    f"{definition.page_name} 不支持数据范围 "
                    f"{grant.data_scope.scope_type}",
                )
            normalized.append(
                {
                    "page_key": grant.page_key,
                    "permissions": permissions,
                    "sensitive_actions": sorted(set(grant.sensitive_actions)),
                    "scope_type": grant.data_scope.scope_type,
                    "department_ids": grant.data_scope.department_ids,
                }
            )
        return sorted(normalized, key=lambda item: item["page_key"])

    async def validate_department_ids(
        self, db: AsyncSession, *, grants: list[dict[str, Any]]
    ) -> None:
        active_keys = await self.repo.active_page_keys(db)
        if any(grant["page_key"] not in active_keys for grant in grants):
            raise HTTPException(
                400, "授权中包含已停用、不可路由或尚未同步的菜单页面，请刷新后重试"
            )
        requested = {
            department_id
            for grant in grants
            for department_id in grant.get("department_ids", [])
        }
        existing = await self.repo.existing_department_ids(db, department_ids=requested)
        missing = requested - existing
        if missing:
            raise HTTPException(
                400,
                f"包含不存在或已停用的部门：{', '.join(sorted(missing))}",
            )

    async def rollout_out(
        self, db: AsyncSession, *, module_code: str
    ) -> PermissionModuleRolloutOut:
        rollout = await self.repo.get_rollout(db, module_code=module_code)
        if rollout is None:
            return PermissionModuleRolloutOut(
                module_code=module_code, status="legacy", version=0
            )
        return PermissionModuleRolloutOut.model_validate(rollout, from_attributes=True)

    async def rollout_preview(
        self, db: AsyncSession, *, module_code: str
    ) -> PermissionModuleRolloutPreviewOut:
        pages = PAGES_BY_MODULE.get(module_code, ())
        rollout = await self.rollout_out(db, module_code=module_code)
        users = await self.repo.list_active_users(db)
        without_access = 0
        authorization_facts = []
        for user in users:
            grants = await self.effective_grants(db, user=user)
            authorization_facts.append(
                {
                    "user_id": str(user.id),
                    "version": user.grant_version,
                    "grants": [
                        item.model_dump(mode="json")
                        for item in grants
                        if item.module_code == module_code
                    ],
                }
            )
            if not any(
                item.module_code == module_code and "access" in item.permissions
                for item in grants
            ):
                without_access += 1
        gaps = [] if pages else ["未登记有效菜单页面"]
        menu_catalog = await self.repo.active_menu_page_catalog(db)
        menu_by_key = {item.key: item for item in menu_catalog if item.key}
        page_by_key = {page.page_key: page for page in pages}
        module_roots = {page.page_key.split(":", 1)[0] for page in pages}
        module = MODULES_BY_CODE.get(module_code)
        if not module_roots and module:
            module_roots.add(module.path.strip("/").split("/", 1)[0])
        module_menu_catalog = [
            item for item in menu_catalog if item.root_key in module_roots
        ]
        for page in pages:
            menu = menu_by_key.get(page.page_key)
            if menu is None:
                gaps.append(
                    f"权限登记缺少有效菜单绑定：{page.page_name}（{page.page_key}）"
                )
            elif menu.route_path != page.route_path:
                gaps.append(
                    "菜单页面路由与权限登记不一致："
                    f"{page.page_name}（菜单 {menu.route_path}；"
                    f"登记 {page.route_path}）"
                )
            elif menu.root_key not in module_roots:
                gaps.append(
                    "菜单页面所属目录与权限登记不一致："
                    f"{page.page_name}（当前目录 {menu.root_key or '未知'}）"
                )
        for menu in module_menu_catalog:
            menu_label = f"{menu.name}（{menu.route_path}）"
            if not menu.key:
                gaps.append(f"菜单页面缺少稳定权限标识：{menu_label}")
            elif menu.key not in page_by_key:
                gaps.append(
                    f"新增菜单页面尚未接入权限登记：{menu.name}（{menu.key}）"
                )
        gaps.extend(page_api_catalog_gaps(module_code))
        tools = tool_page_bindings()
        if tools is None:
            gaps.append("Livzon 工具目录尚未加载，无法核对发布契约")
        for spec in tools or []:
            if spec.module_code != module_code:
                continue
            if not spec.page_keys:
                gaps.append(f"Livzon 工具未绑定菜单页面：{spec.summary}")
            for page_key in spec.page_keys:
                definition = PAGES_BY_KEY.get(page_key)
                if definition is None or definition.module_code != module_code:
                    gaps.append(f"Livzon 工具页面绑定无效：{spec.summary}")
                    continue
                if spec.sensitive_action and spec.sensitive_action not in {
                    action.key for action in definition.sensitive_actions
                }:
                    gaps.append(f"Livzon 工具高风险动作绑定无效：{spec.summary}")
        payload = {
            "module_code": module_code,
            "version": rollout.version,
            "page_keys": [item.page_key for item in pages],
            "user_count": len(users),
            "users_without_access": without_access,
            "catalog_gaps": gaps,
            "menu_catalog": [asdict(item) for item in module_menu_catalog],
            "page_policies": [asdict(item) for item in pages],
            "api_policies": [
                asdict(item) for item in api_bindings_for_module(module_code)
            ],
            "actual_api_routes": api_route_catalog(module_code),
            "tool_policies": [
                asdict(item) for item in tools or [] if item.module_code == module_code
            ],
            "authorization_facts": sorted(
                authorization_facts, key=lambda item: str(item["user_id"])
            ),
        }
        preview_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()
        ).hexdigest()
        return PermissionModuleRolloutPreviewOut(
            module_code=module_code,
            current_status=rollout.status,
            current_version=rollout.version,
            preview_hash=preview_hash,
            page_count=len(pages),
            user_count=len(users),
            users_without_access=without_access,
            catalog_gaps=gaps,
        )

    @staticmethod
    def _merge_role_scopes(
        scope_types: set[str],
        department_ids: set[str],
        *,
        own_department_ids: set[str] | None = None,
    ) -> tuple[str, list[str]]:
        if "all" in scope_types:
            return "all", []
        if "departments" in scope_types and department_ids:
            own_ids = own_department_ids or set()
            return "departments", sorted(
                department_ids
                | (own_ids if "department_tree" in scope_types else set())
            )
        if "department_tree" in scope_types:
            return "department_tree", []
        if "self" in scope_types:
            return "self", []
        return "not_applicable", []

    @staticmethod
    def _user_department_ids(user: User) -> set[str]:
        try:
            values = json.loads(user.feishu_department_ids or "[]")
        except (ValueError, TypeError, AttributeError):
            return set()
        return (
            {item for item in values if isinstance(item, str) and item}
            if isinstance(values, list)
            else set()
        )

    @staticmethod
    def mark_rollout(
        rollout: Any,
        *,
        enforced: bool,
        actor_id: UUID,
        reason: str,
    ) -> None:
        rollout.status = "enforced" if enforced else "legacy"
        rollout.version += 1
        rollout.published_at = datetime.now(UTC)
        rollout.published_by = actor_id
        rollout.last_reason = reason
        rollout.updated_by = actor_id
