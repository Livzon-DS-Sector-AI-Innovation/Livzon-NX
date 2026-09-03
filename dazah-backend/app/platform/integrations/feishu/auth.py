"""Feishu tenant access token management."""

import time

import httpx

from app.core.exceptions import AppException


class FeishuCredentialsRequiredError(AppException):
    """Business integrations must supply their own complete credential pair."""

    def __init__(self) -> None:
        super().__init__(503, "业务飞书应用未配置，请在所属模块配置独立应用")


class FeishuAuth:
    _token_cache: dict[tuple[str, str], tuple[str, float]] = {}

    def __init__(self, app_id: str = "", app_secret: str = "") -> None:
        self.app_id = app_id
        self.app_secret = app_secret

    @classmethod
    def default(cls) -> "FeishuAuth":
        """Return a compatibility instance for callers that inject auth objects."""
        return cls()

    async def get_token(self) -> str:
        """Compatibility wrapper around the shared tenant token cache."""
        return await self.get_tenant_access_token(self.app_id, self.app_secret)

    @classmethod
    async def get_tenant_access_token(
        cls,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> str:
        if not app_id or not app_secret:
            raise FeishuCredentialsRequiredError()

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
            raise RuntimeError(f"Feishu auth failed: code={data.get('code')}")

        token = data.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Feishu auth response missing tenant_access_token")
        expire = data.get("expire", 7200)
        expire_seconds = expire if isinstance(expire, (int, float)) else 7200
        expire_at = time.time() + expire_seconds
        cls._token_cache[cache_key] = (token, expire_at)
        return token
