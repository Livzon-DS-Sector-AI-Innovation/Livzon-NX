from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.platform.identity.models import User, UserModuleGrant
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
        current_user: CurrentUser,
        db: AsyncSession = Depends(get_db),
        settings: Settings = Depends(get_settings),
    ) -> User:
        user = await require_current_user(current_user)
        if settings.effective_module_access_mode == "all":
            return user
        if user.role == "admin":
            return user
        result = await db.execute(
            select(UserModuleGrant.permissions).where(
                UserModuleGrant.user_id == user.id,
                UserModuleGrant.module_code == module_code,
                UserModuleGrant.status == "active",
                UserModuleGrant.is_deleted.is_(False),
            )
        )
        permissions = result.scalar_one_or_none()
        if permissions is None or "module.view" not in permissions:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"未获授权访问模块：{module_code}",
            )
        return user

    return _require_module_view


RequiredUser = Annotated[User, Depends(require_current_user)]
# Backwards-compatible name used by the migrated warehouse endpoints.
RequireUser = RequiredUser
AdminUser = Annotated[User, Depends(require_admin)]
