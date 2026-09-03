"""Serialize administrative authorization writes and recheck queued actors."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import User
from app.platform.identity.rbac import lock_admin_changes


async def lock_authorization_actor(db: AsyncSession, actor: User) -> User:
    # Reuse the last-administrator transaction lock. Acquire it before any
    # role/user/rollout row locks so different management paths cannot deadlock.
    await lock_admin_changes(db)
    user = await db.scalar(
        select(User)
        .where(User.id == actor.id)
        .execution_options(populate_existing=True)
    )
    if user is None or user.is_deleted or user.status != "active":
        raise HTTPException(403, "当前账号已停用，请重新登录")
    return user
