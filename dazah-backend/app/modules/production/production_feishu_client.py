"""Production Feishu Bitable client."""

import hashlib
from typing import Any

import httpx

from app.core.redis import redis_client
from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL

TOKEN_TTL = 90 * 60


def _cache_key(app_id: str) -> str:
    digest = hashlib.sha256(app_id.encode()).hexdigest()[:24]
    return f"production:feishu:token:{digest}"


class ProductionFeishuClient:
    def __init__(self, app_id: str, app_secret: str, app_token: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token

    async def _get_token(self) -> str:
        cache_key = _cache_key(self.app_id)
        cached = await redis_client.get(cache_key)
        if cached:
            return str(cached)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{OPEN_API_BASE_URL}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            resp.raise_for_status()
            body = resp.json()

        if body.get("code") != 0:
            raise RuntimeError(body.get("msg", str(body)))

        token = body["tenant_access_token"]
        await redis_client.set(cache_key, token, ex=TOKEN_TTL)
        return str(token)

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = await self._get_token()
        async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=30) as client:
            resp = await client.request(
                method,
                path,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                **kwargs,
            )
            resp.raise_for_status()
            body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(body.get("msg", str(body)))
        return body.get("data") or {}

    async def list_records(
        self, table_id: str, page_size: int = 100, page_token: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page_size": page_size}
        if page_token:
            payload["page_token"] = page_token
        data = await self._request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search",
            json=payload,
        )
        return {
            "items": data.get("items") or [],
            "has_more": bool(data.get("has_more")),
            "page_token": data.get("page_token"),
            "total": data.get("total"),
        }

    async def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
            params={"page_size": 100},
        )
        return data.get("items") or []

    async def subscribe(self) -> bool:
        await self._request(
            "POST",
            f"/drive/v1/files/{self.app_token}/subscribe",
            params={"file_type": "bitable"},
        )
        return True
