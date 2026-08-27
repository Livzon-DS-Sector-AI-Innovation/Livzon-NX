"""Feishu HTTP client with auth and retry."""

import asyncio
import logging
from typing import Any, cast

import httpx

from app.modules.hr.feishu.auth import FeishuAuth

logger = logging.getLogger(__name__)


class FeishuClient:
    system_name = "feishu"
    base_url = "https://open.feishu.cn/open-apis"

    def __init__(
        self, *, app_id: str | None = None, app_secret: str | None = None
    ) -> None:
        self._client: httpx.AsyncClient | None = None
        self._app_id = app_id
        self._app_secret = app_secret

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                timeout=httpx.Timeout(15.0, connect=5.0),
            )
        return self._client

    async def _request_with_retry(
        self, method: str, url: str, *, retries: int = 3, **kwargs: Any
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                client = await self._get_client()
                resp = await client.request(method, url, **kwargs)
                return resp
            except httpx.TransportError as e:
                last_error = e
                if attempt < retries - 1:
                    logger.warning(
                        "Feishu client retry %d/%d: %s", attempt + 1, retries, e
                    )
                    await asyncio.sleep(2**attempt)
        raise last_error or RuntimeError("飞书请求失败")

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        *,
        parent_type: str = "bitable_file",
        parent_node: str | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Upload a file to Feishu Drive and return file metadata.

        Args:
            file_bytes: Raw file bytes.
            filename: Original file name.
            parent_type: Feishu parent type, e.g. "bitable_file".
            parent_node: Parent node ID, e.g. Bitable app_token.
            timeout: Upload timeout in seconds.

        Returns:
            Dict with keys like file_token, name, size, type.
        """
        import io

        token = await FeishuAuth.get_tenant_access_token(
            app_id=self._app_id, app_secret=self._app_secret
        )
        headers = {"Authorization": f"Bearer {token}"}

        files = {"file": (filename, io.BytesIO(file_bytes))}
        data: dict[str, str] = {
            "file_name": filename,
            "size": str(len(file_bytes)),
        }
        if parent_type:
            data["parent_type"] = parent_type
        if parent_node:
            data["parent_node"] = parent_node

        client = await self._get_client()
        resp = await client.post(
            "/drive/v1/medias/upload_all",
            headers=headers,
            files=files,
            data=data,
            timeout=timeout,
        )
        try:
            resp.raise_for_status()
        except Exception:
            error_body = ""
            try:
                error_body = resp.text
            except Exception as e:
                logger.warning("Failed to read Feishu error body: %s", e)
            logger.error(
                (
                    "Feishu upload_file failed: status=%s, bo"
                    "dy=%s, parent_type=%s, parent_node=%s"
                ),
                resp.status_code,
                error_body,
                parent_type,
                parent_node,
            )
            raise
        result = resp.json()
        if result.get("code") != 0:
            raise RuntimeError(
                "Feishu upload error: "
                f"code={result.get('code')}, msg={result.get('msg')}"
            )
        data = result.get("data", {})
        return cast(dict[str, Any], data if isinstance(data, dict) else {})

    async def download_file(self, file_token: str) -> bytes:
        """Download a file from Feishu Drive by file_token.

        Returns raw file bytes.
        """
        token = await FeishuAuth.get_tenant_access_token(
            app_id=self._app_id, app_secret=self._app_secret
        )
        headers = {"Authorization": f"Bearer {token}"}
        client = await self._get_client()
        resp = await client.get(
            f"/drive/v1/medias/{file_token}/download",
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content

    async def health_check(self) -> dict[str, Any]:
        try:
            await FeishuAuth.get_tenant_access_token(
                app_id=self._app_id, app_secret=self._app_secret
            )
            return {"status": "ok"}
        except Exception as e:
            logger.warning("Feishu health check failed: %s", e)
            return {"status": "error"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        token = await FeishuAuth.get_tenant_access_token(
            app_id=self._app_id, app_secret=self._app_secret
        )
        default_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if headers:
            default_headers.update(headers)

        client = await self._get_client()
        resp = await client.request(
            method,
            path,
            headers=default_headers,
            json=json,
            params=params,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"Feishu API error: code={data.get('code')}, msg={data.get('msg')}, "
                f"path={path}"
            )
        payload = data.get("data", {})
        return cast(dict[str, Any], payload if isinstance(payload, dict) else {})
