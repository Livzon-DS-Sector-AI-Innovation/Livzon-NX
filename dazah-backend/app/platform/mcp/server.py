"""Legacy MCP registrations remain importable; the HTTP transport is retired."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from starlette.middleware import Middleware

# 全局 FastMCP 实例
mcp = FastMCP("dazah-mcp")


def create_mcp_server() -> FastMCP:
    """Return the legacy registration object, without exposing a transport."""
    return mcp


def get_mcp_app(path: str = "/mcp", middleware: list[Middleware] | None = None) -> Any:
    """Refuse legacy HTTP mounts, even when called without middleware."""
    raise RuntimeError(
        "Legacy MCP transport is retired; use the authenticated Agent tool gateway"
    )
