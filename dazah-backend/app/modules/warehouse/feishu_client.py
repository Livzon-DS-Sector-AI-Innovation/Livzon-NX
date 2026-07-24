"""Warehouse-owned Feishu Bitable client with explicit credentials."""

import asyncio
import hashlib
import json
import random
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.core.redis import redis_client
from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL

TOKEN_TTL_SECONDS = 90 * 60


def _token_cache_key(app_id: str, app_secret: str) -> str:
    digest = hashlib.sha256(
        f"{app_id}\0{app_secret}".encode("utf-8")
    ).hexdigest()[:24]
    return f"warehouse:feishu:tenant_token:{digest}"


class WarehouseFeishuClient:
    _rate_locks: dict[str, asyncio.Lock] = {}
    _last_request_at: dict[str, float] = {}

    def __init__(self, *, app_id: str, app_secret: str, app_token: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token

    async def _wait_for_shared_rate_slot(self) -> None:
        if not hasattr(redis_client, "eval"):
            return
        key = "warehouse:feishu:qps:" + hashlib.sha256(self.app_id.encode()).hexdigest()
        member = f"{time.time_ns()}-{random.random()}"
        while True:
            wait_ms = await redis_client.eval(
                "local t=redis.call('time'); local now=t[1]*1000+math.floor(t[2]/1000); "
                "redis.call('zremrangebyscore',KEYS[1],0,now-1000); "
                "if redis.call('zcard',KEYS[1]) < tonumber(ARGV[2]) then "
                "redis.call('zadd',KEYS[1],now,ARGV[1]); redis.call('expire',KEYS[1],2); "
                "return 0 end; local first=redis.call('zrange',KEYS[1],0,0,'WITHSCORES'); "
                "return math.max(1,1000-(now-tonumber(first[2])))",
                1,
                key,
                member,
                5,
            )
            if int(wait_ms or 0) <= 0:
                return
            await asyncio.sleep(int(wait_ms) / 1000 + random.uniform(0.005, 0.025))

    async def get_tenant_access_token(self, *, force_refresh: bool = False) -> str:
        if not self.app_id or not self.app_secret:
            raise RuntimeError("App ID 或 App Secret 未配置")

        cache_key = _token_cache_key(self.app_id, self.app_secret)
        if not force_refresh:
            cached = await redis_client.get(cache_key)
            if cached:
                return str(cached)

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{OPEN_API_BASE_URL}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            resp.raise_for_status()
            body = resp.json()

        if body.get("code") != 0:
            raise RuntimeError(body.get("msg") or str(body))

        token = body.get("tenant_access_token")
        if not token:
            raise RuntimeError("tenant_access_token 响应为空")

        await redis_client.set(cache_key, token, ex=TOKEN_TTL_SECONDS)
        return str(token)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        force_token_refresh: bool = False,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        lock = self._rate_locks.setdefault(self.app_id, asyncio.Lock())
        for attempt in range(6):
            async with lock:
                wait_for = 0.2 - (time.monotonic() - self._last_request_at.get(self.app_id, 0))
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                await self._wait_for_shared_rate_slot()
                token = await self.get_tenant_access_token(
                    force_refresh=force_token_refresh or attempt > 0
                )
                try:
                    async with httpx.AsyncClient(
                        base_url=OPEN_API_BASE_URL,
                        timeout=timeout,
                    ) as client:
                        resp = await client.request(
                            method,
                            path,
                            params=params,
                            json=json_body,
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json; charset=utf-8",
                            },
                        )
                    self._last_request_at[self.app_id] = time.monotonic()
                    body = resp.json()
                    code = body.get("code")
                    message = str(body.get("msg") or "")
                    auth_failed = (
                        resp.status_code == 401
                        or code in {99991663, 99991664, 99991668}
                        or (
                            "access token" in message.lower()
                            and "invalid" in message.lower()
                        )
                    )
                    if auth_failed and attempt == 0 and not force_token_refresh:
                        continue
                    retryable = resp.status_code == 429 or resp.status_code >= 500 or code == 1254290
                    if retryable and attempt < 5:
                        retry_after = resp.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else min(2**attempt, 16)
                        await asyncio.sleep(delay + random.uniform(0, 0.3))
                        continue
                    if code != 0:
                        raise RuntimeError(
                            message or json.dumps(body, ensure_ascii=False)
                        )
                    resp.raise_for_status()
                    data = body.get("data")
                    return data if isinstance(data, dict) else {}
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt >= 5:
                        raise
                    await asyncio.sleep(min(2**attempt, 16) + random.uniform(0, 0.3))
        raise RuntimeError("飞书请求重试次数已耗尽")

    async def list_tables(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = await self.request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables",
                params=params,
            )
            items = data.get("items") or []
            tables.extend(item for item in items if isinstance(item, dict))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break
        return tables

    async def list_fields(
        self,
        table_id: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = await self.request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                params=params,
            )
            items = data.get("items") or []
            fields.extend(item for item in items if isinstance(item, dict))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break
        return fields

    async def search_records(
        self,
        table_id: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        data = await self.request(
            "POST",
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search",
            params=params,
            json_body={},
            timeout=30.0,
        )
        items = data.get("items") or []
        return {
            "items": [item for item in items if isinstance(item, dict)],
            "has_more": bool(data.get("has_more")),
            "page_token": data.get("page_token"),
            "total": data.get("total"),
        }

    async def download_media(self, file_token: str) -> tuple[bytes, str, str | None]:
        await self._wait_for_shared_rate_slot()
        token = await self.get_tenant_access_token()
        async with httpx.AsyncClient(
            base_url=OPEN_API_BASE_URL,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                f"/drive/v1/medias/{quote(file_token, safe='')}/download",
                headers={"Authorization": f"Bearer {token}"},
            )
        response.raise_for_status()
        return (
            response.content,
            response.headers.get("content-type", "application/octet-stream"),
            response.headers.get("content-disposition"),
        )

    async def subscribe_bitable(self) -> bool:
        await self.request(
            "POST",
            f"/drive/v1/files/{self.app_token}/subscribe",
            params={"file_type": "bitable"},
        )
        return True

    async def get_wiki_node(self, node_token: str) -> dict[str, Any]:
        data = await self.request(
            "GET", "/wiki/v2/spaces/get_node", params={"token": node_token}
        )
        node = data.get("node")
        if not isinstance(node, dict):
            raise RuntimeError("飞书未返回 Wiki 节点")
        return node

    async def list_wiki_children(
        self, *, space_id: str, parent_node_token: str
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "parent_node_token": parent_node_token,
                "page_size": 50,
            }
            if page_token:
                params["page_token"] = page_token
            data = await self.request(
                "GET", f"/wiki/v2/spaces/{space_id}/nodes", params=params
            )
            items.extend(item for item in data.get("items", []) if isinstance(item, dict))
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                break
        return items

    async def discover_wiki_bases(
        self, root_token: str
    ) -> list[dict[str, Any]]:
        root = await self.get_wiki_node(root_token)
        space_id = str(root.get("space_id") or "")
        if not space_id:
            raise RuntimeError("Wiki 根节点缺少 space_id")
        root_title = str(root.get("title") or root_token)
        queue: list[tuple[dict[str, Any], list[dict[str, str]]]] = [
            (root, [{"token": root_token, "title": root_title}])
        ]
        visited: set[str] = set()
        bases: list[dict[str, Any]] = []
        while queue:
            node, path = queue.pop(0)
            node_token = str(node.get("node_token") or root_token)
            if node_token in visited:
                continue
            visited.add(node_token)
            if len(visited) > 10000:
                raise RuntimeError("Wiki 节点超过安全上限 10000")
            if str(node.get("obj_type") or "") == "bitable":
                app_token = str(node.get("obj_token") or "")
                if app_token:
                    bases.append({"app_token": app_token, "path": path})
            if not node.get("has_child"):
                continue
            children = await self.list_wiki_children(
                space_id=space_id, parent_node_token=node_token
            )
            for child in children:
                child_token = str(child.get("node_token") or "")
                title = str(child.get("title") or child_token)
                queue.append((child, [*path, {"token": child_token, "title": title}]))
        return bases


def parse_feishu_root_token(value: str, source_type: str) -> str:
    text = value.strip()
    pattern = r"/wiki/([^/?#\s]+)" if source_type == "wiki" else r"/base/([^/?#\s]+)"
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    if text and "/" not in text:
        return text
    raise ValueError("无法从链接解析飞书资源 token")


def record_cache_key(
    *, app_token: str, table_id: str, page_size: int, page_token: str | None
) -> str:
    digest = hashlib.sha256(
        f"{app_token}:{table_id}:{page_size}:{page_token or ''}".encode()
    ).hexdigest()
    return f"warehouse:feishu:records:{digest}"
