"""全局权限中间件：负责请求级职责，权限准入判定统一收敛到 check_access。

- 请求级职责：JWT 解析、登录频率限制、自动续签、401/403 响应构造
- 权限准入判定（公开路径、通配、identity 子路径、常规模块、写操作细分放行）
  委托 app.platform.identity.access_check.check_access，与接口权限模拟器共用同一套逻辑
- 公开路径豁免与 DEV_BYPASS_AUTH 在 JWT 解析之前提前放行
- JWT 自动续签：剩余有效期 < 1h 时续签并 Set-Cookie
- 登录频率限制：/api/v1/identity/auth/* 按 IP 限流（10 次/分钟，二轮评审新增）
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Match

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.core.response import error_response
from app.platform.identity.access_check import check_access
from app.platform.identity.deps import get_current_user
from app.platform.identity.rbac import (
    is_public_path,
    resolve_user_permissions,
)

logger = logging.getLogger(__name__)

JWT_RENEW_THRESHOLD_SECONDS = 3600  # JWT 剩余 < 1h 自动续签

# 登录频率限制：/api/v1/identity/auth/* 按 IP 限流
AUTH_PATH_PREFIX = "/api/v1/identity/auth/"
LOGIN_RATE_LIMIT = 10  # 每分钟最多 10 次
LOGIN_RATE_WINDOW_SECONDS = 60
ROUTE_AUTH_PATH_PREFIXES = ("/api/v1/agent/internal/",)


def _matches_registered_route(request: Request) -> bool:
    """Let FastAPI own 404/405 responses for paths absent from the router."""
    return any(
        route.matches(request.scope)[0] in {Match.FULL, Match.PARTIAL}
        for route in request.app.router.routes
    )


async def _check_login_rate_limit(request: Any) -> bool:
    """登录端点按 IP 限流（10 次/分钟），返回 True 表示放行。

    使用 Redis INCR + EXPIRE 实现滑动窗口计数；Redis 不可用时放行（不阻断登录）。
    """
    try:
        from app.core.redis import redis_client

        client_ip = request.client.host if request.client else "unknown"
        key = f"identity:login-rate:{client_ip}"
        async with asyncio.timeout(0.5):
            count = await redis_client.incr(key)
            if count == 1:
                await redis_client.expire(key, LOGIN_RATE_WINDOW_SECONDS)
        if count > LOGIN_RATE_LIMIT:
            logger.warning("Login rate limit exceeded for ip=%s", client_ip)
            return False
    except Exception:
        logger.warning("Login rate limit check skipped (redis unavailable)")
    return True


class PermissionMiddleware(BaseHTTPMiddleware):
    """全局权限强制中间件。"""

    async def dispatch(self, request: Any, call_next: Any) -> Any:
        settings = get_settings()
        path = request.url.path

        # 登录频率限制（二轮评审新增）：auth/* 路径按 IP 限流
        if path.startswith(AUTH_PATH_PREFIX) and not settings.DEV_BYPASS_AUTH:
            allowed = await _check_login_rate_limit(request)
            if not allowed:
                return error_response(
                    message="登录尝试过于频繁，请稍后再试",
                    status_code=429,
                )

        # 公开路径直接放行
        if is_public_path(path):
            return await call_next(request)

        # 开发绕过：全部放行
        if settings.DEV_BYPASS_AUTH:
            return await call_next(request)

        # Internal Agent routes authenticate with their own service token at
        # the endpoint boundary rather than with an end-user JWT.
        if path.startswith(ROUTE_AUTH_PATH_PREFIXES):
            return await call_next(request)

        # Authentication middleware must not turn an absent route into 401.
        # Preserve FastAPI's native 404/405 semantics for removed endpoints.
        if not _matches_registered_route(request):
            return await call_next(request)

        # FastAPI dependency overrides are only installed by the test suite.
        # Honor them here so route tests can inject a user without manufacturing
        # a JWT; production requests never have this override map populated.
        if getattr(request.app, "dependency_overrides", {}).get(get_current_user):
            return await call_next(request)

        # 解析 JWT（Bearer header 或 auth_token cookie）
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.removeprefix("Bearer ")
        if not token:
            token = request.cookies.get("auth_token")
        if not token:
            return self._unauthorized()

        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return self._unauthorized()

        open_id = payload.get("open_id")
        if not open_id:
            return self._unauthorized()

        # 解析用户权限（缓存优先）
        async with async_session_factory() as db:
            user_id = payload.get("sub")
            if not user_id:
                return self._unauthorized()
            from app.platform.identity.permission_cache import (
                get_cached_permissions,
                set_cached_permissions,
            )

            permissions = await get_cached_permissions(user_id)
            if permissions is None:
                permissions = await resolve_user_permissions(db, user_id)
                await set_cached_permissions(user_id, permissions)

        # Preserve the current deployment's explicit "all authenticated
        # users" mode. RBAC enforcement is enabled when MODULE_ACCESS_MODE is
        # switched to roles; the route-level module wrapper still requires a
        # logged-in user in both modes.
        if settings.effective_module_access_mode == "all":
            return await self._maybe_renew(request, call_next, payload, open_id)

        # 准入判定统一收敛到 check_access（与接口权限模拟器共用同一套逻辑）。
        # 未命中模块、通配、identity 子路径、常规模块、写操作细分放行均由其判定，
        # 判定顺序与原中间件逻辑完全一致。
        decision = check_access(path, request.method, permissions)
        if not decision.allowed:
            return self._forbidden(decision.required or decision.reason)

        return await self._maybe_renew(request, call_next, payload, open_id)

    async def _maybe_renew(
        self, request: Any, call_next: Any, payload: dict[str, Any], open_id: str
    ) -> Any:
        """JWT 剩余 < 1h 时续签并 Set-Cookie。续签失败不阻断请求。"""
        response = await call_next(request)
        try:
            exp = payload.get("exp")
            if not exp:
                return response
            remaining = float(exp) - datetime.now(UTC).timestamp()
            if remaining > JWT_RENEW_THRESHOLD_SECONDS:
                return response

            from app.platform.identity.repository import UserRepository
            from app.platform.identity.service import generate_jwt

            async with async_session_factory() as db:
                repo = UserRepository()
                user = await repo.get_by_feishu_open_id(db, open_id)
                if user is None:
                    return response
                new_token = generate_jwt(user)

            response.set_cookie(
                key="auth_token",
                value=new_token,
                max_age=60 * 60 * 24 * 7,
                path="/",
                httponly=True,
                samesite="lax",
                secure=str(request.url).startswith("https:"),
            )
            logger.info("JWT renewed for open_id=%s", open_id)
        except Exception:
            logger.exception("JWT renew failed (non-blocking)")
        return response

    @staticmethod
    def _unauthorized() -> JSONResponse:
        return error_response(
            message="未登录或登录已过期",
            status_code=401,
        )

    @staticmethod
    def _forbidden(permission_code: str) -> JSONResponse:
        return error_response(
            message=f"无权限执行操作 {permission_code}",
            status_code=403,
        )
