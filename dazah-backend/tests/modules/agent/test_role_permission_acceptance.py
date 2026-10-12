"""Role grant HTTP -> outbox -> Livzon scope -> execution acceptance."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.modules.agent import api
from app.modules.agent.access_scope import AgentAccessScopeService
from app.modules.agent.automation_service import AgentAutomationService
from app.modules.agent.models import AgentConfirmation
from app.modules.agent.scheduled import AgentAccessScopeSyncGenerator
from app.modules.agent.schemas import AgentAutomationDraftCreate
from app.modules.procurement.models import PurchaseRequest, Supplier
from app.platform.identity import deps, rbac_api
from app.platform.identity.models import (
    DepartmentRoleRule,
    PermissionOutboxEvent,
    Role,
    User,
)
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.rbac import seed_menus

SUPPLIER_PAGE = "purchasing:supplier"
REQUEST_PAGE = "purchasing:request:request-hardware"
QUALITY_PAGE = "quality:deviations:deviation-ledger"


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["web", "feishu"])
async def test_assigned_roles_control_catalog_execution_confirmations_and_automation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # Real endpoints commit savepoints; the outer test transaction owns every row.
    connection = await db_session.connection()
    async with AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        await seed_menus(db)
        tag = uuid4().hex
        admin = User(name="集成授权管理员", role="admin", tenant_key="local")
        user = User(
            name="角色权限验收用户", role="user", tenant_key="local", department=tag
        )
        reader = Role(name="供应商查询角色", code=f"livzon_reader_{tag}")
        writer = Role(name="部门经办角色", code=f"livzon_writer_{tag}")
        db.add_all([admin, user, reader, writer])
        db.add_all(
            [
                Supplier(
                    supplier_name="验收供应商",
                    purchase_category=tag,
                    import_row_number=1,
                ),
                Supplier(
                    supplier_name="已删除验收供应商",
                    purchase_category=tag,
                    import_row_number=2,
                    is_deleted=True,
                ),
            ]
        )
        await db.flush()
        current_actor = [admin]
        app = FastAPI()
        app.include_router(rbac_api.rbac_router, prefix="/api/v1/identity")
        app.include_router(api.router, prefix="/api/v1/agent")
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[deps.get_current_user] = lambda: current_actor[0]
        settings = get_settings().model_copy(
            update={"AGENT_TOOL_TOKEN": "acceptance-token"}
        )
        app.dependency_overrides[get_settings] = lambda: settings
        # Cache notifications are external boundaries; authorization is real DB logic.
        monkeypatch.setattr(rbac_api, "publish_permissions_changed", AsyncMock())
        monkeypatch.setattr(rbac_api, "publish_permissions_changed_all", AsyncMock())
        subject = {"user_id": str(user.id), "tenant_id": "local", "source": source}
        headers = {"Authorization": "Bearer acceptance-token"}
        scope_service = AgentAccessScopeService()
        scanner = AgentAccessScopeSyncGenerator(batch_size=10000)

        async def synchronize_outbox() -> None:
            pending = [
                event
                for event in await scanner.find_due(db)
                if event.user_id == user.id
            ]
            assert pending, "授权接口必须产生可被同步任务消费的页面权限事件"
            assert all(
                event.event_type == "identity.user_page_grants.changed.v1"
                for event in pending
            )
            for event in pending:
                await scanner.execute_one(db, event)
                assert event.status == "processed"
            snapshot = await scope_service.get_snapshot(db, user_id=user.id)
            assert snapshot is not None
            assert snapshot.source_grant_version == user.grant_version
            assert snapshot.sync_status == "synced"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def replace_role(role: Role, grants: list[dict]) -> None:
                response = await client.put(
                    f"/api/v1/identity/admin/roles/{role.id}/page-permissions",
                    json={
                        "expected_grant_version": role.grant_version,
                        "reason": "Livzon 角色联动验收",
                        "grants": grants,
                    },
                )
                assert response.status_code == 200, response.text

            async def assign_roles(role_ids: list[UUID]) -> None:
                response = await client.post(
                    f"/api/v1/identity/admin/users/{user.id}/roles",
                    json={
                        "role_ids": [str(item) for item in role_ids],
                        "mode": "replace",
                        "expected_grant_version": user.grant_version,
                    },
                )
                assert response.status_code == 200, response.text

            async def search() -> set[str]:
                response = await client.post(
                    "/api/v1/agent/tools/search",
                    headers=headers,
                    json={
                        "subject": subject,
                        "query": "",
                        "module": "procurement",
                        "limit": 50,
                    },
                )
                assert response.status_code == 200, response.text
                return {item["operation"] for item in response.json()["data"]}

            async def execute(operation: str, params: dict):
                return await client.post(
                    "/api/v1/agent/tools/execute",
                    headers=headers,
                    json={"subject": subject, "operation": operation, "params": params},
                )

            def grant(page: str, permissions: list[str], scope: str = "all") -> dict:
                return {
                    "page_key": page,
                    "permissions": permissions,
                    "data_scope": {"scope_type": scope},
                }

            await replace_role(
                reader,
                [grant(SUPPLIER_PAGE, ["query"]), grant(REQUEST_PAGE, ["query"])],
            )
            assert "analytics.aggregate" not in await search()
            await assign_roles([reader.id])
            await synchronize_outbox()
            assert user.role == "user", "业务能力来源于分配角色，无需提升账号为管理员"
            names = await search()
            assert "analytics.aggregate" in names
            assert "procurement.create_purchase_request" not in names
            purchase_input = {
                "category": "hardware",
                "request_department": tag,
                "request_date": "2026-10-09",
                "items": [{"product_name": "验收物料", "quantity": 1, "unit_price": 1}],
            }
            assert (
                await execute("procurement.create_purchase_request", purchase_input)
            ).status_code == 403
            stats_input = {
                "dataset": "procurement.suppliers",
                "filters": [{"field": "purchase_category", "op": "eq", "value": tag}],
            }
            result = await execute("analytics.aggregate", stats_input)
            assert result.status_code == 200, result.text
            assert result.json()["data"]["data"]["rows"] == [{"count": 1}]

            # Department-assigned role unions with the manually assigned reader.
            db.add(DepartmentRoleRule(department_name=tag, role_id=writer.id))
            await db.flush()
            await replace_role(
                writer,
                [
                    grant(REQUEST_PAGE, ["operate"]),
                    grant(QUALITY_PAGE, ["query"], "department_tree"),
                ],
            )
            await synchronize_outbox()
            grants = {
                item.page_key: item
                for item in await PagePermissionService().effective_grants(
                    db, user=user
                )
            }
            assert set(grants[REQUEST_PAGE].source_role_names) == {
                reader.name,
                writer.name,
            }
            assert "operate" in grants[REQUEST_PAGE].permissions
            assert "procurement.create_purchase_request" in await search()
            result = await execute(
                "procurement.create_purchase_request", purchase_input
            )
            assert result.status_code == 200, result.text
            assert result.json()["data"]["requires_confirmation"] is True
            confirmation_id = result.json()["data"]["confirmation"]["id"]
            assert (
                await db.scalar(
                    select(func.count(PurchaseRequest.id)).where(
                        PurchaseRequest.request_department == tag
                    )
                )
                == 0
            )

            automation_service = AgentAutomationService()
            draft = await automation_service.create_draft(
                db,
                user=user,
                request=AgentAutomationDraftCreate.model_validate(
                    {
                        "definition": {
                            "name": "角色权限联动",
                            "steps": [
                                {
                                    "key": "read",
                                    "type": "tool",
                                    "operation": "quality.list_deviations",
                                    "input": {},
                                },
                                {"key": "end", "type": "end", "status": "succeeded"},
                            ],
                        }
                    }
                ),
            )
            await automation_service.confirm_automation(
                db, user=user, automation_id=draft.id
            )

            # User-level deny replaces role baseline, then inherit restores it.
            user_url = f"/api/v1/identity/admin/users/{user.id}/page-permissions"
            result = await client.put(
                user_url,
                json={
                    "expected_grant_version": user.grant_version,
                    "reason": "验收显式拒绝",
                    "grants": [grant(SUPPLIER_PAGE, [])],
                },
            )
            assert result.status_code == 200, result.text
            await synchronize_outbox()
            assert "analytics.aggregate" not in await search()
            assert (
                await execute("analytics.aggregate", stats_input)
            ).status_code == 403
            result = await client.put(
                user_url,
                json={
                    "expected_grant_version": user.grant_version,
                    "reason": "验收恢复角色基线",
                    "grants": [{"page_key": SUPPLIER_PAGE, "mode": "inherit"}],
                },
            )
            assert result.status_code == 200, result.text
            await synchronize_outbox()
            assert (
                await execute("analytics.aggregate", stats_input)
            ).status_code == 200

            # Revocation blocks pending confirmation and previously enabled automation.
            await replace_role(writer, [])
            assert (
                await execute("procurement.create_purchase_request", purchase_input)
            ).status_code == 403
            await synchronize_outbox()
            assert "procurement.create_purchase_request" not in await search()
            current_actor[0] = user
            if source == "feishu":
                result = await client.post(
                    f"/api/v1/agent/confirmations/{confirmation_id}/resolve",
                    headers=headers,
                    json={"subject": subject, "choice": "allow"},
                )
            else:
                result = await client.post(
                    f"/api/v1/agent/confirmations/{confirmation_id}/execute"
                )
            assert result.status_code == 403, result.text
            confirmation = await db.get(AgentConfirmation, UUID(confirmation_id))
            assert confirmation.status == "cancelled"
            assert (
                await db.scalar(
                    select(func.count(PurchaseRequest.id)).where(
                        PurchaseRequest.request_department == tag
                    )
                )
                == 0
            )
            with pytest.raises(HTTPException) as error:
                await automation_service.set_enabled(
                    db, user=user, automation_id=draft.id, enabled=True
                )
            assert error.value.status_code == 403
            automation = await automation_service.repo.get_automation(db, draft.id)
            assert automation.status == "suspended_policy"

            current_actor[0] = admin
            await assign_roles([])
            # Direct execute fails closed before async sync catches up.
            assert (
                await execute("analytics.aggregate", stats_input)
            ).status_code == 403
            await synchronize_outbox()
            assert "analytics.aggregate" not in await search()
            assert (
                await execute("analytics.aggregate", stats_input)
            ).status_code == 403
            events = (
                await db.scalars(
                    select(PermissionOutboxEvent).where(
                        PermissionOutboxEvent.user_id == user.id
                    )
                )
            ).all()
            assert events and all(event.status == "processed" for event in events)
