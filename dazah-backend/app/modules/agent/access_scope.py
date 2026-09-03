from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import AgentAccessScopeSnapshot
from app.modules.agent.schemas import AgentAccessScopeOut, AgentModuleScopeOut
from app.platform.identity.models import User
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.shared.module_registry import BUSINESS_MODULES, MODULES_BY_CODE


class AgentAccessScopeService:
    def __init__(
        self, permission_repo: PermissionGrantRepository | None = None
    ) -> None:
        self.permission_repo = permission_repo or PermissionGrantRepository()

    async def synchronize(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        actor_id: UUID | None = None,
    ) -> AgentAccessScopeSnapshot:
        from app.modules.agent.tool_registration import ensure_agent_tools_registered
        from app.modules.agent.tools import tool_registry

        ensure_agent_tools_registered()
        user = await db.get(User, user_id)
        if user is None or user.is_deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
        grants = await self.permission_repo.list_grants(db, user_id=user_id)
        grants_by_module = {
            grant.module_code: grant
            for grant in grants
            if grant.status == "active" and grant.module_code in MODULES_BY_CODE
        }
        specs = tool_registry.list()
        registry_version = self._registry_version(
            [spec.public_dict() for spec in specs]
        )
        rollouts = {
            item.module_code: item.status
            for item in await PagePermissionRepository().list_rollouts(db)
        }
        page_grants = await PagePermissionService().effective_grants(db, user=user)
        page_grants_by_key = {grant.page_key: grant for grant in page_grants}
        enforced_modules = {
            module_code
            for module_code, state in rollouts.items()
            if state == "enforced"
        }
        modules = [
            {
                "module_code": module_code,
                "module_name": MODULES_BY_CODE[module_code].name,
                "permissions": sorted(set(grant.permissions or [])),
                "data_scope": dict(grant.data_scope or {}),
            }
            for module_code, grant in sorted(grants_by_module.items())
            if module_code not in enforced_modules
            and "module.view" in set(grant.permissions or [])
        ]
        for module in BUSINESS_MODULES:
            if module.code not in enforced_modules:
                continue
            module_page_grants = [
                grant
                for grant in page_grants
                if grant.module_code == module.code and "access" in grant.permissions
            ]
            if not module_page_grants:
                continue
            modules.append(
                {
                    "module_code": module.code,
                    "module_name": module.name,
                    "permissions": ["page.access"],
                    "data_scope": {
                        "pages": {
                            grant.page_key: grant.data_scope.model_dump()
                            for grant in module_page_grants
                        }
                    },
                }
            )
        if user.role == "admin":
            modules = [
                {
                    "module_code": module.code,
                    "module_name": module.name,
                    "permissions": [
                        "module.view",
                        "page.access",
                        "page.query",
                        "page.operate",
                    ],
                    "data_scope": {"scope_type": "all"},
                }
                for module in BUSINESS_MODULES
            ]
        tool_names: list[str] = []
        workflow_tool_names: list[str] = []
        for spec in specs:
            if (
                user.role != "admin"
                and spec.required_roles
                and user.role not in spec.required_roles
            ):
                continue
            if spec.module is None or user.role == "admin":
                tool_names.append(spec.name)
                if spec.workflow_allowed and not spec.human_decision_required:
                    workflow_tool_names.append(spec.name)
                continue
            if spec.module in enforced_modules:
                if not spec.page_keys:
                    continue
                required_permission = (
                    "operate" if spec.write or spec.sensitive_action else "query"
                )
                matching_grants = [
                    page_grants_by_key.get(page_key) for page_key in spec.page_keys
                ]
                allowed_by_page = any(
                    grant is not None
                    and required_permission in grant.permissions
                    and (
                        spec.sensitive_action is None
                        or spec.sensitive_action in grant.sensitive_actions
                    )
                    for grant in matching_grants
                )
                if not allowed_by_page:
                    continue
                tool_names.append(spec.name)
                if spec.workflow_allowed and not spec.human_decision_required:
                    workflow_tool_names.append(spec.name)
                continue
            # 首批模块仍处于草稿期时，继续执行原有模块权限规则；发布为
            # enforced 后才切换到上面的页面权限规则。
            grant = grants_by_module.get(spec.module)
            if grant is None:
                continue
            permissions = set(grant.permissions or [])
            if "module.view" not in permissions:
                continue
            if spec.permission_key and spec.permission_key not in permissions:
                continue
            tool_names.append(spec.name)
            if (
                "module.agent.automate" in permissions
                and spec.workflow_allowed
                and not spec.human_decision_required
            ):
                workflow_tool_names.append(spec.name)

        snapshot = await self.get_snapshot(db, user_id=user_id, for_update=True)
        now = datetime.now(UTC)
        if snapshot is None:
            snapshot = AgentAccessScopeSnapshot(
                user_id=user_id,
                source_grant_version=user.grant_version,
                agent_scope_version=user.grant_version,
                modules=modules,
                tool_names=sorted(tool_names),
                workflow_tool_names=sorted(workflow_tool_names),
                registry_version=registry_version,
                sync_status="synced",
                synced_at=now,
            )
            snapshot.created_by = actor_id
            snapshot.updated_by = actor_id
            db.add(snapshot)
        else:
            snapshot.source_grant_version = user.grant_version
            snapshot.agent_scope_version = max(
                snapshot.agent_scope_version + 1,
                user.grant_version,
            )
            snapshot.modules = modules
            snapshot.tool_names = sorted(tool_names)
            snapshot.workflow_tool_names = sorted(workflow_tool_names)
            snapshot.registry_version = registry_version
            snapshot.sync_status = "synced"
            snapshot.synced_at = now
            snapshot.last_error = None
            snapshot.updated_by = actor_id
        await db.flush()
        return snapshot

    async def get_current_scope(
        self,
        db: AsyncSession,
        *,
        user: User,
        rebuild_if_stale: bool = True,
    ) -> AgentAccessScopeSnapshot:
        if user.status != "active" or user.is_deleted:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "账户当前不可用")
        snapshot = await self.get_snapshot(db, user_id=user.id)
        current_registry_version = self.current_registry_version()
        is_stale = (
            snapshot is None
            or snapshot.sync_status != "synced"
            or snapshot.source_grant_version != user.grant_version
            or snapshot.registry_version != current_registry_version
        )
        if is_stale and rebuild_if_stale:
            try:
                snapshot = await self.synchronize(db, user_id=user.id, actor_id=user.id)
            except Exception as exc:
                if snapshot is not None:
                    snapshot.sync_status = "failed"
                    snapshot.last_error = str(exc)[:2000]
                    snapshot.updated_by = user.id
                    await db.flush()
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Livzon 访问范围尚未同步，已按安全策略拒绝访问",
                ) from exc
        if (
            snapshot is None
            or snapshot.sync_status != "synced"
            or snapshot.source_grant_version != user.grant_version
            or snapshot.registry_version != current_registry_version
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Livzon 访问范围已过期，已按安全策略拒绝访问",
            )
        return snapshot

    async def require_tool_access(
        self,
        db: AsyncSession,
        *,
        user: User | None,
        tool_name: str,
        module: str | None,
        for_workflow: bool = False,
    ) -> AgentAccessScopeSnapshot | None:
        if module is None:
            return None
        if user is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "业务能力必须使用已登录责任主体执行",
            )
        snapshot = await self.get_current_scope(db, user=user, rebuild_if_stale=False)
        allowed = snapshot.workflow_tool_names if for_workflow else snapshot.tool_names
        if tool_name not in set(allowed or []):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"当前 Livzon 有效范围不允许调用 {tool_name}",
            )
        return snapshot

    async def get_snapshot(
        self,
        db: AsyncSession,
        *,
        user_id: UUID,
        for_update: bool = False,
    ) -> AgentAccessScopeSnapshot | None:
        stmt = select(AgentAccessScopeSnapshot).where(
            AgentAccessScopeSnapshot.user_id == user_id,
            AgentAccessScopeSnapshot.is_deleted.is_(False),
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def scope_out(
        self,
        db: AsyncSession,
        *,
        user: User,
        rebuild_if_stale: bool = True,
    ) -> AgentAccessScopeOut:
        snapshot = await self.get_current_scope(
            db, user=user, rebuild_if_stale=rebuild_if_stale
        )
        return AgentAccessScopeOut(
            user_id=user.id,
            source_grant_version=snapshot.source_grant_version,
            agent_scope_version=snapshot.agent_scope_version,
            registry_version=snapshot.registry_version,
            sync_status=snapshot.sync_status,
            synced_at=snapshot.synced_at,
            last_error=snapshot.last_error,
            modules=[
                AgentModuleScopeOut.model_validate(item) for item in snapshot.modules
            ],
            tool_names=list(snapshot.tool_names or []),
            workflow_tool_names=list(snapshot.workflow_tool_names or []),
        )

    @staticmethod
    def snapshot_out(snapshot: AgentAccessScopeSnapshot) -> AgentAccessScopeOut:
        return AgentAccessScopeOut(
            user_id=snapshot.user_id,
            source_grant_version=snapshot.source_grant_version,
            agent_scope_version=snapshot.agent_scope_version,
            registry_version=snapshot.registry_version,
            sync_status=snapshot.sync_status,
            synced_at=snapshot.synced_at,
            last_error=snapshot.last_error,
            modules=[
                AgentModuleScopeOut.model_validate(item)
                for item in (snapshot.modules or [])
            ],
            tool_names=list(snapshot.tool_names or []),
            workflow_tool_names=list(snapshot.workflow_tool_names or []),
        )

    @staticmethod
    def _registry_version(public_specs: list[dict[str, Any]]) -> str:
        from dataclasses import asdict

        from app.platform.identity.page_lifecycle import load_ledger
        from app.platform.identity.page_policy import (
            PAGE_API_BINDINGS,
            PAGE_DEFINITIONS,
        )

        payload = json.dumps(
            {
                "page_policy_version": 2,
                "tools": public_specs,
                "pages": [asdict(page) for page in PAGE_DEFINITIONS],
                "api_bindings": [asdict(binding) for binding in PAGE_API_BINDINGS],
                "lifecycle": load_ledger(),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    @classmethod
    def current_registry_version(cls) -> str:
        from app.modules.agent.tool_registration import ensure_agent_tools_registered
        from app.modules.agent.tools import tool_registry

        ensure_agent_tools_registered()
        return cls._registry_version(
            [spec.public_dict() for spec in tool_registry.list()]
        )
