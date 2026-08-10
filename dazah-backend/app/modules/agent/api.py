import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.response import error_response, success_response
from app.platform.audit.models import AuditLog
from app.platform.identity.deps import AdminUser, RequiredUser
from app.platform.identity.models import User

from .access_scope import AgentAccessScopeService
from .audit_service import AgentAuditService
from .automation_service import AgentAutomationService
from .catalog import ToolCatalogService
from .event_service import AgentDomainEventService
from .llm_proxy import forward_chat_completion, list_active_text_models
from .memory_policy import AgentMemoryPolicyService
from .models import (
    AgentConfirmation,
    AgentDomainEvent,
    AgentMessage,
    AgentPushDelivery,
    AgentToolCall,
)
from .operations_service import AgentOperationsService
from .push_delivery_service import PushDeliveryService
from .repository import AgentRepository
from .schemas import (
    AgentAccessScopeOut,
    AgentAuditSessionDetail,
    AgentAuditSessionPage,
    AgentAutomationAuditItem,
    AgentChatRequest,
    AgentConfirmationExecuteResponse,
    AgentConfirmationResolveRequest,
    AgentMemoryTenantPolicyOut,
    AgentMemoryTenantPolicyUpdate,
    AgentSessionDetail,
    AgentSessionItem,
    AgentSessionPage,
    AgentSkillCreate,
    AgentSkillResolveRequest,
    AgentSkillUpdate,
    AgentToolCatalogPage,
    AgentToolControlRequest,
    AgentToolEnabledUpdate,
    AgentToolExecuteRequest,
    AgentToolSearchRequest,
    AgentTrustedSubject,
    FeishuConversationCompleteRequest,
    FeishuConversationCompleteResponse,
    FeishuConversationPrepareRequest,
    FeishuConversationPrepareResponse,
)
from .service import AgentService

router = APIRouter()


@router.get(
    "/memory/tenant-policy",
    summary="获取租户 Agent 记忆治理策略",
    response_model=AgentMemoryTenantPolicyOut,
)
async def get_agent_memory_tenant_policy(
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
    settings: Settings = Depends(get_settings),
):
    return await AgentMemoryPolicyService(settings).tenant_policy(
        db, tenant_id=current_user.tenant_key or "default"
    )


@router.put(
    "/memory/tenant-policy",
    summary="更新租户 Agent 记忆治理策略",
    response_model=AgentMemoryTenantPolicyOut,
)
async def update_agent_memory_tenant_policy(
    payload: AgentMemoryTenantPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: AdminUser = None,
    settings: Settings = Depends(get_settings),
):
    result = await AgentMemoryPolicyService(settings).update_tenant_policy(
        db, user=current_user, mode=payload.mode
    )
    await db.commit()
    return result


def _changed_definition_fields(
    current: dict[str, Any], previous: dict[str, Any]
) -> list[str]:
    return sorted(
        key
        for key in set(current) | set(previous)
        if current.get(key) != previous.get(key)
    )


@router.get(
    "/audit/sessions",
    summary="管理员查询 Livzon 对话审计",
    response_model=AgentAuditSessionPage,
)
async def list_agent_audit_sessions(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    user_id: uuid.UUID | None = None,
    channel: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentAuditService().list_sessions(
        db,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
        keyword=keyword,
        user_id=user_id,
        channel=channel,
        started_at=started_at,
        ended_at=ended_at,
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="GET",
            path="/api/v1/agent/audit/sessions",
            status_code=200,
            resource_type="agent_audit",
            action="list_agent_conversation_audit",
            extra={"user_id": str(user_id) if user_id else None, "channel": channel},
        )
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get(
    "/audit/sessions/{session_id}",
    summary="管理员查看 Livzon 对话审计详情",
    response_model=AgentAuditSessionDetail,
)
async def get_agent_audit_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentAuditService().get_session_detail(db, session_id=session_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Livzon session not found")
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="GET",
            path=f"/api/v1/agent/audit/sessions/{session_id}",
            status_code=200,
            resource_type="agent_session",
            resource_id=session_id,
            action="view_agent_conversation_audit",
        )
    )
    return success_response(data=result.model_dump(mode="json"))


def _audit_automation_query(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    action: str,
    resource_id: uuid.UUID | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            method="GET",
            path="/api/v1/agent/automations",
            status_code=200,
            resource_type="agent_automation",
            resource_id=resource_id,
            action=action,
            extra=extra or {},
        )
    )


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return None


@router.get("/push-deliveries")
async def list_push_deliveries(
    status_value: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await PushDeliveryService().list_for_user(
        db,
        user=current_user,
        status_value=status_value,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_push_deliveries",
        extra={"status": status_value},
    )
    return success_response(data=result)


@router.get("/push-deliveries/{delivery_id}")
async def get_push_delivery(
    delivery_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    try:
        result = await PushDeliveryService().get_for_user(
            db, user=current_user, delivery_id=delivery_id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="view_agent_push_delivery",
        resource_id=delivery_id,
    )
    return success_response(data=result)


def require_service_token(expected: str, authorization: str | None) -> None:
    token = _bearer_token(authorization)
    if not expected or token != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Agent service token")


async def _require_feishu_subject_user(
    db: AsyncSession,
    *,
    subject: AgentTrustedSubject,
) -> User:
    if subject.source != "feishu":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Feishu subject required")
    user = await db.get(User, subject.user_id)
    if user is None or user.is_deleted or user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Feishu user is not active")
    if (user.tenant_key or "default") != subject.tenant_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Feishu tenant mismatch")
    return user


@router.get("/domain-events/{correlation_id}")
async def list_domain_events(
    correlation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentDomainEventService().list_for_user(
        db, user=current_user, correlation_id=correlation_id
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_domain_events",
        extra={"correlation_id": str(correlation_id)},
    )
    return success_response(data=result)


@router.get("/automation-capability-impacts")
async def list_automation_capability_impacts(
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().list_capability_impacts(
        db, user=current_user
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_automation_capability_impacts",
    )
    return success_response(data=result)


@router.get("/operations/health")
async def get_automation_health(
    db: AsyncSession = Depends(get_db), current_user: RequiredUser = None
):
    result = await AgentOperationsService().health(db, user=current_user)
    _audit_automation_query(
        db, user_id=current_user.id, action="view_automation_health"
    )
    return success_response(data=result)


@router.get("/operations/trends")
async def get_automation_trends(
    db: AsyncSession = Depends(get_db), current_user: RequiredUser = None
):
    result = await AgentOperationsService().trends(db, user=current_user)
    _audit_automation_query(
        db, user_id=current_user.id, action="view_automation_trends"
    )
    return success_response(data=result)


@router.get("/operations/templates")
async def list_automation_templates(
    db: AsyncSession = Depends(get_db), current_user: RequiredUser = None
):
    _audit_automation_query(
        db, user_id=current_user.id, action="list_automation_templates"
    )
    return success_response(data=AgentOperationsService.templates())


@router.get("/operations/suggestions")
async def list_automation_suggestions(
    db: AsyncSession = Depends(get_db), current_user: RequiredUser = None
):
    result = await AgentOperationsService().suggestions(db, user=current_user)
    _audit_automation_query(
        db, user_id=current_user.id, action="view_automation_suggestions"
    )
    return success_response(data=result)


@router.get("/operations/report")
async def get_operations_report(
    db: AsyncSession = Depends(get_db), current_user: RequiredUser = None
):
    result = await AgentOperationsService().admin_report(db, user=current_user)
    _audit_automation_query(
        db, user_id=current_user.id, action="view_operations_report"
    )
    return success_response(data=result)


@router.get("/automations")
async def list_automations(
    scope: str = "mine",
    status_value: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().list_automations(
        db,
        user=current_user,
        scope=scope,
        status_value=status_value,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_automations",
        extra={"scope": scope, "status": status_value},
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/automations/{automation_id}")
async def get_automation(
    automation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().get_automation_out(
        db, user=current_user, automation_id=automation_id
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="view_agent_automation",
        resource_id=automation_id,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/automations/{automation_id}/versions")
async def list_automation_versions(
    automation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().list_versions(
        db, user=current_user, automation_id=automation_id
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_automation_versions",
        resource_id=automation_id,
    )
    return success_response(data=[item.model_dump(mode="json") for item in result])


@router.get("/automation-audit", response_model=list[AgentAutomationAuditItem])
async def list_automation_audit(
    automation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    versions = await AgentAutomationService().list_versions(
        db, user=current_user, automation_id=automation_id
    )
    previous: dict[str, Any] = {}
    result: list[AgentAutomationAuditItem] = []
    for version in sorted(versions, key=lambda item: item.version):
        result.append(
            AgentAutomationAuditItem(
                id=version.id,
                automation_id=version.automation_id,
                version=version.version,
                actor_id=version.created_by,
                change_summary=version.change_summary,
                changed_fields=_changed_definition_fields(version.definition, previous),
                created_at=version.created_at,
            )
        )
        previous = version.definition
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_automation_audit",
        resource_id=automation_id,
    )
    return success_response(
        data=[item.model_dump(mode="json") for item in reversed(result)]
    )


@router.get("/automations/{automation_id}/schedule-preview")
async def preview_automation_schedule(
    automation_id: uuid.UUID,
    count: int = 5,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().simulate_schedule(
        db,
        user=current_user,
        automation_id=automation_id,
        count=min(max(1, count), 20),
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="simulate_agent_automation_schedule",
        resource_id=automation_id,
    )
    return success_response(data=result)


@router.get("/scheduled-triggers")
async def list_scheduled_triggers(
    scope: str = "mine",
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().list_scheduled_triggers(
        db,
        user=current_user,
        scope=scope,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_scheduled_triggers",
        extra={"scope": scope},
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/automation-runs")
async def list_automation_runs(
    scope: str = "mine",
    status_value: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().list_runs(
        db,
        user=current_user,
        scope=scope,
        status_value=status_value,
        page=max(1, page),
        page_size=min(max(1, page_size), 100),
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_automation_runs",
        extra={"scope": scope, "status": status_value},
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/automation-runs/{run_id}")
async def get_automation_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().get_run(
        db, user=current_user, run_id=run_id
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="view_agent_automation_run",
        resource_id=run_id,
    )
    return success_response(data=result)


@router.get("/automation-runs/{run_id}/events")
async def list_automation_run_events(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAutomationService().list_run_events(
        db, user=current_user, run_id=run_id
    )
    _audit_automation_query(
        db,
        user_id=current_user.id,
        action="list_agent_automation_run_events",
        resource_id=run_id,
    )
    return success_response(data=[item.model_dump(mode="json") for item in result])


@router.post(
    "/internal/feishu/conversations/prepare",
    response_model=FeishuConversationPrepareResponse,
)
async def prepare_internal_feishu_conversation(
    payload: FeishuConversationPrepareRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.HERMES_INTERNAL_TOKEN, authorization)
    user = await _require_feishu_subject_user(db, subject=payload.subject)
    await AgentAccessScopeService().get_current_scope(db, user=user)
    return await AgentService(settings).prepare_feishu_conversation(
        db,
        request=payload,
        current_user=user,
    )


@router.post(
    "/internal/feishu/conversations/{session_id}/complete",
    response_model=FeishuConversationCompleteResponse,
)
async def complete_internal_feishu_conversation(
    session_id: uuid.UUID,
    payload: FeishuConversationCompleteRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.HERMES_INTERNAL_TOKEN, authorization)
    user = await _require_feishu_subject_user(db, subject=payload.subject)
    return await AgentService(settings).complete_feishu_conversation(
        db,
        session_id=session_id,
        request=payload,
        current_user=user,
    )


@router.post("/chat")
async def chat(
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    await AgentAccessScopeService().get_current_scope(db, user=current_user)
    result = await AgentService(settings).chat(
        db, request=payload, current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/sessions", response_model=AgentSessionPage)
async def list_my_agent_sessions(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    result = await AgentService(settings).list_sessions(
        db,
        current_user=current_user,
        page=max(1, page),
        page_size=min(max(1, page_size), 50),
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/sessions/{session_id}", response_model=AgentSessionDetail)
async def get_my_agent_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    result = await AgentService(settings).get_session_detail(
        db, session_id=session_id, current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/sessions/{session_id}/archive", response_model=AgentSessionItem)
async def archive_my_agent_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    result = await AgentService(settings).archive_session(
        db, session_id=session_id, current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/chat/stream")
async def chat_stream(
    payload: AgentChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    await AgentAccessScopeService().get_current_scope(db, user=current_user)
    return StreamingResponse(
        AgentService(settings).stream_chat(
            db,
            request=payload,
            current_user=current_user,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/access-scope", response_model=AgentAccessScopeOut)
async def get_my_access_scope(
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    result = await AgentAccessScopeService().scope_out(db, user=current_user)
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="GET",
            path="/api/v1/agent/access-scope",
            status_code=200,
            resource_type="agent_access_scope",
            resource_id=current_user.id,
            action="view_own_agent_access_scope",
            extra={
                "source_grant_version": result.source_grant_version,
                "agent_scope_version": result.agent_scope_version,
            },
        )
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/tools/execute")
async def execute_tool(
    payload: AgentToolExecuteRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_TOOL_TOKEN, authorization)
    result = await AgentService(settings).execute_tool(db, request=payload)
    return success_response(data=result.model_dump(mode="json"))


@router.post("/control/tools/execute")
async def execute_control_plane_tool(
    payload: AgentToolControlRequest,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    request = AgentToolExecuteRequest(
        operation=payload.operation,
        params=payload.params,
        body=payload.body,
        reason=payload.reason,
        session_id=payload.session_id,
        trace_id=payload.trace_id,
        subject=AgentTrustedSubject(
            tenant_id=current_user.tenant_key or "default",
            user_id=current_user.id,
            source="web",
        ),
        execution_context={"source": "admin_control_plane"},
    )
    result = await AgentService(settings).execute_tool(db, request=request)
    return success_response(data=result.model_dump(mode="json"))


@router.get("/control/tools")
async def list_control_plane_tools(
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await ToolCatalogService().list_all(db)
    return success_response(data=[item.model_dump(mode="json") for item in result])


@router.get("/control/tools/page", response_model=None)
async def list_control_plane_tools_page(
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
    module: str | None = None,
    status_value: str | None = None,
    risk_level: str | None = None,
    write: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    normalized_page = max(1, page)
    normalized_size = min(max(1, page_size), 100)
    items, total = await ToolCatalogService().list_page(
        db,
        page=normalized_page,
        page_size=normalized_size,
        keyword=keyword,
        module=module,
        status_value=status_value,
        risk_level=risk_level,
        write=write,
    )
    result = AgentToolCatalogPage(
        items=items,
        page=normalized_page,
        page_size=normalized_size,
        total=total,
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/control/confirmations")
async def list_control_plane_confirmations(
    page: int = 1,
    page_size: int = 20,
    status_value: str | None = None,
    user_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    await AgentRepository().expire_due_confirmations(db)
    conditions: list[Any] = [AgentConfirmation.is_deleted.is_(False)]
    if status_value:
        conditions.append(AgentConfirmation.status == status_value)
    if user_id:
        conditions.append(AgentConfirmation.user_id == user_id)
    normalized_page = max(1, page)
    normalized_size = min(max(1, page_size), 100)
    total = int(
        await db.scalar(
            select(func.count()).select_from(AgentConfirmation).where(*conditions)
        )
        or 0
    )
    rows = list(
        (
            await db.execute(
                select(AgentConfirmation)
                .where(*conditions)
                .order_by(AgentConfirmation.created_at.desc())
                .offset((normalized_page - 1) * normalized_size)
                .limit(normalized_size)
            )
        )
        .scalars()
        .all()
    )
    return success_response(
        data={
            "items": [
                {
                    "id": str(item.id),
                    "session_id": str(item.session_id) if item.session_id else None,
                    "user_id": str(item.user_id) if item.user_id else None,
                    "operation": item.operation,
                    "summary": item.summary,
                    "risk_level": item.risk_level,
                    "status": item.status,
                    "expires_at": item.expires_at.isoformat(),
                    "executed_at": item.executed_at.isoformat()
                    if item.executed_at
                    else None,
                    "created_at": item.created_at.isoformat(),
                }
                for item in rows
            ],
            "page": normalized_page,
            "page_size": normalized_size,
            "total": total,
        }
    )


@router.get("/control/traces/{trace_id}")
async def get_control_plane_trace(
    trace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    tool_calls = list(
        (
            await db.execute(
                select(AgentToolCall)
                .where(
                    AgentToolCall.correlation_id == trace_id,
                    AgentToolCall.is_deleted.is_(False),
                )
                .order_by(AgentToolCall.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    messages = list(
        (
            await db.execute(
                select(AgentMessage)
                .where(
                    AgentMessage.message_metadata["trace_id"].astext == str(trace_id),
                    AgentMessage.is_deleted.is_(False),
                )
                .order_by(AgentMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    confirmations = list(
        (
            await db.execute(
                select(AgentConfirmation)
                .where(
                    AgentConfirmation.request_payload["trace_id"].astext
                    == str(trace_id),
                    AgentConfirmation.is_deleted.is_(False),
                )
                .order_by(AgentConfirmation.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    domain_events = list(
        (
            await db.execute(
                select(AgentDomainEvent)
                .where(
                    AgentDomainEvent.correlation_id == trace_id,
                    AgentDomainEvent.is_deleted.is_(False),
                )
                .order_by(AgentDomainEvent.occurred_at.asc())
            )
        )
        .scalars()
        .all()
    )
    deliveries = list(
        (
            await db.execute(
                select(AgentPushDelivery)
                .where(
                    AgentPushDelivery.run_id == trace_id,
                    AgentPushDelivery.is_deleted.is_(False),
                )
                .order_by(AgentPushDelivery.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    audit_receipts = list(
        (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.resource_type.in_(
                        (
                            "agent_capability_search",
                            "agent_capability_description",
                            "feishu_resource",
                            "feishu_resource_change",
                        )
                    ),
                    or_(
                        AuditLog.request_id == str(trace_id),
                        AuditLog.extra["trace_id"].as_string() == str(trace_id),
                    ),
                )
                .order_by(AuditLog.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    timeline: list[dict[str, Any]] = [
        {
            "type": "tool_call",
            "id": str(item.id),
            "occurred_at": item.created_at.isoformat(),
            "status": item.status,
            "summary": item.operation,
            "operation": item.operation,
            "error_code": "agent.tool_failed" if item.error_message else None,
        }
        for item in tool_calls
    ]
    timeline.extend(
        {
            "type": "inbound_message" if item.role == "user" else "assistant_response",
            "id": str(item.id),
            "occurred_at": item.created_at.isoformat(),
            "status": "recorded",
            "summary": (
                "飞书入站消息（正文已隐藏）"
                if item.role == "user"
                else "Livzon Agent 回复（正文已隐藏）"
            ),
            "operation": None,
            "error_code": None,
            "session_id": str(item.session_id),
            "channel": item.message_metadata.get("channel") or "web",
        }
        for item in messages
        if item.role in {"user", "assistant"}
    )
    timeline.extend(
        {
            "type": "confirmation",
            "id": str(item.id),
            "occurred_at": item.created_at.isoformat(),
            "status": item.status,
            "summary": item.operation,
            "operation": item.operation,
            "error_code": None,
            "session_id": str(item.session_id) if item.session_id else None,
            "risk_level": item.risk_level,
        }
        for item in confirmations
    )
    timeline.extend(
        {
            "type": "domain_event",
            "id": str(item.id),
            "occurred_at": item.occurred_at.isoformat(),
            "status": "recorded",
            "summary": item.event_type,
            "operation": None,
            "error_code": None,
        }
        for item in domain_events
    )
    timeline.extend(
        {
            "type": "delivery",
            "id": str(item.id),
            "occurred_at": item.created_at.isoformat(),
            "status": item.status,
            "summary": item.template_key,
            "operation": None,
            "error_code": item.last_error_code,
            "external_message_id": item.external_message_id,
            "attempt_count": item.attempt_count,
        }
        for item in deliveries
    )
    timeline.extend(
        {
            "type": (
                "capability_search"
                if item.resource_type
                in {"agent_capability_search", "agent_capability_description"}
                else "audit_receipt"
            ),
            "id": str(item.id),
            "occurred_at": item.created_at.isoformat(),
            "status": (
                "recorded" if item.status_code and item.status_code < 400 else "failed"
            ),
            "summary": item.action,
            "operation": (item.extra or {}).get("operation"),
            "error_code": None,
            "receipt_id": item.request_id,
        }
        for item in audit_receipts
    )
    timeline.sort(key=lambda item: item["occurred_at"])
    return success_response(
        data={
            "trace_id": str(trace_id),
            "timeline": timeline,
            "counts": {
                "tool_calls": len(tool_calls),
                "messages": len(messages),
                "confirmations": len(confirmations),
                "domain_events": len(domain_events),
                "deliveries": len(deliveries),
                "capability_searches": sum(
                    item.resource_type
                    in {"agent_capability_search", "agent_capability_description"}
                    for item in audit_receipts
                ),
                "audit_receipts": sum(
                    item.resource_type in {"feishu_resource", "feishu_resource_change"}
                    for item in audit_receipts
                ),
            },
        }
    )


@router.get("/control/traces/{trace_id}/export")
async def export_control_plane_trace(
    trace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    response = await get_control_plane_trace(
        trace_id=trace_id,
        db=db,
        current_user=current_user,
    )
    envelope = json.loads(response.body)
    trace = envelope["data"]
    canonical = json.dumps(
        trace,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    export = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "filters": {"trace_id": str(trace_id)},
        "content_policy": "metadata_only_no_business_body_or_credentials",
        "trace": trace,
        "verification": {"sha256": hashlib.sha256(canonical).hexdigest()},
    }
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="GET",
            path=f"/api/v1/agent/control/traces/{trace_id}/export",
            status_code=200,
            resource_type="agent_trace",
            action="export_agent_trace_diagnostic",
            extra={"trace_id": str(trace_id)},
        )
    )
    return JSONResponse(
        content=export,
        headers={
            "Content-Disposition": (
                f'attachment; filename="livzon-trace-{trace_id}.json"'
            )
        },
    )


@router.get("/control/runtime-overview")
async def get_control_plane_runtime_overview(
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    pending_confirmations = int(
        await db.scalar(
            select(func.count(AgentConfirmation.id)).where(
                AgentConfirmation.status == "pending",
                AgentConfirmation.expires_at > datetime.now(UTC),
                AgentConfirmation.is_deleted.is_(False),
            )
        )
        or 0
    )
    failed_deliveries = int(
        await db.scalar(
            select(func.count(AgentPushDelivery.id)).where(
                AgentPushDelivery.status == "failed",
                AgentPushDelivery.is_deleted.is_(False),
            )
        )
        or 0
    )
    recovered_call = aliased(AgentToolCall)
    has_later_success = (
        select(recovered_call.id)
        .where(
            recovered_call.operation == AgentToolCall.operation,
            recovered_call.status == "succeeded",
            recovered_call.created_at > AgentToolCall.created_at,
            recovered_call.is_deleted.is_(False),
        )
        .exists()
    )
    latest_failed_call = await db.scalar(
        select(AgentToolCall)
        .where(
            AgentToolCall.status == "failed",
            AgentToolCall.is_deleted.is_(False),
            ~has_later_success,
        )
        .order_by(AgentToolCall.created_at.desc())
        .limit(1)
    )
    return success_response(
        data={
            "pending_confirmations": pending_confirmations,
            "failed_deliveries": failed_deliveries,
            "latest_error_trace_id": str(latest_failed_call.correlation_id)
            if latest_failed_call
            else None,
            "latest_error_at": latest_failed_call.created_at.isoformat()
            if latest_failed_call
            else None,
        }
    )


@router.post("/tools/search")
async def search_tools(
    payload: AgentToolSearchRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_TOOL_TOKEN, authorization)
    result = await ToolCatalogService().search(db, payload)
    db.add(
        AuditLog(
            request_id=str(payload.trace_id),
            user_id=payload.subject.user_id,
            method="POST",
            path="/api/v1/agent/tools/search",
            status_code=200,
            resource_type="agent_capability_search",
            action="search_agent_tools",
            extra={
                "trace_id": str(payload.trace_id),
                "module": payload.module,
                "result_count": len(result),
            },
        )
    )
    return success_response(data=[item.model_dump(mode="json") for item in result])


@router.get("/tools/{operation}")
async def describe_tool(
    operation: str,
    subject_user_id: uuid.UUID,
    subject_tenant_id: str,
    trace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_TOOL_TOKEN, authorization)
    result = await ToolCatalogService().describe(
        db,
        operation=operation,
        user_id=subject_user_id,
        tenant_id=subject_tenant_id,
    )
    db.add(
        AuditLog(
            request_id=str(trace_id),
            user_id=subject_user_id,
            method="GET",
            path=f"/api/v1/agent/tools/{operation}",
            status_code=200,
            resource_type="agent_capability_description",
            action="describe_agent_tool",
            extra={"trace_id": str(trace_id), "operation": operation},
        )
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/tools/{operation}/enabled")
async def set_tool_enabled(
    operation: str,
    payload: AgentToolEnabledUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await ToolCatalogService().set_enabled(
        db,
        operation=operation,
        enabled=payload.enabled,
    )
    db.add(
        AuditLog(
            user_id=current_user.id,
            method="POST",
            path=f"/api/v1/agent/tools/{operation}/enabled",
            status_code=200,
            resource_type="agent_tool_catalog",
            action="set_agent_tool_enabled",
            extra={"operation": operation, "enabled": payload.enabled},
        )
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/skills/resolve")
async def resolve_skills(
    payload: AgentSkillResolveRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_TOOL_TOKEN, authorization)
    result = await AgentService(settings).resolve_skills(db, request=payload)
    return success_response(data=result.model_dump(mode="json"))


@router.get("/skills")
async def list_skills(
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentService(settings).list_skills(db)
    return success_response(data=[item.model_dump(mode="json") for item in result])


@router.post("/skills")
async def create_skill(
    payload: AgentSkillCreate,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentService(settings).create_skill(
        db, request=payload, current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.get("/skills/{skill_id}")
async def get_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentService(settings).get_skill(db, skill_id=skill_id)
    return success_response(data=result.model_dump(mode="json"))


@router.put("/skills/{skill_id}")
async def update_skill(
    skill_id: uuid.UUID,
    payload: AgentSkillUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentService(settings).update_skill(
        db, skill_id=skill_id, request=payload, current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/skills/{skill_id}/enable")
async def enable_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentService(settings).set_skill_status(
        db, skill_id=skill_id, status_value="active", current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.post("/skills/{skill_id}/disable")
async def disable_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    result = await AgentService(settings).set_skill_status(
        db, skill_id=skill_id, status_value="disabled", current_user=current_user
    )
    return success_response(data=result.model_dump(mode="json"))


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    await AgentService(settings).delete_skill(
        db, skill_id=skill_id, current_user=current_user
    )
    return success_response(data={"ok": True})


@router.post("/confirmations/{confirmation_id}/execute")
async def execute_confirmation(
    confirmation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    confirmation, result = await AgentService(settings).execute_confirmation(
        db,
        confirmation_id=confirmation_id,
        current_user=current_user,
    )
    if result is None:
        return error_response(
            message="Agent confirmation has expired",
            status_code=status.HTTP_409_CONFLICT,
        )
    response = AgentConfirmationExecuteResponse(
        confirmation=AgentService(settings)._confirmation_out(confirmation),
        result=result,
    )
    return success_response(data=response.model_dump(mode="json"))


@router.post("/confirmations/{confirmation_id}/cancel")
async def cancel_confirmation(
    confirmation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: RequiredUser = None,
    settings: Settings = Depends(get_settings),
):
    confirmation = await AgentService(settings).cancel_confirmation(
        db,
        confirmation_id=confirmation_id,
        current_user=current_user,
    )
    return success_response(
        data=AgentService(settings)
        ._confirmation_out(confirmation)
        .model_dump(mode="json")
    )


@router.post("/confirmations/{confirmation_id}/resolve")
async def resolve_confirmation_from_gateway(
    confirmation_id: uuid.UUID,
    payload: AgentConfirmationResolveRequest,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_TOOL_TOKEN, authorization)
    user = await db.get(User, payload.subject.user_id)
    if user is None or user.is_deleted or user.status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Trusted subject is not active")
    service = AgentService(settings)
    if payload.choice == "reject":
        confirmation = await service.cancel_confirmation(
            db,
            confirmation_id=confirmation_id,
            current_user=user,
        )
        return success_response(
            data={
                "confirmation": service._confirmation_out(confirmation).model_dump(
                    mode="json"
                )
            }
        )
    confirmation, result = await service.execute_confirmation(
        db,
        confirmation_id=confirmation_id,
        current_user=user,
    )
    if result is None:
        return error_response(
            message="Agent confirmation has expired",
            status_code=status.HTTP_409_CONFLICT,
        )
    return success_response(
        data={
            "confirmation": service._confirmation_out(confirmation).model_dump(
                mode="json"
            ),
            "result": result.model_dump(mode="json"),
        }
    )


@router.get("/llm/models")
async def agent_llm_models(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_LLM_PROXY_TOKEN, authorization)
    return await list_active_text_models()


@router.post("/llm/chat/completions")
async def agent_llm_chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    require_service_token(settings.AGENT_LLM_PROXY_TOKEN, authorization)
    payload: dict[str, Any] = await request.json()
    return await forward_chat_completion(payload)
