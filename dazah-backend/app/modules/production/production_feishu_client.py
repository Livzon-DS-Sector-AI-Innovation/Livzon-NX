"""Production Feishu Bitable client."""

import hashlib
from typing import Any

import httpx

from app.core.redis import redis_client
from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL

TOKEN_TTL = 90 * 60

# 飞书认证失败错误码：token 失效/非法（缓存 token 被服务端作废等）
AUTH_ERROR_CODES = {99991661, 99991663, 99991668}


def _cache_key(app_id: str) -> str:
    digest = hashlib.sha256(app_id.encode()).hexdigest()[:24]
    return f"production:feishu:token:{digest}"


class ProductionFeishuClient:
    def __init__(self, app_id: str, app_secret: str, app_token: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        cache_key = _cache_key(self.app_id)
        if not force_refresh:
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

    async def _send(
        self, method: str, path: str, token: str, **kwargs: Any
    ) -> tuple[dict[str, Any], httpx.Response]:
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
        try:
            body = resp.json()
        except ValueError:
            body = {}
        return body, resp

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = await self._get_token()
        body, resp = await self._send(method, path, token, **kwargs)
        # 缓存 token 可能被服务端提前作废（应用更新/密钥轮换等）：
        # 认证失败时清缓存强制刷新，重试一次；非认证类 4xx 不重试
        auth_failed = resp.status_code in (400, 401) or (
            isinstance(body, dict) and body.get("code") in AUTH_ERROR_CODES
        )
        if auth_failed:
            token = await self._get_token(force_refresh=True)
            body, resp = await self._send(method, path, token, **kwargs)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(body.get("msg", str(body)))
        return body.get("data") or {}

    async def list_tables(self, page_size: int = 100) -> list[dict[str, Any]]:
        """列出多维表格中的数据表（按界面顺序，第一个即默认同步目标）。"""
        data = await self._request(
            "GET",
            f"/bitable/v1/apps/{self.app_token}/tables",
            params={"page_size": page_size},
        )
        return [
            {
                "table_id": item.get("table_id"),
                "name": item.get("name"),
            }
            for item in (data.get("items") or [])
        ]

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
