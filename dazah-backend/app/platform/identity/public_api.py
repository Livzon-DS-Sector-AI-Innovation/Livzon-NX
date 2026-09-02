"""Small, non-HTTP identity capabilities shared by business modules."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.platform.identity.repository import FeishuConfigRepository, UserRepository


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
