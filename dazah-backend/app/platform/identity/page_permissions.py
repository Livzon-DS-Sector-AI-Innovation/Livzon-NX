from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
    canonical_page_key,
    get_page_definition,
    normalize_permissions,
    page_api_catalog_gaps,
    tool_page_bindings,
)
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.platform.identity.schemas import (
    EffectivePageGrantOut,
    PageDataScopeInput,
    PageGrantInput,
    PagePermissionDefinitionOut,
    PagePermissionHealthIssueOut,
    PagePermissionHealthOut,
    PagePermissionHistoryActorOut,
    PagePermissionHistoryChangeOut,
    PagePermissionHistoryItemOut,
    PagePermissionHistoryPageOut,
    PagePermissionRoleSourceOut,
    PermissionModuleRolloutOut,
    PermissionModuleRolloutPreviewOut,
    RolePagePermissionAffectedUserOut,
    RolePagePermissionsOut,
    RolePagePermissionsPreviewOut,
    SensitiveActionDefinitionOut,
    UserPagePermissionsOut,
)
from app.shared.module_registry import MODULES_BY_CODE

REVIEW_PENDING_ROLLOUT_MODULES = frozenset(
    {"hr", "warehouse", "registration", "production"}
)


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

    @staticmethod
    def history_changes(
        old_grants: list[dict[str, Any]], new_grants: list[dict[str, Any]]
    ) -> list[PagePermissionHistoryChangeOut]:
        def canonical(item: dict[str, Any]) -> dict[str, Any]:
            result = dict(item)
            expiry = result.get("sensitive_actions_expires_at")
            if isinstance(expiry, datetime):
                result["sensitive_actions_expires_at"] = expiry.isoformat()
            for field in ("permissions", "sensitive_actions", "department_ids"):
                result[field] = sorted(set(result.get(field) or []))
            return result

        old_by_key = {str(item.get("page_key")): canonical(item) for item in old_grants}
        new_by_key = {str(item.get("page_key")): canonical(item) for item in new_grants}
        changes: list[PagePermissionHistoryChangeOut] = []
        for page_key in sorted(old_by_key.keys() | new_by_key.keys()):
            before = old_by_key.get(page_key)
            after = new_by_key.get(page_key)
            if before == after:
                continue
            if before is None:
                kind = "grant"
                summary = "新增页面授权"
            elif after is None:
                kind = "revoke"
                summary = "移除页面授权"
            else:
                before_values = set(before.get("permissions") or []) | set(
                    before.get("sensitive_actions") or []
                )
                after_values = set(after.get("permissions") or []) | set(
                    after.get("sensitive_actions") or []
                )
                scope_same = before.get("scope_type") == after.get(
                    "scope_type"
                ) and set(before.get("department_ids") or []) == set(
                    after.get("department_ids") or []
                )
                expiry_same = before.get("sensitive_actions_expires_at") == after.get(
                    "sensitive_actions_expires_at"
                )
                changed_fields = [
                    label
                    for field, label in (
                        ("permissions", "权限层级"),
                        ("sensitive_actions", "高风险动作"),
                        ("scope_type", "数据范围"),
                        ("department_ids", "指定部门"),
                        ("sensitive_actions_expires_at", "高风险到期时间"),
                    )
                    if before.get(field) != after.get(field)
                ]
                if before_values < after_values and scope_same and expiry_same:
                    kind = "expand"
                elif after_values < before_values and scope_same and expiry_same:
                    kind = "restrict"
                else:
                    kind = "mixed"
                summary = f"变更：{'、'.join(changed_fields)}"
            definition = get_page_definition(page_key)
            changes.append(
                PagePermissionHistoryChangeOut(
                    page_key=page_key,
                    page_name=definition.page_name if definition else page_key,
                    kind=kind,
                    summary=summary,
                    before=before,
                    after=after,
                )
            )
        return changes

    async def is_super_admin(self, db: AsyncSession, *, user_id: UUID) -> bool:
        # Compatibility method name; both former administrator identities are
        # normalized to User.role by the identity merge migration.
        user = await db.get(User, user_id)
        return bool(user and not user.is_deleted and user.role == "admin")

    async def effective_grants(
        self,
        db: AsyncSession,
        *,
        user: User,
        include_user_overrides: bool = True,
        resolved_roles: list[Role] | None = None,
        role_grant_overrides: dict[UUID, list[dict[str, Any]]] | None = None,
        active_page_keys: set[str] | None = None,
        prefetched_role_grants: list[Any] | None = None,
        prefetched_user_grants: list[Any] | None = None,
    ) -> list[EffectivePageGrantOut]:
        from app.platform.identity.rbac import resolve_user_roles

        roles = (
            resolved_roles
            if resolved_roles is not None
            else await resolve_user_roles(db, user.id)
        )
        active_keys = (
            active_page_keys
            if active_page_keys is not None
            else await self.repo.active_page_keys(db)
        )
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
                    resolution=["系统管理员身份直接授予全部页面权限"],
                )
                for item in PAGE_DEFINITIONS
                if item.page_key in active_keys
            ]

        role_by_id = {role.id: role for role in roles}
        role_grants: list[Any] = list(
            prefetched_role_grants
            if prefetched_role_grants is not None
            else await self.repo.list_role_grants(db, role_ids=list(role_by_id))
        )
        role_grants = [grant for grant in role_grants if grant.role_id in role_by_id]
        for role_id, replacement in (role_grant_overrides or {}).items():
            if role_id not in role_by_id:
                continue
            role_grants = [grant for grant in role_grants if grant.role_id != role_id]
            role_grants.extend(
                SimpleNamespace(role_id=role_id, **grant) for grant in replacement
            )
        merged: dict[str, dict[str, Any]] = {}
        for grant in role_grants:
            page_key = canonical_page_key(grant.page_key)
            definition = get_page_definition(page_key)
            if definition is None or page_key not in active_keys:
                continue
            if (
                grant.scope_type not in definition.supported_scope_types
                or set(grant.permissions or []) - PAGE_PERMISSION_SET
            ):
                continue
            if not grant.permissions and not grant.sensitive_actions:
                continue
            item = merged.setdefault(
                page_key,
                {
                    "permissions": set(),
                    "sensitive_actions": set(),
                    "sensitive_action_expirations": {},
                    "scope_types": set(),
                    "department_ids": set(),
                    "role_names": set(),
                    "role_sources": [],
                },
            )
            item["permissions"].update(grant.permissions or [])
            expires_at = getattr(grant, "sensitive_actions_expires_at", None)
            active_actions = self._active_sensitive_actions(
                grant.sensitive_actions or [], expires_at
            )
            item["sensitive_actions"].update(active_actions)
            for action in active_actions:
                previous_expiry = item["sensitive_action_expirations"].get(action)
                if action not in item["sensitive_action_expirations"]:
                    item["sensitive_action_expirations"][action] = expires_at
                elif previous_expiry is not None and (
                    expires_at is None or expires_at > previous_expiry
                ):
                    item["sensitive_action_expirations"][action] = expires_at
            item["scope_types"].add(grant.scope_type)
            item["department_ids"].update(grant.department_ids or [])
            role = role_by_id.get(grant.role_id)
            if role is not None:
                item["role_names"].add(role.name)
                item["role_sources"].append(
                    PagePermissionRoleSourceOut(
                        role_id=role.id,
                        role_name=role.name,
                        permissions=list(
                            normalize_permissions(list(grant.permissions or []))
                        ),
                        sensitive_actions=sorted(
                            set(active_actions)
                            & {action.key for action in definition.sensitive_actions}
                        ),
                        sensitive_actions_expires_at=expires_at,
                        data_scope=PageDataScopeInput(
                            scope_type=grant.scope_type,
                            department_ids=list(grant.department_ids or []),
                        ),
                    )
                )

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
                sensitive_action_expirations={
                    action: value["sensitive_action_expirations"].get(action)
                    for action in sensitive_actions
                },
                data_scope=PageDataScopeInput(
                    scope_type=scope_type, department_ids=department_ids
                ),
                source="role" if permissions else "none",
                source_role_names=sorted(value["role_names"]),
                role_sources=sorted(
                    value["role_sources"], key=lambda item: item.role_name
                ),
                resolution=[
                    (
                        f"合并 {len(value['role_names'])} 个角色的授权："
                        "权限和高风险动作取并集，"
                        "数据范围按最大可见范围合并"
                        if len(value["role_names"]) > 1
                        else f"由角色「{next(iter(value['role_names']))}」授予"
                    )
                ],
            )

        overrides: list[Any] = []
        if include_user_overrides:
            overrides = (
                prefetched_user_grants
                if prefetched_user_grants is not None
                else await self.repo.list_user_grants(db, user_id=user.id)
            )
        for override in overrides:
            page_key = canonical_page_key(override.page_key)
            definition = get_page_definition(page_key)
            if definition is None or page_key not in active_keys:
                continue
            if (
                override.scope_type not in definition.supported_scope_types
                or set(override.permissions or []) - PAGE_PERMISSION_SET
            ):
                # An obsolete custom override must deny, never reveal the role baseline.
                outputs.pop(page_key, None)
                continue
            permissions = list(normalize_permissions(list(override.permissions or [])))
            allowed_actions = {action.key for action in definition.sensitive_actions}
            override_expiry = getattr(override, "sensitive_actions_expires_at", None)
            sensitive_actions = sorted(
                set(
                    self._active_sensitive_actions(
                        override.sensitive_actions or [], override_expiry
                    )
                )
                & allowed_actions
            )
            if sensitive_actions and "operate" not in permissions:
                permissions = list(normalize_permissions([*permissions, "operate"]))
            baseline = outputs.get(page_key)
            role_names = baseline.source_role_names if baseline else []
            role_sources = baseline.role_sources if baseline else []
            outputs[page_key] = EffectivePageGrantOut(
                page_key=page_key,
                module_code=definition.module_code,
                permissions=permissions,
                sensitive_actions=sensitive_actions,
                sensitive_action_expirations={
                    action: override_expiry for action in sensitive_actions
                },
                data_scope=PageDataScopeInput(
                    scope_type=override.scope_type,
                    department_ids=list(override.department_ids or []),
                ),
                source="user" if permissions else "none",
                source_role_names=role_names,
                role_sources=role_sources,
                resolution=[
                    (
                        "用户覆盖完整替换角色基线（原基线来自："
                        f"{'、'.join(role_names)}）"
                        if role_names
                        else "用户覆盖直接定义该页面权限"
                    ),
                    (
                        "当前覆盖为明确拒绝"
                        if not permissions
                        else "当前覆盖为最终生效结果"
                    ),
                ],
            )
        return sorted(outputs.values(), key=lambda item: item.page_key)

    async def role_permissions_preview(
        self,
        db: AsyncSession,
        *,
        role: Role,
        proposed_grants: list[dict[str, Any]],
        module_access_mode: str = "roles",
    ) -> RolePagePermissionsPreviewOut:
        from app.platform.identity.rbac import resolve_users_roles

        current_grants = await self.repo.list_role_grants(db, role_ids=[role.id])

        def stored_fact(grant: Any) -> tuple[Any, ...]:
            return (
                tuple(grant.permissions or []),
                tuple(sorted(grant.sensitive_actions or [])),
                getattr(grant, "sensitive_actions_expires_at", None),
                grant.scope_type,
                tuple(sorted(grant.department_ids or [])),
            )

        current_by_page = {
            grant.page_key: stored_fact(grant) for grant in current_grants
        }
        proposed_by_page = {
            grant["page_key"]: (
                tuple(grant["permissions"]),
                tuple(grant["sensitive_actions"]),
                grant.get("sensitive_actions_expires_at"),
                grant["scope_type"],
                tuple(sorted(grant["department_ids"])),
            )
            for grant in proposed_grants
        }
        changed_page_keys = {
            page_key
            for page_key in current_by_page.keys() | proposed_by_page.keys()
            if current_by_page.get(page_key) != proposed_by_page.get(page_key)
        }
        changed_modules = {
            definition.module_code
            for page_key in changed_page_keys
            if (definition := get_page_definition(page_key)) is not None
        }

        def effective_facts(
            grants: list[EffectivePageGrantOut], allowed_modules: set[str]
        ) -> set[str]:
            facts: set[str] = set()
            for grant in grants:
                if (
                    grant.page_key not in changed_page_keys
                    or grant.module_code not in allowed_modules
                ):
                    continue
                prefix = grant.page_key
                facts.update(
                    f"{prefix}:permission:{item}" for item in grant.permissions
                )
                facts.update(
                    f"{prefix}:action:{item}" for item in grant.sensitive_actions
                )
                facts.add(f"{prefix}:scope:{grant.data_scope.scope_type}")
                facts.update(
                    f"{prefix}:department:{item}"
                    for item in grant.data_scope.department_ids
                )
            return facts

        users = await self.repo.list_active_users(db)
        roles_by_user = await resolve_users_roles(db, users)
        members = [
            user
            for user in users
            if any(item.id == role.id for item in roles_by_user.get(user.id, []))
        ]
        member_ids = [user.id for user in members]
        all_role_ids = {
            resolved_role.id
            for user in members
            for resolved_role in roles_by_user.get(user.id, [])
        }
        all_role_grants = await self.repo.list_role_grants(
            db, role_ids=list(all_role_ids)
        )
        all_user_grants = await self.repo.list_user_grants_for_users(
            db, user_ids=member_ids
        )
        user_grants_by_user: dict[UUID, list[Any]] = {}
        for grant in all_user_grants:
            user_grants_by_user.setdefault(grant.user_id, []).append(grant)
        active_keys = await self.repo.active_page_keys(db)
        module_access_by_user = (
            {user.id: set(changed_modules) for user in members}
            if module_access_mode == "all"
            else await PermissionGrantRepository().list_module_access_by_user(
                db, user_ids=member_ids, module_codes=changed_modules
            )
        )

        member_count = len(members)
        users_with_overrides = 0
        counts = {"expanded": 0, "restricted": 0, "mixed": 0}
        samples: list[RolePagePermissionAffectedUserOut] = []
        for user in members:
            roles = roles_by_user[user.id]
            overrides = user_grants_by_user.get(user.id, [])
            if any(
                canonical_page_key(item.page_key) in changed_page_keys
                for item in overrides
            ):
                users_with_overrides += 1
            allowed_modules = (
                set(changed_modules)
                if getattr(user, "role", None) == "admin"
                else module_access_by_user.get(user.id, set())
            )
            before = effective_facts(
                await self.effective_grants(
                    db,
                    user=user,
                    resolved_roles=roles,
                    active_page_keys=active_keys,
                    prefetched_role_grants=all_role_grants,
                    prefetched_user_grants=overrides,
                ),
                allowed_modules,
            )
            after = effective_facts(
                await self.effective_grants(
                    db,
                    user=user,
                    resolved_roles=roles,
                    role_grant_overrides={role.id: proposed_grants},
                    active_page_keys=active_keys,
                    prefetched_role_grants=all_role_grants,
                    prefetched_user_grants=overrides,
                ),
                allowed_modules,
            )
            added = bool(after - before)
            removed = bool(before - after)
            if not added and not removed:
                continue
            impact = (
                "mixed" if added and removed else "expanded" if added else "restricted"
            )
            counts[impact] += 1
            if len(samples) < 20:
                samples.append(
                    RolePagePermissionAffectedUserOut(
                        user_id=user.id, user_name=user.name, impact=impact
                    )
                )
        return RolePagePermissionsPreviewOut(
            role_id=role.id,
            grant_version=role.grant_version,
            member_count=member_count,
            affected_user_count=sum(counts.values()),
            expanded_user_count=counts["expanded"],
            restricted_user_count=counts["restricted"],
            mixed_user_count=counts["mixed"],
            users_with_overrides=users_with_overrides,
            affected_user_samples=samples,
        )

    async def user_permissions_out(
        self, db: AsyncSession, *, user: User
    ) -> UserPagePermissionsOut:
        effective = await self.effective_grants(db, user=user)
        custom = await self.repo.list_user_grants(db, user_id=user.id)
        rollouts = await self.repo.list_rollouts(db)
        active_keys = await self.repo.active_page_keys(db)
        rollout_statuses = {item.module_code: item.status for item in rollouts}
        for module_code in REVIEW_PENDING_ROLLOUT_MODULES:
            rollout_statuses.setdefault(module_code, "draft")
        custom_outputs: list[EffectivePageGrantOut] = []
        for grant in custom:
            page_key = canonical_page_key(grant.page_key)
            definition = get_page_definition(page_key)
            if definition is None or page_key not in active_keys:
                continue
            actions = sorted(set(grant.sensitive_actions or []))
            expires_at = getattr(grant, "sensitive_actions_expires_at", None)
            custom_outputs.append(
                EffectivePageGrantOut(
                    page_key=page_key,
                    module_code=definition.module_code,
                    permissions=list(
                        normalize_permissions(list(grant.permissions or []))
                    ),
                    sensitive_actions=actions,
                    sensitive_action_expirations={
                        action: expires_at for action in actions
                    },
                    data_scope=PageDataScopeInput(
                        scope_type=grant.scope_type,
                        department_ids=list(grant.department_ids or []),
                    ),
                    source="user" if grant.permissions else "none",
                    resolution=["用户覆盖的已配置状态"],
                )
            )
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
            custom_grants=sorted(custom_outputs, key=lambda item: item.page_key),
            custom_page_keys=sorted(
                canonical_page_key(grant.page_key) for grant in custom
            ),
            module_rollouts=rollout_statuses,
        )

    async def role_permissions_out(
        self, db: AsyncSession, *, role: Role
    ) -> RolePagePermissionsOut:
        grants = await self.repo.list_role_grants(db, role_ids=[role.id])
        active_keys = await self.repo.active_page_keys(db)
        outputs: list[EffectivePageGrantOut] = []
        for grant in grants:
            page_key = canonical_page_key(grant.page_key)
            definition = get_page_definition(page_key)
            if definition is None or page_key not in active_keys:
                continue
            active_actions = list(grant.sensitive_actions or [])
            outputs.append(
                EffectivePageGrantOut(
                    page_key=page_key,
                    module_code=definition.module_code,
                    permissions=list(
                        normalize_permissions(list(grant.permissions or []))
                    ),
                    sensitive_actions=sorted(set(active_actions)),
                    sensitive_action_expirations={
                        action: getattr(grant, "sensitive_actions_expires_at", None)
                        for action in active_actions
                    },
                    data_scope=PageDataScopeInput(
                        scope_type=grant.scope_type,
                        department_ids=list(grant.department_ids or []),
                    ),
                    source="role",
                    source_role_names=[role.name],
                    role_sources=[
                        PagePermissionRoleSourceOut(
                            role_id=role.id,
                            role_name=role.name,
                            permissions=list(
                                normalize_permissions(list(grant.permissions or []))
                            ),
                            sensitive_actions=sorted(
                                set(
                                    self._active_sensitive_actions(
                                        grant.sensitive_actions or [],
                                        getattr(
                                            grant,
                                            "sensitive_actions_expires_at",
                                            None,
                                        ),
                                    )
                                )
                            ),
                            sensitive_actions_expires_at=getattr(
                                grant, "sensitive_actions_expires_at", None
                            ),
                            data_scope=PageDataScopeInput(
                                scope_type=grant.scope_type,
                                department_ids=list(grant.department_ids or []),
                            ),
                        )
                    ],
                    resolution=[f"由角色「{role.name}」授予"],
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

    async def permission_history(
        self,
        db: AsyncSession,
        *,
        resource_type: str,
        resource_id: UUID,
        limit: int = 50,
        offset: int = 0,
        actor_user_id: UUID | None = None,
        source: str | None = None,
        page_key: str | None = None,
        change_kind: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[PagePermissionHistoryItemOut]:
        logs = await self.repo.list_page_permission_history(
            db,
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
            offset=offset,
            actor_user_id=actor_user_id,
            source=source,
            date_from=date_from,
            date_to=date_to,
        )
        if page_key:
            logs = [
                log
                for log in logs
                if page_key
                in {
                    str(item.get("page_key"))
                    for item in [
                        *list((log.old_value or {}).get("grants") or []),
                        *list((log.new_value or {}).get("grants") or []),
                    ]
                }
            ]
        actor_labels = await self.repo.user_labels_by_ids(
            db, user_ids={log.user_id for log in logs if log.user_id is not None}
        )
        items: list[PagePermissionHistoryItemOut] = []
        for log in logs:
            old_grants = list((log.old_value or {}).get("grants") or [])
            new_grants = list((log.new_value or {}).get("grants") or [])
            source_value = (
                "rollback"
                if log.action.startswith("rollback_")
                else "health_remediation"
                if log.action.startswith("remediate_")
                else "manual"
            )
            items.append(
                PagePermissionHistoryItemOut(
                    id=log.id,
                    actor_user_id=log.user_id,
                    actor_name=actor_labels.get(log.user_id) if log.user_id else None,
                    action=log.action,
                    source=source_value,
                    reason=str((log.new_value or {}).get("reason") or "") or None,
                    grant_version=(log.new_value or {}).get("grant_version"),
                    old_grants=old_grants,
                    grants=new_grants,
                    changes=self.history_changes(old_grants, new_grants),
                    rollback_of=(log.new_value or {}).get("rollback_of"),
                    created_at=log.created_at,
                )
            )
        if change_kind:
            items = [
                item
                for item in items
                if any(change.kind == change_kind for change in item.changes)
            ]
        return items[:limit]

    async def permission_history_page(
        self,
        db: AsyncSession,
        *,
        resource_type: str,
        resource_id: UUID,
        page: int,
        page_size: int,
        actor_user_id: UUID | None = None,
        source: str | None = None,
        page_key: str | None = None,
        change_kind: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> PagePermissionHistoryPageOut:
        offset = (page - 1) * page_size
        is_truncated = False
        if page_key or change_kind:
            base_total = await self.repo.count_page_permission_history(
                db,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_user_id=actor_user_id,
                source=source,
                date_from=date_from,
                date_to=date_to,
            )
            scan_limit = min(base_total, 5000)
            matching = await self.permission_history(
                db,
                resource_type=resource_type,
                resource_id=resource_id,
                limit=scan_limit,
                actor_user_id=actor_user_id,
                source=source,
                page_key=page_key,
                change_kind=change_kind,
                date_from=date_from,
                date_to=date_to,
            )
            is_truncated = base_total > scan_limit
            total = len(matching)
            items = matching[offset : offset + page_size]
        else:
            total = await self.repo.count_page_permission_history(
                db,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_user_id=actor_user_id,
                source=source,
                date_from=date_from,
                date_to=date_to,
            )
            items = await self.permission_history(
                db,
                resource_type=resource_type,
                resource_id=resource_id,
                limit=page_size,
                offset=offset,
                actor_user_id=actor_user_id,
                source=source,
                date_from=date_from,
                date_to=date_to,
            )
        actors = await self.repo.page_permission_history_actors(
            db, resource_type=resource_type, resource_id=resource_id
        )
        return PagePermissionHistoryPageOut(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            actor_options=[
                PagePermissionHistoryActorOut(user_id=user_id, user_name=name)
                for user_id, name in actors.items()
            ],
            is_truncated=is_truncated,
        )

    async def permission_health(self, db: AsyncSession) -> PagePermissionHealthOut:
        from app.platform.identity.rbac import resolve_users_roles

        now = datetime.now(UTC)
        warning_at = now + timedelta(days=30)
        role_grants = await self.repo.list_all_role_grants(db)
        user_grants = await self.repo.list_all_user_grants(db)
        role_ids = {grant.role_id for grant in role_grants}
        user_ids = {grant.user_id for grant in user_grants}
        roles = {
            role.id: role
            for role in await self.repo.list_roles_by_ids(db, role_ids=role_ids)
        }
        users = {
            user.id: user
            for user in await self.repo.list_users_by_ids(db, user_ids=user_ids)
        }
        active_keys = await self.repo.active_page_keys(db)
        active_department_ids = set((await self.repo.department_labels(db)).keys())
        module_codes = {
            definition.module_code
            for grant in user_grants
            if (definition := get_page_definition(grant.page_key)) is not None
        }
        module_access = await PermissionGrantRepository().list_module_access_by_user(
            db, user_ids=list(user_ids), module_codes=module_codes
        )
        roles_by_user = await resolve_users_roles(db, list(users.values()))
        baseline_by_user: dict[UUID, dict[str, EffectivePageGrantOut]] = {}
        for user in users.values():
            baseline_by_user[user.id] = {
                grant.page_key: grant
                for grant in await self.effective_grants(
                    db,
                    user=user,
                    include_user_overrides=False,
                    resolved_roles=roles_by_user.get(user.id, []),
                    active_page_keys=active_keys,
                    prefetched_role_grants=role_grants,
                )
            }

        issues: list[PagePermissionHealthIssueOut] = []

        def add_issue(
            *,
            code: str,
            severity: str,
            target_type: str,
            target_id: UUID,
            target_name: str,
            grant: Any,
            detail: str,
        ) -> None:
            definition = get_page_definition(grant.page_key)
            target = (
                roles.get(target_id) if target_type == "role" else users.get(target_id)
            )
            remediation = (
                "remove_grant"
                if code in {"retired_page", "redundant_user_override"}
                else "prune_departments"
                if code == "invalid_department"
                else "edit"
            )
            issues.append(
                PagePermissionHealthIssueOut(
                    code=code,
                    severity=severity,
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    page_key=grant.page_key,
                    page_name=(definition.page_name if definition else grant.page_key),
                    module_code=definition.module_code if definition else None,
                    detail=detail,
                    grant_version=getattr(target, "grant_version", 0),
                    remediation=remediation,
                )
            )

        def inspect_common(
            grant: Any, target_type: str, target_id: UUID, target_name: str
        ) -> None:
            if canonical_page_key(grant.page_key) not in active_keys:
                add_issue(
                    code="retired_page",
                    severity="error",
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    grant=grant,
                    detail="页面已停用、不可路由或未同步，授权不会生效",
                )
            missing_departments = (
                set(grant.department_ids or []) - active_department_ids
            )
            if missing_departments:
                add_issue(
                    code="invalid_department",
                    severity="error",
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    grant=grant,
                    detail=f"包含 {len(missing_departments)} 个已失效部门",
                )
            actions = list(grant.sensitive_actions or [])
            expires_at = getattr(grant, "sensitive_actions_expires_at", None)
            if not actions:
                return
            if expires_at is None:
                add_issue(
                    code="sensitive_without_expiry",
                    severity="warning",
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    grant=grant,
                    detail="高风险动作尚未设置到期时间",
                )
                return
            expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
            if expiry <= now:
                add_issue(
                    code="sensitive_expired",
                    severity="error",
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    grant=grant,
                    detail="高风险动作授权已到期并停止生效",
                )
            elif expiry <= warning_at:
                add_issue(
                    code="sensitive_expiring",
                    severity="warning",
                    target_type=target_type,
                    target_id=target_id,
                    target_name=target_name,
                    grant=grant,
                    detail="高风险动作授权将在 30 天内到期",
                )

        for role_grant in role_grants:
            role = roles.get(role_grant.role_id)
            inspect_common(
                role_grant,
                "role",
                role_grant.role_id,
                role.name if role else "已删除角色",
            )
        for user_grant in user_grants:
            target_user = users.get(user_grant.user_id)
            target_name = target_user.name if target_user else "已删除用户"
            inspect_common(user_grant, "user", user_grant.user_id, target_name)
            definition = get_page_definition(user_grant.page_key)
            if (
                definition
                and user_grant.permissions
                and definition.module_code
                not in module_access.get(user_grant.user_id, set())
                and getattr(target_user, "role", None) != "admin"
            ):
                add_issue(
                    code="missing_module_access",
                    severity="warning",
                    target_type="user",
                    target_id=user_grant.user_id,
                    target_name=target_name,
                    grant=user_grant,
                    detail="页面已授权，但用户没有对应模块入口",
                )
            baseline = baseline_by_user.get(user_grant.user_id, {}).get(
                canonical_page_key(user_grant.page_key)
            )
            if baseline and user_grant.permissions:
                current_actions = sorted(
                    self._active_sensitive_actions(
                        user_grant.sensitive_actions or [],
                        getattr(user_grant, "sensitive_actions_expires_at", None),
                    )
                )
                if (
                    list(normalize_permissions(user_grant.permissions or []))
                    == baseline.permissions
                    and current_actions == baseline.sensitive_actions
                    and user_grant.scope_type == baseline.data_scope.scope_type
                    and sorted(user_grant.department_ids or [])
                    == sorted(baseline.data_scope.department_ids)
                ):
                    add_issue(
                        code="redundant_user_override",
                        severity="warning",
                        target_type="user",
                        target_id=user_grant.user_id,
                        target_name=target_name,
                        grant=user_grant,
                        detail="用户覆盖与角色基线相同，可恢复为角色基线",
                    )
        issues.sort(
            key=lambda item: (
                item.severity != "error",
                item.target_type,
                item.target_name,
                item.page_key,
            )
        )
        return PagePermissionHealthOut(
            checked_at=now,
            issue_count=len(issues),
            error_count=sum(item.severity == "error" for item in issues),
            warning_count=sum(item.severity == "warning" for item in issues),
            issues=issues,
        )

    def normalize_inputs(
        self, grants: list[PageGrantInput], *, allow_inherit: bool
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for grant in grants:
            page_key = canonical_page_key(grant.page_key)
            if page_key in seen:
                raise HTTPException(400, f"页面授权重复：{grant.page_key}")
            seen.add(page_key)
            definition = get_page_definition(page_key)
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
                    "page_key": page_key,
                    "permissions": permissions,
                    "sensitive_actions": sorted(set(grant.sensitive_actions)),
                    "sensitive_actions_expires_at": (
                        grant.sensitive_actions_expires_at
                    ),
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

    @staticmethod
    def _active_sensitive_actions(
        actions: list[str], expires_at: datetime | None
    ) -> list[str]:
        if expires_at is None:
            return list(actions)
        normalized_expiry = (
            expires_at.replace(tzinfo=UTC)
            if expires_at.tzinfo is None
            else expires_at.astimezone(UTC)
        )
        return list(actions) if normalized_expiry > datetime.now(UTC) else []

    async def rollout_out(
        self, db: AsyncSession, *, module_code: str
    ) -> PermissionModuleRolloutOut:
        rollout = await self.repo.get_rollout(db, module_code=module_code)
        if rollout is None:
            return PermissionModuleRolloutOut(
                module_code=module_code,
                status=(
                    "draft"
                    if module_code in REVIEW_PENDING_ROLLOUT_MODULES
                    else "legacy"
                ),
                version=0,
            )
        return PermissionModuleRolloutOut.model_validate(rollout, from_attributes=True)

    async def rollout_preview(
        self, db: AsyncSession, *, module_code: str
    ) -> PermissionModuleRolloutPreviewOut:
        from app.platform.identity.rbac import resolve_users_roles

        pages = PAGES_BY_MODULE.get(module_code, ())
        rollout = await self.rollout_out(db, module_code=module_code)
        users = await self.repo.list_active_users(db)
        roles_by_user = await resolve_users_roles(db, users) if users else {}
        role_grants = (
            await self.repo.list_role_grants(
                db,
                role_ids=list(
                    {role.id for roles in roles_by_user.values() for role in roles}
                ),
            )
            if users
            else []
        )
        user_grants = (
            await self.repo.list_user_grants_for_users(
                db, user_ids=[user.id for user in users]
            )
            if users
            else []
        )
        user_grants_by_user: dict[UUID, list[Any]] = {}
        for grant in user_grants:
            user_grants_by_user.setdefault(grant.user_id, []).append(grant)
        active_keys = await self.repo.active_page_keys(db)
        without_access = 0
        authorization_facts = []
        for user in users:
            grants = await self.effective_grants(
                db,
                user=user,
                resolved_roles=roles_by_user.get(user.id, []),
                active_page_keys=active_keys,
                prefetched_role_grants=role_grants,
                prefetched_user_grants=user_grants_by_user.get(user.id, []),
            )
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
        menu_by_key = {
            canonical_page_key(item.key): item for item in menu_catalog if item.key
        }
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
            elif canonical_page_key(menu.key) not in page_by_key:
                gaps.append(f"新增菜单页面尚未接入权限登记：{menu.name}（{menu.key}）")
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
                definition = PAGES_BY_KEY.get(canonical_page_key(page_key))
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
