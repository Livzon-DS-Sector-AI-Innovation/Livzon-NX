"""Feishu tenant access token management."""

import time

import httpx

from app.core.config import get_settings

_settings = get_settings()


class FeishuAuth:
    _token: str | None = None
    _expire_at: float = 0.0
    _token_cache: dict[tuple[str, str], tuple[str, float]] = {}

    @classmethod
    def default(cls) -> "FeishuAuth":
        """Return a compatibility instance for callers that inject auth objects."""
        return cls()

    async def get_token(self) -> str:
        """Compatibility wrapper around the shared tenant token cache."""
        return await self.get_tenant_access_token()

    @classmethod
    async def get_tenant_access_token(
        cls,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> str:
        app_id = app_id or _settings.FEISHU_APP_ID
        app_secret = app_secret or _settings.FEISHU_APP_SECRET
        if not app_id or not app_secret:
            raise RuntimeError("Feishu app_id or app_secret not configured")

        uses_default_credentials = (
            app_id == _settings.FEISHU_APP_ID
            and app_secret == _settings.FEISHU_APP_SECRET
        )
        if (
            uses_default_credentials
            and cls._token
            and time.time() < cls._expire_at - 60
        ):
            return cls._token

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

        token = data.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Feishu auth response missing tenant_access_token")
        expire = data.get("expire", 7200)
        expire_seconds = expire if isinstance(expire, (int, float)) else 7200
        expire_at = time.time() + expire_seconds
        if uses_default_credentials:
            cls._token = token
            cls._expire_at = expire_at
        cls._token_cache[cache_key] = (token, expire_at)
        return token
