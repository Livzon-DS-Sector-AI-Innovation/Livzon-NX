import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypeVar, cast, get_type_hints

from fastapi import HTTPException, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import normalize_correlation_id
from app.platform.audit.models import AuditLog
from app.platform.identity.models import User
from app.shared.module_registry import MODULES_BY_CODE

from .models import AgentAutomationGrant, AgentConfirmation
from .repository import AgentRepository
from .schemas import AgentToolExecuteRequest, AgentToolExecuteResponse

RiskLevel = Literal["low", "medium", "high"]
ToolHandler = Callable[["ToolContext", BaseModel], Awaitable[Any] | Any]
ToolCallable = TypeVar("ToolCallable", bound=Callable[..., Any])


@dataclass(frozen=True)
class ToolContext:
    db: AsyncSession
    session_id: uuid.UUID | None
    user_id: uuid.UUID | None
    user: User | None
    reason: str | None
    raw_request: AgentToolExecuteRequest
    agent_service: Any = None
    confirmation_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    summary: str
    input_model: type[BaseModel]
    handler: ToolHandler
    write: bool = False
    confirmation_required: bool = False
    risk_level: RiskLevel = "medium"
    required_roles: tuple[str, ...] = ()
    workflow_allowed: bool = True
    human_decision_required: bool = False
    method: str = "TOOL"
    path: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_hint: str = ""
    capability_version: str = "1.0"
    module: str | None = None
    permission_key: str | None = None
    data_scope_type: str | None = None
    sensitivity: Literal["public", "internal", "sensitive", "restricted"] = "internal"
    idempotent: bool = False
    supports_dry_run: bool = False
    timeout_seconds: int = 30
    output_schema: dict[str, Any] = field(default_factory=dict)
    events_emitted: tuple[str, ...] = ()
    deprecated_at: datetime | None = None
    replacement_operation: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "input_schema": self.input_schema or self.input_model.model_json_schema(),
            "risk_level": self.risk_level,
            "write": self.write,
            "confirmation_required": self.confirmation_required,
            "method": self.method,
            "path": self.path,
            "required_roles": list(self.required_roles),
            "workflow_allowed": self.workflow_allowed,
            "human_decision_required": self.human_decision_required,
            "output_hint": self.output_hint,
            "capability_version": self.capability_version,
            "module": self.module,
            "permission_key": self.permission_key,
            "data_scope_type": self.data_scope_type,
            "sensitivity": self.sensitivity,
            "idempotent": self.idempotent,
            "supports_dry_run": self.supports_dry_run,
            "timeout_seconds": self.timeout_seconds,
            "output_schema": self.output_schema,
            "events_emitted": list(self.events_emitted),
            "deprecated_at": self.deprecated_at.isoformat()
            if self.deprecated_at
            else None,
            "replacement_operation": self.replacement_operation,
        }


class EmptyToolInput(BaseModel):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentToolSpec] = {}

    def register(self, spec: AgentToolSpec) -> AgentToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"Agent tool already registered: {spec.name}")
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> AgentToolSpec | None:
        return self._tools.get(name)

    def require(self, name: str) -> AgentToolSpec:
        spec = self.get(name)
        if spec is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Operation is not in Agent tool registry",
            )
        return spec

    def list(self) -> list[AgentToolSpec]:
        return [self._tools[name] for name in sorted(self._tools)]

    def clear(self) -> None:
        self._tools.clear()


tool_registry = ToolRegistry()


def _inferred_output_schema(handler: Callable[..., Any]) -> dict[str, Any]:
    """Build a non-empty baseline contract from the handler return annotation."""
    try:
        annotation = get_type_hints(handler).get("return", Any)
        schema = TypeAdapter(annotation).json_schema()
    except (NameError, TypeError, ValueError):
        schema = {}
    if not schema:
        schema = {"type": "object", "additionalProperties": True}
    return {"x-dazah-schema-source": "return_annotation", **schema}


def agent_tool(
    *,
    name: str,
    summary: str,
    input_model: type[BaseModel] = EmptyToolInput,
    write: bool = False,
    confirmation_required: bool | None = None,
    risk_level: RiskLevel = "medium",
    required_roles: tuple[str, ...] | list[str] = (),
    workflow_allowed: bool | None = None,
    human_decision_required: bool = False,
    method: str = "TOOL",
    path: str = "",
    input_schema: dict[str, Any] | None = None,
    output_hint: str = "",
    capability_version: str = "1.0",
    module: str | None = None,
    permission_key: str | None = None,
    data_scope_type: str | None = None,
    sensitivity: Literal["public", "internal", "sensitive", "restricted"] = "internal",
    idempotent: bool = False,
    supports_dry_run: bool = False,
    timeout_seconds: int = 30,
    output_schema: dict[str, Any] | None = None,
    events_emitted: tuple[str, ...] | list[str] = (),
    deprecated_at: datetime | None = None,
    replacement_operation: str | None = None,
    registry: ToolRegistry = tool_registry,
) -> Callable[[ToolCallable], ToolCallable]:
    def decorator(func: ToolCallable) -> ToolCallable:
        inferred_module = module or name.partition(".")[0]
        business_module = (
            inferred_module if inferred_module in MODULES_BY_CODE else None
        )
        inferred_permission_key = permission_key
        if inferred_permission_key is None and business_module is not None:
            inferred_permission_key = (
                "module.agent.execute" if write else "module.agent.read"
            )
        resolved_output_schema = (
            dict(output_schema) if output_schema else _inferred_output_schema(func)
        )
        spec = AgentToolSpec(
            name=name,
            summary=summary,
            input_model=input_model,
            handler=cast(ToolHandler, func),
            write=write,
            confirmation_required=(
                write if confirmation_required is None else confirmation_required
            ),
            risk_level=risk_level,
            required_roles=tuple(required_roles),
            workflow_allowed=(
                not human_decision_required
                if workflow_allowed is None
                else workflow_allowed
            ),
            human_decision_required=human_decision_required,
            method=method,
            path=path,
            input_schema=input_schema or input_model.model_json_schema(),
            output_hint=output_hint,
            capability_version=capability_version,
            module=business_module or module,
            permission_key=inferred_permission_key,
            data_scope_type=data_scope_type,
            sensitivity=sensitivity,
            idempotent=idempotent,
            supports_dry_run=supports_dry_run,
            timeout_seconds=timeout_seconds,
            output_schema=resolved_output_schema,
            events_emitted=tuple(events_emitted),
            deprecated_at=deprecated_at,
            replacement_operation=replacement_operation,
        )
        registry.register(spec)
        return func

    return decorator


class ToolExecutor:
    def __init__(
        self,
        *,
        registry: ToolRegistry = tool_registry,
        repo: AgentRepository | None = None,
        confirmation_ttl_seconds: int = 300,
        access_scope_service: Any = None,
    ) -> None:
        self.registry = registry
        self.repo = repo or AgentRepository()
        self.confirmation_ttl_seconds = confirmation_ttl_seconds
        if access_scope_service is None:
            from .access_scope import AgentAccessScopeService

            access_scope_service = AgentAccessScopeService()
        self.access_scope_service = access_scope_service

    async def execute(
        self,
        db: AsyncSession,
        *,
        request: AgentToolExecuteRequest,
        agent_service: Any = None,
    ) -> AgentToolExecuteResponse:
        spec = self.registry.require(request.operation)
        session_id, user_id, user = await self._resolve_identity(db, request)
        if user_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Trusted Agent subject is missing a local user identity",
            )
        call = await self.repo.create_tool_call(
            db,
            session_id=session_id,
            operation=request.operation,
            request_payload=self._sanitize_request(request),
        )

        try:
            await self._check_catalog_enabled(db, operation=request.operation)
            if spec.human_decision_required:
                result = self._policy_refusal(request.operation)
                await self.repo.finish_tool_call(
                    db,
                    call,
                    status="rejected_by_policy",
                    response_payload=result.model_dump(mode="json"),
                )
                await self._write_audit(
                    db,
                    action="agent_tool_reject",
                    spec=spec,
                    request=request,
                    session_id=session_id,
                    user_id=user_id,
                    status_value="rejected_by_policy",
                    response_payload=result.model_dump(mode="json"),
                )
                return result
            try:
                validated = self._validate_input(spec, request)
            except HTTPException as exc:
                result = AgentToolExecuteResponse(
                    ok=False,
                    operation=request.operation,
                    data={"message": str(exc.detail)},
                    meta={"validation": "failed"},
                )
                await self.repo.finish_tool_call(
                    db,
                    call,
                    status="invalid_request",
                    response_payload=result.model_dump(mode="json"),
                )
                await self._write_audit(
                    db,
                    action="agent_tool_execute",
                    spec=spec,
                    request=request,
                    session_id=session_id,
                    user_id=user_id,
                    status_value="invalid_request",
                    response_payload=result.model_dump(mode="json"),
                )
                return result
            self._check_permission(spec, user)
            await self._check_access_scope(
                db,
                spec=spec,
                user=user,
                for_workflow=request.subject.source == "automation",
            )

            automation_authorized = (
                request.subject.source == "automation"
                and await self._is_automation_write_authorized(
                    db, spec=spec, request=request, user_id=user_id
                )
            )
            if spec.write and spec.confirmation_required and not automation_authorized:
                confirmation = await self._create_confirmation(
                    db,
                    spec=spec,
                    request=request,
                    session_id=session_id,
                    user_id=user_id,
                )
                result = AgentToolExecuteResponse(
                    ok=True,
                    operation=request.operation,
                    data=None,
                    requires_confirmation=True,
                    confirmation=agent_service._confirmation_out(confirmation)
                    if agent_service is not None
                    else None,
                )
                await self.repo.finish_tool_call(
                    db,
                    call,
                    status="confirmation_required",
                    response_payload=result.model_dump(mode="json"),
                )
                await self._write_audit(
                    db,
                    action="agent_tool_execute",
                    spec=spec,
                    request=request,
                    session_id=session_id,
                    user_id=user_id,
                    confirmation_id=confirmation.id,
                    status_value="confirmation_required",
                    response_payload=result.model_dump(mode="json"),
                )
                return result

            result = await self._invoke_tool(
                db,
                spec=spec,
                request=request,
                validated=validated,
                session_id=session_id,
                user_id=user_id,
                user=user,
                agent_service=agent_service,
            )
            await self.repo.finish_tool_call(
                db,
                call,
                status="succeeded",
                response_payload=result.model_dump(mode="json"),
            )
            await self._write_audit(
                db,
                action="agent_tool_execute",
                spec=spec,
                request=request,
                session_id=session_id,
                user_id=user_id,
                status_value="succeeded",
                response_payload=result.model_dump(mode="json"),
            )
            return result
        except HTTPException as exc:
            await self.repo.finish_tool_call(
                db,
                call,
                status="invalid_request"
                if exc.status_code == status.HTTP_400_BAD_REQUEST
                else "failed",
                error_message=str(exc.detail),
            )
            await self._write_audit(
                db,
                action="agent_tool_execute",
                spec=spec,
                request=request,
                session_id=session_id,
                user_id=user_id,
                status_value="failed",
                error_message=str(exc.detail),
            )
            raise

        except Exception as exc:
            await self.repo.finish_tool_call(
                db,
                call,
                status="failed",
                error_message=str(exc),
            )
            await self._write_audit(
                db,
                action="agent_tool_execute",
                spec=spec,
                request=request,
                session_id=session_id,
                user_id=user_id,
                status_value="failed",
                error_message=str(exc),
            )
            raise

    @staticmethod
    async def _is_automation_write_authorized(
        db: AsyncSession,
        *,
        spec: AgentToolSpec,
        request: AgentToolExecuteRequest,
        user_id: uuid.UUID,
    ) -> bool:
        if spec.human_decision_required or not spec.workflow_allowed:
            return False
        context = request.execution_context
        try:
            grant_id = uuid.UUID(str(context.get("automation_grant_id")))
            automation_id = uuid.UUID(str(context.get("workflow_id")))
            version_id = uuid.UUID(str(context.get("automation_version_id")))
        except (TypeError, ValueError, AttributeError):
            return False
        result = await db.execute(
            select(AgentAutomationGrant).where(
                AgentAutomationGrant.id == grant_id,
                AgentAutomationGrant.automation_id == automation_id,
                AgentAutomationGrant.version_id == version_id,
                AgentAutomationGrant.owner_user_id == user_id,
                AgentAutomationGrant.status == "active",
                AgentAutomationGrant.is_deleted.is_(False),
            )
        )
        grant = result.scalar_one_or_none()
        if grant is None:
            return False
        operations = grant.authorization_scope.get("operations") or []
        return spec.name in operations

    async def execute_confirmed(
        self,
        db: AsyncSession,
        *,
        request: AgentToolExecuteRequest,
        current_user: User,
        confirmation: AgentConfirmation,
        agent_service: Any = None,
    ) -> AgentToolExecuteResponse:
        spec = self.registry.require(request.operation)
        await self._check_catalog_enabled(db, operation=request.operation)
        if not spec.write:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Confirmation operation is invalid",
            )
        if spec.human_decision_required:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                HUMAN_DECISION_REQUIRED_MESSAGE,
            )
        validated = self._validate_input(spec, request)
        self._check_permission(spec, current_user)
        await self._check_access_scope(
            db,
            spec=spec,
            user=current_user,
            for_workflow=request.subject.source == "automation",
        )
        result = await self._invoke_tool(
            db,
            spec=spec,
            request=request,
            validated=validated,
            session_id=confirmation.session_id,
            user_id=current_user.id,
            user=current_user,
            agent_service=agent_service,
            confirmation_id=confirmation.id,
        )
        await self._write_audit(
            db,
            action="agent_tool_confirm",
            spec=spec,
            request=request,
            session_id=confirmation.session_id,
            user_id=current_user.id,
            confirmation_id=confirmation.id,
            status_value="succeeded",
            response_payload=result.model_dump(mode="json"),
        )
        return result

    async def _check_catalog_enabled(
        self,
        db: AsyncSession,
        *,
        operation: str,
    ) -> None:
        # Isolated registries and lightweight unit-test DB doubles do not
        # participate in the platform's synchronized administration catalog.
        if self.registry is not tool_registry or not isinstance(db, AsyncSession):
            return
        from .catalog import ToolCatalogService

        await ToolCatalogService().require_enabled(db, operation=operation)

    def _validate_input(
        self,
        spec: AgentToolSpec,
        request: AgentToolExecuteRequest,
    ) -> BaseModel:
        payload = {**request.params, **(request.body or {})}
        try:
            return spec.input_model.model_validate(payload)
        except ValidationError as exc:
            errors = exc.errors()
            if errors:
                first = errors[0]
                loc = ".".join(str(part) for part in first.get("loc", ()))
                message = first.get("msg") or str(exc)
                detail = f"{loc}: {message}" if loc else message
            else:
                detail = str(exc)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail) from exc

    def _check_permission(self, spec: AgentToolSpec, user: User | None) -> None:
        if not spec.required_roles:
            return
        if user is None or user.role not in spec.required_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Agent tool permission denied",
            )

    async def _check_access_scope(
        self,
        db: AsyncSession,
        *,
        spec: AgentToolSpec,
        user: User | None,
        for_workflow: bool = False,
    ) -> None:
        await self.access_scope_service.require_tool_access(
            db,
            user=user,
            tool_name=spec.name,
            module=spec.module,
            for_workflow=for_workflow,
        )

    async def _invoke_tool(
        self,
        db: AsyncSession,
        *,
        spec: AgentToolSpec,
        request: AgentToolExecuteRequest,
        validated: BaseModel,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        user: User | None,
        agent_service: Any,
        confirmation_id: uuid.UUID | None = None,
    ) -> AgentToolExecuteResponse:
        context = ToolContext(
            db=db,
            session_id=session_id,
            user_id=user_id,
            user=user,
            reason=request.reason,
            raw_request=request,
            agent_service=agent_service,
            confirmation_id=confirmation_id,
            correlation_id=normalize_correlation_id(request.trace_id),
        )
        data = spec.handler(context, validated)
        if inspect.isawaitable(data):
            data = await data
        return AgentToolExecuteResponse(
            ok=True,
            operation=request.operation,
            data=data,
            meta={
                "trace_id": str(request.trace_id),
                "policy": {
                    "decision": "allow",
                    "resource_domain": "dazah_business",
                    "risk_level": spec.risk_level,
                },
            },
        )

    async def _create_confirmation(
        self,
        db: AsyncSession,
        *,
        spec: AgentToolSpec,
        request: AgentToolExecuteRequest,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
    ) -> AgentConfirmation:
        return await self.repo.create_confirmation(
            db,
            session_id=session_id,
            user_id=user_id,
            operation=request.operation,
            summary=request.reason or spec.summary or request.operation,
            risk_level=spec.risk_level,
            request_payload=request.model_dump(mode="json"),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=self.confirmation_ttl_seconds),
        )

    async def _resolve_identity(
        self,
        db: AsyncSession,
        request: AgentToolExecuteRequest,
    ) -> tuple[uuid.UUID | None, uuid.UUID | None, User | None]:
        session_id = request.session_id
        user_id = request.subject.user_id
        if session_id is not None:
            session = await self.repo.get_session(db, session_id)
            if session and user_id is not None and session.user_id != user_id:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Agent session identity does not match acting user",
                )
        user = None
        if user_id is not None and hasattr(db, "get"):
            user = await db.get(User, user_id)
            if user and (
                getattr(user, "is_deleted", False)
                or getattr(user, "status", None) != "active"
            ):
                user = None
        if user is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Trusted Agent subject is not an active local user",
            )
        return session_id, user_id, user

    async def _write_audit(
        self,
        db: AsyncSession,
        *,
        action: str,
        spec: AgentToolSpec,
        request: AgentToolExecuteRequest,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        status_value: str,
        confirmation_id: uuid.UUID | None = None,
        response_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        if not hasattr(db, "add"):
            return
        audit = AuditLog(
            request_id=str(normalize_correlation_id(request.trace_id)),
            user_id=user_id,
            method="AGENT",
            path=f"agent://tools/{spec.name}",
            status_code=(
                200 if status_value in {"succeeded", "confirmation_required"} else 400
            ),
            resource_type="agent_tool",
            action=action,
            new_value=self._truncate_payload(response_payload),
            extra={
                "operation": spec.name,
                "risk_level": spec.risk_level,
                "write": spec.write,
                "session_id": str(session_id) if session_id else None,
                "confirmation_id": str(confirmation_id) if confirmation_id else None,
                "status": status_value,
                "request": self._sanitize_request(request),
                "error_message": error_message,
            },
        )
        db.add(audit)

    @staticmethod
    def _sanitize_request(request: AgentToolExecuteRequest) -> dict[str, Any]:
        from app.core.redaction import redact_sensitive

        data = request.model_dump(mode="json")
        return cast(
            dict[str, Any],
            redact_sensitive(data, max_string_length=4000),
        )

    @staticmethod
    def _mask_secret_fields(value: dict[str, Any]) -> dict[str, Any]:
        masked: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(
                token in key_lower for token in ("secret", "token", "password", "key")
            ):
                masked[key] = "***"
            elif isinstance(item, dict):
                masked[key] = ToolExecutor._mask_secret_fields(item)
            else:
                masked[key] = item
        return masked

    @staticmethod
    def _truncate_payload(value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        from app.core.redaction import redact_sensitive

        sanitized = cast(
            dict[str, Any],
            redact_sensitive(value, max_string_length=4000),
        )
        text = str(sanitized)
        if len(text) <= 4000:
            return sanitized
        return {"truncated": True, "preview": text[:4000]}

    @staticmethod
    def _policy_refusal(operation: str) -> AgentToolExecuteResponse:
        return AgentToolExecuteResponse(
            ok=False,
            operation=operation,
            data={"message": HUMAN_DECISION_REQUIRED_MESSAGE},
            meta={"policy": "human_decision_required"},
        )

    @staticmethod
    def _uuid_or_none(value: Any) -> uuid.UUID | None:
        if not value:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except ValueError:
            return None


HUMAN_DECISION_REQUIRED_MESSAGE = (
    "抱歉，我不能代你完成审批决定、批准、驳回、拒绝或关键连接重启等"
    "需要最终责任判断的高风险操作。"
    "请你在对应业务页面自行查看资料、评估风险并手动操作；我可以帮助你查询待处理事项、"
    "整理背景信息或生成意见草稿供你参考。普通消息发送和其他可确认写操作不会被此策略拦截，"
    "系统会生成待确认项供你核对后执行。"
)
