from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.platform.identity.data_scope import (
    current_page_actor,
    current_page_data_scope,
    current_page_key,
)
from app.platform.identity.models import User
from app.platform.identity.page_permission_repository import PagePermissionRepository
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.page_policy import (
    api_binding_for_route,
    api_route_catalog,
    get_page_definition,
    page_key_for_route,
)
from app.platform.identity.permission_repository import PermissionGrantRepository
from app.platform.identity.repository import UserRepository


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth_token: str | None = Cookie(default=None),
) -> User | None:
    """Resolve the current user from either:
    1. Authorization: Bearer <jwt> header (API clients)
    2. auth_token cookie (browser SSO flow)
    """
    token = None

    # 1. Try Bearer header first
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ")

    # 2. Fall back to cookie
    if not token and auth_token:
        token = auth_token

    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None

    repo = UserRepository()
    user: User | None = None

    subject: str | None = payload.get("sub")
    if subject:
        user = await repo.get_by_id(db, subject)

    if user is None:
        open_id: str | None = payload.get("open_id")
        if open_id:
            user = await repo.get_by_feishu_open_id(db, open_id)

    if user is None or user.status == "disabled":
        return None

    return user


CurrentUser = Annotated[User | None, Depends(get_current_user)]


async def require_current_user(current_user: CurrentUser) -> User:
    if current_user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return current_user


async def require_admin(current_user: CurrentUser) -> User:
    user = await require_current_user(current_user)
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    return user


def require_module_view(module_code: str) -> Callable[..., Awaitable[User]]:
    """Create a dependency enforcing the configured module access policy.

    In ``all`` mode any authenticated user can enter business modules. In
    ``roles`` mode module grants remain the authorization fact source. This
    dependency is applied when each business router is mounted so it also
    protects routes that predate the identity subsystem and did not previously
    declare a user dependency.
    """

    async def _require_module_view(
        request: Request,
        current_user: CurrentUser,
        db: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> User:
        user = await require_current_user(current_user)
        current_page_data_scope.set(None)
        current_page_actor.set(None)
        current_page_key.set(None)
        if getattr(user, "role", None) == "admin":
            current_page_actor.set(user)
            # Full authority does not remove the business page context: reviewed
            # handlers still need it for workflow/state and responsibility checks.
            binding = api_binding_for_route(
                request.method, getattr(request.scope.get("route"), "path", "")
            )
            if binding is not None:
                key = request.headers.get("X-Dazah-Page-Key")
                path = request.headers.get("X-Dazah-Page-Path")
                if not key and path:
                    key = page_key_for_route(path)
                if not key and len(binding.page_keys) == 1:
                    key = binding.page_keys[0]
                if not key:
                    raise HTTPException(400, "共享业务接口需要明确的页面上下文")
                if key not in binding.page_keys:
                    raise HTTPException(403, "当前页面不能调用此业务接口")
                if key in binding.page_keys:
                    current_page_key.set(key)
                    current_page_actor.set(user)
                    current_page_data_scope.set(
                        {"scope_type": "all", "department_ids": []}
                    )
            return user
        if (
            settings.effective_module_access_mode != "all"
            and not await PermissionGrantRepository().has_module_view(
                db,
                user_id=user.id,
                module_code=module_code,
            )
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"未获授权访问模块：{module_code}",
            )
        rollout = await PagePermissionRepository().get_rollout(
            db, module_code=module_code
        )
        if rollout is not None and rollout.status == "enforced":
            page_key = request.headers.get("X-Dazah-Page-Key")
            page_path = request.headers.get("X-Dazah-Page-Path")
            if not page_key and page_path:
                page_key = page_key_for_route(page_path)
            if not page_key:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "已发布模块必须提供明确的页面上下文",
                )
            definition = get_page_definition(page_key)
            if definition is None or definition.module_code != module_code:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "页面上下文与目标业务模块不匹配",
                )
            route_path = getattr(request.scope.get("route"), "path", "")
            binding = api_binding_for_route(request.method, route_path)
            if binding is None or not binding.scope_adapter:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "当前接口尚未完成页面权限和数据范围登记",
                )
            actual_routes = api_route_catalog(module_code)
            if (
                actual_routes is not None
                and actual_routes.count((request.method.upper(), route_path)) > 1
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "当前业务接口存在重复路由，暂不能执行",
                )
            if page_key not in binding.page_keys:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "当前页面不允许调用此业务接口",
                )
            grants = await PagePermissionService().effective_grants(db, user=user)
            grant = next((item for item in grants if item.page_key == page_key), None)
            required_permission = binding.permission
            if grant is None or required_permission not in grant.permissions:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    f"未获授权在页面“{definition.page_name}”执行当前业务请求",
                )
            sensitive_action = binding.sensitive_action
            if sensitive_action is not None:
                declared_actions = {
                    action.key for action in definition.sensitive_actions
                }
                if sensitive_action not in declared_actions:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        "当前页面不能发起该高风险业务动作",
                    )
                if sensitive_action not in grant.sensitive_actions:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        "未获得当前高风险业务动作授权",
                    )
            request.state.page_permission = grant
            current_page_data_scope.set(grant.data_scope.model_dump())
            current_page_actor.set(user)
            current_page_key.set(page_key)
            return user
        return user

    return _require_module_view


RequiredUser = Annotated[User, Depends(require_current_user)]
# Backwards-compatible name used by the migrated warehouse endpoints.
RequireUser = RequiredUser
AdminUser = Annotated[User, Depends(require_admin)]
