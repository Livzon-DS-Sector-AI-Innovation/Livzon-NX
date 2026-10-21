"""Small, non-HTTP identity capabilities shared by business modules."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.platform.identity.models import User
from app.platform.identity.repository import FeishuConfigRepository, UserRepository


async def has_current_page_permission(
    db: AsyncSession,
    user: User | None,
    module_code: str,
    permission: Literal["query", "operate"] = "operate",
    sensitive_action: str | None = None,
) -> bool:
    """Check the exact trusted request page; legacy module codes never widen it."""
    from app.platform.identity.data_scope import current_page_key
    from app.platform.identity.page_permissions import PagePermissionService
    from app.platform.identity.page_policy import get_page_definition

    page_key = current_page_key.get()
    definition = get_page_definition(page_key) if page_key else None
    if user is None or definition is None or definition.module_code != module_code:
        return False
    grants = await PagePermissionService().effective_grants(db, user=user)
    return any(
        grant.page_key == page_key
        and permission in grant.permissions
        and (
            sensitive_action is None
            or "operate" in grant.permissions
            and sensitive_action in grant.sensitive_actions
        )
        for grant in grants
    )


@dataclass(frozen=True)
class ActiveUserOption:
    id: UUID
    name: str
    department: str


async def list_active_user_options(db: AsyncSession) -> list[ActiveUserOption]:
    """Minimal assignable identities; no authentication or contact secrets."""
    rows = await db.scalars(
        select(User)
        .where(User.status == "active", User.is_deleted.is_(False))
        .order_by(User.name)
        .limit(5000)
    )
    return [
        ActiveUserOption(user.id, user.name, user.department or "") for user in rows
    ]


async def notification_recipient_for_user(
    db: AsyncSession, user_id: UUID
) -> tuple[str, str] | None:
    """Resolve enterprise identifiers without reusing another app's open_id."""
    user = await UserRepository().get_by_id(db, user_id)
    if user is None or user.is_deleted or user.status != "active":
        return None
    if user.feishu_user_id:
        return user.feishu_user_id, "user_id"
    if user.enterprise_email:
        return user.enterprise_email, "email"
    return None


@dataclass(frozen=True)
class FeishuAppCredentials:
    """Decrypted credentials kept only in the current backend call."""

    app_id: str
    app_secret: str


async def get_platform_feishu_app_credentials(
    db: AsyncSession,
) -> FeishuAppCredentials | None:
    """Resolve explicitly configured platform application credentials only."""
    stored = await FeishuConfigRepository().get_active(db)

    if stored is not None:
        app_id = stored.app_id.strip()
        app_secret = decrypt_secret(stored.encrypted_app_secret)
    else:
        return None

    if not app_id or not app_secret:
        return None
    return FeishuAppCredentials(app_id=app_id, app_secret=app_secret)


async def resolve_feishu_notification_recipient(
    db: AsyncSession, receive_id: str, receive_id_type: str
) -> tuple[str, str] | None:
    """将已知登录应用 open_id 转为企业 user_id，避免跨应用误用 open_id。"""
    if receive_id_type != "open_id":
        return receive_id, receive_id_type
    user = await UserRepository().get_by_feishu_open_id(db, receive_id)
    if user is None:
        # 未匹配平台用户的标识由调用模块负责，可能已属于业务应用。
        return receive_id, receive_id_type
    if user.feishu_user_id:
        return user.feishu_user_id, "user_id"
    if user.enterprise_email:
        return user.enterprise_email, "email"
    return None
