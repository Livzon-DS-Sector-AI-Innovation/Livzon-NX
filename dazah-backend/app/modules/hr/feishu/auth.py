"""Feishu tenant access token management.

Supports reading credentials from environment variables (default) or
from the HR Feishu app settings database table (via explicit app_id/app_secret).
"""

import time
from collections.abc import Hashable

import httpx

from app.core.config import get_settings

_settings = get_settings()


class FeishuAuth:
    """Feishu tenant access token manager with per-credential caching."""

    _token_cache: dict[Hashable, tuple[str, float]] = {}

    @classmethod
    async def get_tenant_access_token(
        cls: type["FeishuAuth"],
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> str:
        """Get tenant access token.

        Args:
            app_id: Optional app_id. Falls back to env ``FEISHU_APP_ID``.
            app_secret: Optional app_secret. Falls back to env ``FEISHU_APP_SECRET``.
        """
        app_id = app_id or _settings.FEISHU_APP_ID
        app_secret = app_secret or _settings.FEISHU_APP_SECRET
        if not app_id or not app_secret:
            raise RuntimeError("Feishu app_id or app_secret not configured")

        cache_key = (app_id, app_secret)
        cached = cls._token_cache.get(cache_key)
        if cached and time.time() < cached[1] - 60:
            return cached[0]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": app_id, "app_secret": app_secret},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Feishu auth failed: {data}")

        token = str(data["tenant_access_token"])
        expire_at = time.time() + float(data.get("expire", 7200))
        cls._token_cache[cache_key] = (token, expire_at)
        return token
