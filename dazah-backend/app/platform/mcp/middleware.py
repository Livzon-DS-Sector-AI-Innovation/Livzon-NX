"""MCP 请求认证中间件。

负责：
1. 从 API-Key header 验证 Agent 身份
2. 为每个 MCP 请求创建/清理 DB session
3. 将 db session 写入 contextvars
"""

import logging

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.platform.mcp.deps import reset_context, set_context

logger = logging.getLogger(__name__)


class MCPAuthMiddleware(BaseHTTPMiddleware):
    """MCP 认证与 DB 会话中间件。

    只处理 /mcp 路径请求，验证 API Key 后创建数据库会话并写入 contextvars。
    请求结束后 commit（成功）或 rollback（失败），然后清理资源。
    """

    def __init__(self, app, valid_keys: set[str]):
        super().__init__(app)
        self._valid_keys = set(valid_keys)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        # 1. 验证 API Key
        api_key = request.headers.get("API-Key", "")
        if not api_key or api_key not in self._valid_keys:
            logger.warning(
                "MCP 请求 API Key 无效: %s...",
                api_key[:8] if api_key else "<empty>",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32001,
                        "message": "Agent API Key 无效或已过期",
                    },
                    "id": None,
                },
            )

        # 2. 创建 DB session
        db = async_session_factory()
        db_token, user_token = set_context(db, None)

        try:
            response = await call_next(request)
            await db.commit()
            return response
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()
            reset_context(db_token, user_token)


def build_mcp_middleware() -> list:
    """构建 MCP 应用的中间件列表，供 FastMCP http_app 使用。"""
    settings = get_settings()
    raw = settings.MCP_AGENT_API_KEYS
    valid_keys: set[str] = (
        {k.strip() for k in raw.split(",") if k.strip()} if raw else set()
    )
    return [
        Middleware(MCPAuthMiddleware, valid_keys=valid_keys),
    ]
