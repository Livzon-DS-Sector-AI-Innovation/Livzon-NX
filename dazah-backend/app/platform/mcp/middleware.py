"""Fail-closed compatibility shim for the retired legacy MCP transport.

Business tools are available only through the identity-aware Agent tool gateway.
An old shared MCP key must never create a database session or invoke a handler.
"""

from typing import Any

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """Reject every request, including alternate mounts and previously valid keys."""

    def __init__(self, app: Any, valid_keys: set[str]):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        return JSONResponse(
            status_code=403,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32001,
                    "message": "Legacy MCP retired; use the Agent tool gateway",
                },
                "id": None,
            },
        )


def validate_mcp_settings(*, enabled: bool, api_keys: str) -> set[str]:
    """No key or opt-in flag can reactivate the unscoped legacy tool surface."""
    if not enabled:
        raise RuntimeError("Legacy MCP transport is disabled and retired")
    raise RuntimeError(
        "Legacy MCP transport is retired; MCP_ENABLED cannot enable it. "
        "Use the authenticated Agent tool gateway."
    )


def build_mcp_middleware() -> list[Middleware]:
    """Retained for import compatibility; creating a legacy MCP app is forbidden."""
    raise RuntimeError("Legacy MCP transport is retired")
