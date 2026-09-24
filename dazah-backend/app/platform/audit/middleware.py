import json
import logging
import re
import time
import uuid
from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match

from app.core.database import async_session_factory
from app.core.redaction import is_sensitive_key, redact_sensitive
from app.platform.audit.models import AuditLog
from app.platform.identity.rbac import match_module

logger = logging.getLogger(__name__)
OPERATION_ACTION = "platform_api_request"
MAX_BODY_BYTES = 16_384
MAX_FIELD_LENGTH = 500
SENSITIVE_ROUTE_PARTS = ("/auth/", "/llm/", "/agent/")
current_audit_request_id: ContextVar[str | None] = ContextVar(
    "current_audit_request_id", default=None
)


def _sensitive_field(key: object) -> bool:
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key))
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized)
    return is_sensitive_key(normalized)


def _mask_body_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "***" if _sensitive_field(key) else _mask_body_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_body_fields(item) for item in value]
    return value


def _safe_mapping(values: list[tuple[str, str]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values[:100]:
        safe_key = key[:100] + ("[truncated]" if len(key) > 100 else "")
        safe_value = (
            "***"
            if _sensitive_field(key)
            else value[:MAX_FIELD_LENGTH]
            + ("[truncated]" if len(value) > MAX_FIELD_LENGTH else "")
        )
        if safe_key in result:
            existing = result[safe_key]
            result[safe_key] = (
                [*existing, safe_value]
                if isinstance(existing, list)
                else [existing, safe_value]
            )
        else:
            result[safe_key] = safe_value
    if len(values) > 100:
        result["_truncated"] = True
    return result


def _route_params(request: Request) -> dict[str, Any]:
    for route in request.app.router.routes:
        match, scope = route.matches(request.scope)
        if match is Match.FULL:
            params = scope.get("path_params", {})
            return {
                str(key): (
                    "***"
                    if _sensitive_field(key)
                    else redact_sensitive(value, max_string_length=MAX_FIELD_LENGTH)
                )
                for key, value in params.items()
            }
    return {}


async def _request_body(request: Request) -> tuple[Any, str | None]:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None, None
    if any(part in request.url.path for part in SENSITIVE_ROUTE_PARTS):
        return None, "sensitive_route"
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type.strip().lower() != "application/json":
        return None, "non_json"
    size = request.headers.get("content-length")
    if size is None or not size.isdecimal() or int(size) > MAX_BODY_BYTES:
        return None, "size_unknown_or_exceeded"
    try:
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return None, "size_exceeded"
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None, "invalid_json"
    bounded_body = redact_sensitive(
        parsed, max_depth=8, max_string_length=MAX_FIELD_LENGTH
    )
    return _mask_body_fields(bounded_body), None


def _route_details(request: Request) -> tuple[str, str, str] | None:
    matched_route = request.scope.get("route")
    routes = (
        (matched_route,) if matched_route is not None else request.app.router.routes
    )
    for route in routes:
        if route.matches(request.scope)[0] is not Match.FULL:
            continue
        template = getattr(route, "path", None)
        if not template or not template.startswith("/api/v1/"):
            return None
        module = match_module(template)
        if module is None:
            segment = template.split("/")[3]
            module = {
                "audit": "audit",
                "agent": "agent",
                "storage": "storage",
                "product": "product",
                "dossier-writer": "dossier_writer",
            }.get(segment, segment.replace("-", "_"))
        operation = getattr(route, "summary", None) or getattr(route, "name", None)
        return template, module, str(operation or request.method)
    return None


class AuditMiddleware(BaseHTTPMiddleware):
    """Persist one safe audit record for each identified user's API request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()
        request.state.request_id = request_id
        body, body_omission = await _request_body(request)
        sensitive_route = any(
            part in request.url.path for part in SENSITIVE_ROUTE_PARTS
        )
        request_details: dict[str, Any] = {
            "path_params": {} if sensitive_route else _route_params(request),
            "query_params": {}
            if sensitive_route
            else _safe_mapping(list(request.query_params.multi_items())),
            "content_type": request.headers.get("content-type", "").split(";", 1)[0][
                :100
            ] or None,
        }
        if sensitive_route:
            request_details["parameters_omitted"] = "sensitive_route"
        if body is not None:
            request_details["body"] = body
        if body_omission:
            request_details["body_omitted"] = body_omission

        context_token = current_audit_request_id.set(request_id)
        try:
            try:
                response = await call_next(request)
            except Exception:
                await self._record(
                    request, request_id, start_time, 500, request_details
                )
                raise
        finally:
            current_audit_request_id.reset(context_token)
        duration_ms = round((time.monotonic() - start_time) * 1000)
        await self._record(
            request, request_id, start_time, response.status_code, request_details,
            duration_ms, response.headers.get("content-length"),
        )
        response.headers["X-Request-ID"] = request_id
        return response

    async def _record(
        self,
        request: Request,
        request_id: str,
        start_time: float,
        status_code: int,
        request_details: dict[str, Any],
        duration_ms: int | None = None,
        response_bytes: str | None = None,
    ) -> None:
        actor_id = getattr(request.state, "audit_user_id", None)
        if actor_id is None or request.method == "OPTIONS":
            return
        route = _route_details(request)
        if route is None:
            return
        path, module, operation = route
        path_params = request_details["path_params"]
        target = ", ".join(f"{key}={value}" for key, value in path_params.items())
        resource_id = None
        if len(path_params) == 1:
            try:
                resource_id = uuid.UUID(str(next(iter(path_params.values()))))
            except (ValueError, TypeError, AttributeError):
                pass
        response_detail: dict[str, Any] = {"status_code": status_code}
        if response_bytes and response_bytes.isdecimal():
            response_detail["content_length"] = int(response_bytes)
        try:
            async with async_session_factory() as db:
                db.add(
                    AuditLog(
                        request_id=request_id,
                        user_id=actor_id,
                        action=OPERATION_ACTION,
                        resource_type=module,
                        resource_id=resource_id,
                        method=request.method,
                        path=path,
                        status_code=status_code,
                        duration_ms=duration_ms
                        if duration_ms is not None
                        else round((time.monotonic() - start_time) * 1000),
                        ip_address=request.client.host[:64] if request.client else None,
                        user_agent=request.headers.get("user-agent", "")[:500] or None,
                        extra={
                            "operation": operation,
                            "target": target or None,
                            "request": request_details,
                            "response": response_detail,
                        },
                    )
                )
                await db.commit()
        except Exception:
            logger.exception(
                "User operation audit write failed: request_id=%s route=%s",
                request_id,
                path,
            )
