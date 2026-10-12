"""Administrator inventory; page binding coverage is not functional completeness."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import User
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import PAGE_DEFINITIONS
from app.shared.module_registry import BUSINESS_MODULES

from .catalog import ToolCatalogService
from .models import AgentToolCatalog
from .schemas import (
    AgentCoveragePageOut,
    AgentCoverageToolOut,
    AgentModuleCoverageOut,
    AgentModuleCoverageViewOut,
)
from .tool_policy import tool_exclusion_reason
from .tools import tool_registry

# This management inventory intentionally omits these business modules.
_HIDDEN_COVERAGE_MODULES = frozenset(
    {"regulatory_tracker", "product", "environment", "dossier_writer"}
)


class AgentModuleCoverageService:
    async def view(
        self, db: AsyncSession, *, actor: User
    ) -> AgentModuleCoverageViewOut:
        if actor.role != "admin" or actor.status != "active" or actor.is_deleted:
            raise HTTPException(403, "仅管理员可查看模块接入情况")
        await ToolCatalogService().synchronize(db)
        active_pages = {
            grant.page_key
            for grant in await PagePermissionService().effective_grants(db, user=actor)
        }
        rows = (await db.execute(select(AgentToolCatalog))).scalars().all()
        enabled = {
            row.operation
            for row in rows
            if row.status == "active" and row.admin_enabled and not row.is_deleted
        }
        live = tool_registry.list()
        excluded = tool_registry.excluded()
        modules = []
        for module in BUSINESS_MODULES:
            if module.code in _HIDDEN_COVERAGE_MODULES:
                continue
            specs = [spec for spec in live if spec.module == module.code]
            enabled_specs = [spec for spec in specs if spec.name in enabled]
            closed = [
                (spec, reason)
                for spec, reason in excluded
                if spec.module == module.code
            ]
            pages = []
            for page in PAGE_DEFINITIONS:
                if (
                    page.module_code != module.code
                    or page.page_key not in active_pages
                    or tool_exclusion_reason(
                        name="",
                        path=page.route_path,
                        page_keys=(page.page_key,),
                        module=module.code,
                    )
                ):
                    continue
                pages.append(
                    AgentCoveragePageOut(
                        page_key=page.page_key,
                        page_name=page.page_name,
                        route_path=page.route_path,
                        registered_count=sum(
                            page.page_key in spec.page_keys for spec in specs
                        ),
                        enabled_count=sum(
                            page.page_key in spec.page_keys for spec in enabled_specs
                        ),
                    )
                )
            covered = sum(page.registered_count > 0 for page in pages)
            enabled_pages = sum(page.enabled_count > 0 for page in pages)
            tools = [
                AgentCoverageToolOut(
                    operation=spec.name,
                    summary=spec.summary,
                    state="enabled" if spec.name in enabled else "disabled",
                    write=spec.write,
                    human_decision_required=spec.human_decision_required,
                )
                for spec in specs
            ]
            tools.extend(
                AgentCoverageToolOut(
                    operation=spec.name,
                    summary=spec.summary,
                    state="excluded",
                    reason=reason,
                    write=spec.write,
                    human_decision_required=spec.human_decision_required,
                )
                for spec, reason in closed
            )
            modules.append(
                AgentModuleCoverageOut(
                    module_code=module.code,
                    module_name=module.name,
                    state="not_integrated"
                    if not specs
                    else "disabled"
                    if not enabled_specs
                    else "integrated"
                    if pages and covered == len(pages)
                    else "partial",
                    registered_count=len(specs),
                    enabled_count=len(enabled_specs),
                    excluded_count=len(closed),
                    total_pages=len(pages),
                    covered_pages=covered,
                    enabled_pages=enabled_pages,
                    coverage_percent=round(covered * 100 / len(pages), 1)
                    if pages
                    else None,
                    pages=pages,
                    tools=tools,
                )
            )
        total = sum(module.total_pages for module in modules)
        covered = sum(module.covered_pages for module in modules)
        return AgentModuleCoverageViewOut(
            generated_at=datetime.now(UTC),
            registered_count=len(live),
            enabled_count=sum(spec.name in enabled for spec in live),
            excluded_count=len(excluded),
            personal_count=sum(spec.module is None for spec in live),
            total_pages=total,
            covered_pages=covered,
            enabled_pages=sum(module.enabled_pages for module in modules),
            coverage_percent=round(covered * 100 / total, 1) if total else None,
            modules=modules,
        )
