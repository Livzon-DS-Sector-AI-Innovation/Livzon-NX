import uuid
from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.catalog import ToolCatalogService
from app.modules.agent.schemas import (
    AgentSkillResolveRequest,
    AgentToolExecuteRequest,
    AgentTrustedSubject,
    AgentWorkflowCreate,
    AgentWorkflowUpdate,
)
from app.modules.agent.service import (
    BUILTIN_WORKFLOW_SKILL_CONTENT,
    BUILTIN_WORKFLOW_SKILL_DESCRIPTION,
    BUILTIN_WORKFLOW_SKILL_KEYWORDS,
    BUILTIN_WORKFLOW_SKILL_NAME,
    BUILTIN_WORKFLOW_SKILL_TITLE,
    AgentService,
)
from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry
from app.platform.identity.models import User

SimpleNamespace: Any = _SimpleNamespace


class AllowAllAccessScopeService:
    async def require_tool_access(self: Any, *args: Any, **kwargs: Any) -> Any:
        return None


class FakeDb:
    async def flush(self: Any) -> None:
        return None

    async def commit(self: Any) -> None:
        return None


def test_legacy_update_workflow_tool_is_not_exposed() -> None:
    ensure_agent_tools_registered()

    assert tool_registry.get("agent.update_workflow") is None
    assert tool_registry.get("agent.update_automation") is not None


@pytest.mark.anyio
async def test_update_workflow_changes_editable_fields(monkeypatch: Any) -> None:
    user_id = uuid.uuid4()
    workflow: Any = SimpleNamespace(
        id=uuid.uuid4(),
        name="原工作流",
        description="原说明",
        trigger_phrases=["原触发词"],
        updated_by=None,
    )
    service = AgentService(settings=SimpleNamespace())

    async def fake_get(*args: Any, **kwargs: Any) -> Any:
        return workflow

    async def fake_refetch(*args: Any, **kwargs: Any) -> Any:
        return workflow

    monkeypatch.setattr(service, "_get_user_workflow", fake_get)
    monkeypatch.setattr(service, "_refetch_workflow", fake_refetch)

    result = await service._update_workflow_from_request(
        cast(Any, FakeDb)(),
        workflow_id=workflow.id,
        request=AgentWorkflowUpdate(
            name="新工作流",
            description=None,
            trigger_phrases=["每日查询", "异常提醒"],
        ),
        user_id=user_id,
    )

    assert result.name == "新工作流"
    assert result.description is None
    assert result.trigger_phrases == ["每日查询", "异常提醒"]
    assert result.updated_by == user_id


class FakeSkillWorkflowRepository:
    def __init__(self: Any) -> None:
        now = datetime.now(UTC)
        self.skill = SimpleNamespace(
            id=uuid.uuid4(),
            name=BUILTIN_WORKFLOW_SKILL_NAME,
            title=BUILTIN_WORKFLOW_SKILL_TITLE,
            description=BUILTIN_WORKFLOW_SKILL_DESCRIPTION,
            trigger_keywords=BUILTIN_WORKFLOW_SKILL_KEYWORDS,
            content=BUILTIN_WORKFLOW_SKILL_CONTENT,
            status="active",
            is_builtin=True,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.workflows = []  # type: ignore[var-annotated]

    async def list_active_skills(self: Any, db: Any) -> Any:
        return [self.skill]

    async def create_workflow(
        self: Any,
        db: Any,
        *,
        user_id: Any,
        session_id: Any,
        name: Any,
        description: Any,
        trigger_phrases: Any,
        steps: Any,
        source_skill: Any,
        source_request: Any,
    ) -> Any:
        now = datetime.now(UTC)
        workflow: Any = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            name=name,
            description=description,
            status="enabled",
            trigger_phrases=trigger_phrases,
            steps=steps,
            source_skill=source_skill,
            source_request=source_request,
            last_run_id=None,
            last_run_status=None,
            last_run_at=None,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            updated_by=user_id,
        )
        self.workflows.append(workflow)
        return workflow

    async def list_workflows(self: Any, db: Any, *, user_id: Any) -> Any:
        return [workflow for workflow in self.workflows if workflow.user_id == user_id]


@pytest.mark.anyio
async def test_skill_resolver_matches_workflow_keyword() -> None:
    service = AgentService(
        settings=SimpleNamespace(),
        repo=FakeSkillWorkflowRepository(),  # type: ignore[arg-type]
    )

    response = await service.resolve_skills(
        cast(Any, FakeDb)(),
        request=AgentSkillResolveRequest(message="帮我创建一个采购合同生成工作流"),
    )

    assert len(response.skills) == 1
    assert response.skills[0].name == BUILTIN_WORKFLOW_SKILL_NAME
    assert "agent.list_workflow_capabilities" in response.skills[0].content


@pytest.mark.anyio
async def test_skill_resolver_ignores_unrelated_message() -> None:
    service = AgentService(
        settings=SimpleNamespace(),
        repo=FakeSkillWorkflowRepository(),  # type: ignore[arg-type]
    )

    response = await service.resolve_skills(
        cast(Any, FakeDb)(),
        request=AgentSkillResolveRequest(message="查询原辅料库存"),
    )

    assert response.skills == []


def test_workflow_capabilities_mark_high_risk_as_not_allowed() -> None:
    service = AgentService(settings=SimpleNamespace())

    capabilities = service._workflow_capabilities()["capabilities"]
    by_operation = {item["operation"]: item for item in capabilities}

    assert (
        by_operation["procurement.list_purchase_requests"]["workflow_allowed"] is True
    )
    approve_capability = by_operation["procurement.approve_purchase_request"]
    assert approve_capability["workflow_allowed"] is False
    assert by_operation["warehouse.restart_feishu_ws"]["workflow_allowed"] is False


def test_procurement_supplier_query_is_exposed_as_workflow_capability() -> None:
    service = AgentService(settings=SimpleNamespace())

    capabilities = service._workflow_capabilities()["capabilities"]
    supplier_capability = {item["operation"]: item for item in capabilities}[
        "procurement.list_suppliers"
    ]

    assert supplier_capability["method"] == "GET"
    assert supplier_capability["path"] == "/procurement/suppliers"
    assert supplier_capability["write"] is False
    assert supplier_capability["workflow_allowed"] is True
    assert "supplier_name" in supplier_capability["input_schema"]["params"]
    assert "物料" in supplier_capability["output_hint"]


def test_workflow_create_normalizes_title_and_rejects_missing_path_params() -> None:
    service = AgentService(settings=SimpleNamespace())

    request = service._normalize_tool_request(
        AgentToolExecuteRequest(
            operation="agent.create_workflow",
            subject=AgentTrustedSubject(
                tenant_id="test",
                user_id=uuid.uuid4(),
                source="internal",
            ),
            body={
                "title": "采购申请批量提交",
                "description": "查询草稿申请并提交",
                "steps": [
                    {
                        "order": 1,
                        "title": "查询采购申请",
                        "operation": "procurement.list_purchase_requests",
                    },
                    {
                        "order": 2,
                        "title": "提交采购申请",
                        "operation": "procurement.submit_purchase_request",
                    },
                ],
            },
            reason="创建采购申请批量提交工作流",
        )
    )

    error = service._tool_request_validation_error(request)

    assert request.body["name"] == "采购申请批量提交"  # type: ignore[index]
    assert request.body["source_request"] == "创建采购申请批量提交工作流"  # type: ignore[index]
    assert error is not None
    assert "request_id" in error
    assert "不支持把上一步查询结果自动批量映射到写操作" in error


@pytest.mark.anyio
async def test_workflow_creation_rejects_high_risk_step() -> None:
    service = AgentService(
        settings=SimpleNamespace(),
        repo=FakeSkillWorkflowRepository(),  # type: ignore[arg-type]
    )

    with pytest.raises(Exception) as exc_info:
        await service._create_workflow_from_request(
            cast(Any, FakeDb)(),
            request=AgentWorkflowCreate(
                name="审批工作流",
                steps=[
                    {
                        "order": 1,
                        "title": "审批采购申请",
                        "operation": "procurement.approve_purchase_request",
                        "params": {"request_id": str(uuid.uuid4())},
                    }
                ],
            ),
            user_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
        )

    assert "human-decision" in str(exc_info.value)


@pytest.mark.anyio
async def test_workflow_creation_stores_user_scoped_workflow() -> None:
    repo: Any = FakeSkillWorkflowRepository()
    service = AgentService(
        settings=SimpleNamespace(),
        repo=repo,
        access_scope_service=AllowAllAccessScopeService(),
    )
    user_id = uuid.uuid4()

    workflow = await service._create_workflow_from_request(
        cast(Any, FakeDb)(),
        request=AgentWorkflowCreate(
            name="采购合同模板查询工作流",
            trigger_phrases=["合同模板"],
            steps=[
                {
                    "order": 1,
                    "title": "查询合同模板",
                    "operation": "procurement.list_contract_templates",
                }
            ],
            source_request="帮我创建合同模板查询工作流",
        ),
        user_id=user_id,
        session_id=uuid.uuid4(),
    )

    workflows = await repo.list_workflows(cast(Any, FakeDb)(), user_id=user_id)
    other_user_workflows = await repo.list_workflows(
        cast(Any, FakeDb)(), user_id=uuid.uuid4()
    )

    assert workflow.user_id == user_id
    assert workflows == [workflow]
    assert other_user_workflows == []
    assert workflow.source_skill == BUILTIN_WORKFLOW_SKILL_NAME


@pytest.mark.anyio
async def test_workflow_run_refetches_updated_state_before_response(
    db_session: AsyncSession,
) -> None:
    user = User(
        name="工作流测试用户",
        username=f"workflow-{uuid.uuid4().hex[:12]}",
        # Workflow execution is not the subject of this regression test; use
        # the administrator path so the page-publication gate is covered by
        # its dedicated authorization tests instead.
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()
    service = AgentService(
        settings=SimpleNamespace(),
        access_scope_service=AllowAllAccessScopeService(),
    )
    await ToolCatalogService().set_enabled(
        db_session,
        operation="procurement.list_contract_templates",
        enabled=True,
    )
    workflow = await service._create_workflow_from_request(
        db_session,
        request=AgentWorkflowCreate(
            name="合同模板查询工作流",
            steps=[
                {
                    "order": 1,
                    "title": "查询合同模板",
                    "operation": "procurement.list_contract_templates",
                }
            ],
        ),
        user_id=user.id,
        session_id=None,
    )

    result = await service._start_workflow_run(
        db_session,
        workflow=workflow,
        user_id=user.id,
        session_id=None,
    )

    run = result["run"]
    assert run["status"] == "succeeded", run["error_message"]
    assert run["current_step"] == 1
    assert run["updated_at"] is not None
    assert run["step_results"][0]["operation"] == "procurement.list_contract_templates"
