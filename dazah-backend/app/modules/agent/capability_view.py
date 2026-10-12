"""Live, non-executable capability explanations for users and administrators."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService
from app.shared.module_registry import BUSINESS_MODULES

from .access_scope import AgentAccessScopeService
from .catalog import ToolCatalogService
from .models import AgentAccessScopeSnapshot, AgentToolCatalog
from .schemas import (
    AgentCapabilityModuleOut,
    AgentCapabilityOut,
    AgentCapabilityViewOut,
)
from .tools import tool_registry


class AgentCapabilityViewService:
    async def view(
        self, db: AsyncSession, *, user: User, include_excluded: bool = False
    ) -> AgentCapabilityViewOut:
        if user.status != "active" or user.is_deleted:
            raise HTTPException(403, "账户当前不可用")
        await ToolCatalogService().synchronize(db)
        scope_service = AgentAccessScopeService()
        sync_status = "synced"
        snapshot: AgentAccessScopeSnapshot | None
        try:
            snapshot = await scope_service.get_current_scope(db, user=user)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            snapshot = await scope_service.get_snapshot(db, user_id=user.id)
            sync_status = "failed"
        allowed = (
            set(snapshot.tool_names or [])
            if snapshot and sync_status == "synced"
            else set()
        )
        grants = await PagePermissionService().effective_grants(db, user=user)
        rows = (await db.execute(select(AgentToolCatalog))).scalars().all()
        enabled = {
            row.operation
            for row in rows
            if row.status == "active" and row.admin_enabled
        }
        tools = []
        for spec in tool_registry.list():
            state = (
                "sync_failed"
                if sync_status != "synced"
                else "disabled"
                if spec.name not in enabled
                else "available"
                if spec.name in allowed
                else "unauthorized"
            )
            required = "operate" if spec.write or spec.sensitive_action else "query"
            sources = [
                grant
                for grant in grants
                if grant.page_key in spec.page_keys
                and required in grant.permissions
                and (
                    not spec.sensitive_action
                    or spec.sensitive_action in grant.sensitive_actions
                )
            ]
            tools.append(
                AgentCapabilityOut(
                    operation=spec.name,
                    summary=spec.summary,
                    module=spec.module,
                    state=state,
                    write=spec.write,
                    confirmation_required=spec.confirmation_required,
                    human_decision_required=spec.human_decision_required,
                    workflow_allowed=spec.workflow_allowed
                    and not spec.human_decision_required,
                    page_keys=list(spec.page_keys),
                    permission_sources=sources,
                )
            )
        if include_excluded:
            for spec, reason in tool_registry.excluded():
                tools.append(
                    AgentCapabilityOut(
                        operation=spec.name,
                        summary=spec.summary,
                        module=spec.module,
                        state="not_integrated",
                        reason=reason,
                        write=spec.write,
                        confirmation_required=spec.confirmation_required,
                        human_decision_required=spec.human_decision_required,
                        workflow_allowed=False,
                        page_keys=list(spec.page_keys),
                    )
                )
        modules = []
        for module in BUSINESS_MODULES:
            module_tools = [tool for tool in tools if tool.module == module.code]
            live = [tool for tool in module_tools if tool.state != "not_integrated"]
            modules.append(
                AgentCapabilityModuleOut(
                    module_code=module.code,
                    module_name=module.name,
                    state=(
                        "not_integrated"
                        if not live
                        else "available"
                        if any(tool.state == "available" for tool in live)
                        else "sync_failed"
                        if sync_status != "synced"
                        else "disabled"
                        if all(tool.state == "disabled" for tool in live)
                        else "unauthorized"
                    ),
                    available_count=sum(tool.state == "available" for tool in live),
                    registered_count=len(live),
                )
            )
        return AgentCapabilityViewOut(
            user_id=user.id,
            source_grant_version=user.grant_version,
            agent_scope_version=snapshot.agent_scope_version if snapshot else None,
            sync_status=sync_status,
            synced_at=snapshot.synced_at if snapshot else None,
            modules=modules,
            tools=tools,
        )

    async def diagnose(
        self, db: AsyncSession, *, actor: User, user_id: UUID
    ) -> AgentCapabilityViewOut:
        if actor.role != "admin":
            raise HTTPException(403, "仅管理员可诊断用户能力范围")
        user = await db.get(User, user_id)
        if (
            user is None
            or user.is_deleted
            or (user.tenant_key or "default") != (actor.tenant_key or "default")
        ):
            raise HTTPException(404, "用户不存在")
        return await self.view(db, user=user, include_excluded=True)
