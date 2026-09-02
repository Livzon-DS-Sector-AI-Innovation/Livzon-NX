"""Feishu HTTP client with auth and retry."""

import asyncio
import logging
from typing import Any

import httpx

from app.platform.integrations.base import IntegrationClient
from app.platform.integrations.feishu.auth import FeishuAuth

logger = logging.getLogger(__name__)

# 外部 API 容错策略（后端规范）：最多 3 次重试，指数退避 1s/2s/4s。
# 仅对可判定的瞬时故障重试：连接层错误（请求未送达，重试幂等安全）
# 与 HTTP 429/5xx；ReadTimeout 等"可能已送达"的错误不重试，
# 避免写操作重复。
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
# 飞书 GET /records 等只读接口偶发 400（服务端抖动），纳入重试；POST 写操作不重试 400
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_RETRYABLE_EXC = (httpx.ConnectError, httpx.ConnectTimeout)


def _is_retryable(method: str, status_code: int) -> bool:
    if status_code in _RETRYABLE_STATUS:
        return True
    return method == "GET" and status_code == 400


class FeishuClient(IntegrationClient):
    system_name = "feishu"
    base_url = "https://open.feishu.cn/open-apis"

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret

    async def health_check(self) -> dict[str, Any]:
        try:
            await FeishuAuth.get_tenant_access_token(self.app_id, self.app_secret)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        token = await FeishuAuth.get_tenant_access_token(self.app_id, self.app_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        data: dict[str, Any] = {}
        for attempt in range(_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(base_url=self.base_url) as client:
                    resp = await client.request(
                        method,
                        path,
                        headers=headers,
                        json=json,
                        params=params,
                        timeout=timeout if timeout is not None else 15.0,
                    )
                if _is_retryable(method, resp.status_code) and attempt < _MAX_RETRIES:
                    delay = _BACKOFF_SECONDS[attempt]
                    logger.warning(
                        "Feishu API %s %s returned %s, retry %s/%s in %.0fs",
                        method,
                        path,
                        resp.status_code,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                        extra={"mod": "feishu"},
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                data = resp.json()
            except _RETRYABLE_EXC as exc:
                if attempt >= _MAX_RETRIES:
                    raise
                delay = _BACKOFF_SECONDS[attempt]
                logger.warning(
                    "Feishu API %s %s connection error (%s), retry %s/%s in %.0fs",
                    method,
                    path,
                    exc.__class__.__name__,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                    extra={"mod": "feishu"},
                )
                await asyncio.sleep(delay)
                continue
            break

        if not isinstance(data, dict):
            raise RuntimeError(f"Feishu API response was not an object: path={path}")
        if data.get("code") != 0:
            raise RuntimeError(
                f"Feishu API error: code={data.get('code')}, msg={data.get('msg')}, "
                f"path={path}"
            )
        payload = data.get("data", {})
        return payload if isinstance(payload, dict) else {}
