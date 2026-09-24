import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match

from app.core.database import async_session_factory
from app.platform.audit.models import AuditLog
from app.platform.identity.rbac import match_module

logger = logging.getLogger(__name__)
OPERATION_ACTION = "platform_api_request"


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

        try:
            response = await call_next(request)
        except Exception:
            await self._record(request, request_id, start_time, 500)
            raise
        duration_ms = round((time.monotonic() - start_time) * 1000)
        await self._record(
            request, request_id, start_time, response.status_code, duration_ms
        )
        response.headers["X-Request-ID"] = request_id
        return response

    async def _record(
        self,
        request: Request,
        request_id: str,
        start_time: float,
        status_code: int,
        duration_ms: int | None = None,
    ) -> None:
        actor_id = getattr(request.state, "audit_user_id", None)
        if actor_id is None or request.method == "OPTIONS":
            return
        route = _route_details(request)
        if route is None:
            return
        path, module, operation = route
        try:
            async with async_session_factory() as db:
                db.add(
                    AuditLog(
                        request_id=request_id,
                        user_id=actor_id,
                        action=OPERATION_ACTION,
                        resource_type=module,
                        method=request.method,
                        path=path,
                        status_code=status_code,
                        duration_ms=duration_ms
                        if duration_ms is not None
                        else round((time.monotonic() - start_time) * 1000),
                        extra={"operation": operation},
                    )
                )
                await db.commit()
        except Exception:
            logger.exception(
                "User operation audit write failed: request_id=%s route=%s",
                request_id,
                path,
            )
