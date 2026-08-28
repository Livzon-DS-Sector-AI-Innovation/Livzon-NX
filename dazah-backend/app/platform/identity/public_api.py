"""Small, non-HTTP identity capabilities shared by business modules."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.secrets import decrypt_secret
from app.platform.identity.repository import FeishuConfigRepository


@dataclass(frozen=True)
class FeishuAppCredentials:
    """Decrypted credentials kept only in the current backend call."""

    app_id: str
    app_secret: str


async def get_platform_feishu_app_credentials(
    db: AsyncSession,
) -> FeishuAppCredentials | None:
    """Resolve active database credentials, then fall back to existing env config."""
    settings = get_settings()
    stored = await FeishuConfigRepository().get_active(db)

    if stored is not None:
        app_id = stored.app_id.strip()
        app_secret = decrypt_secret(stored.encrypted_app_secret)
    else:
        app_id = settings.FEISHU_APP_ID.strip()
        app_secret = settings.FEISHU_APP_SECRET

    if not app_id or not app_secret:
        return None
    return FeishuAppCredentials(app_id=app_id, app_secret=app_secret)
