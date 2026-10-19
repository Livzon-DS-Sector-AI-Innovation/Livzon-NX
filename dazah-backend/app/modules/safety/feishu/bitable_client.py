"""安全模块专属 Bitable（多维表格）API 客户端。

使用安全模块独立飞书应用凭证，不依赖 lark_oapi SDK。
提供记录 CRUD、附件下载等基础操作。
"""

import logging
from typing import Any

import httpx

from app.modules.safety.feishu.client import get_safety_tenant_token
from app.modules.safety.feishu.runtime_config import load_safety_feishu_runtime_config

logger = logging.getLogger(__name__)

BITABLE_BASE = "https://open.feishu.cn/open-apis/bitable/v1"
DRIVE_UPLOAD_URL = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"


class SafetyBitableClient:
    """安全模块多维表格 API 客户端。

    默认绑定（隐患多维表格 app_token / table_id）来自数据库配置；
    使用 `await SafetyBitableClient.create()` 构造，或显式传入覆盖值。
    """

    def __init__(
        self,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> None:
        self.app_token = app_token or ""
        self.table_id = table_id or ""

    @classmethod
    async def create(
        cls,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> "SafetyBitableClient":
        """以数据库配置为默认值构造客户端（显式参数优先）。"""
        config = await load_safety_feishu_runtime_config()
        resolved_app_token = app_token or (config.bitable_app_token if config else "")
        resolved_table_id = table_id or (
            config.bitable_hazard_table_id if config else ""
        )
        client = cls(
            app_token=resolved_app_token or None,
            table_id=resolved_table_id or None,
        )
        if not client.app_token or not client.table_id:
            logger.warning(
                "安全模块飞书 Bitable 绑定不完整 (app_token=%s, table_id=%s)",
                bool(client.app_token),
                bool(client.table_id),
            )
        return client

    def _record_url(self, table_id: str | None = None, record_id: str = "") -> str:
        tid = table_id or self.table_id
        base = f"{BITABLE_BASE}/apps/{self.app_token}/tables/{tid}/records"
        return f"{base}/{record_id}" if record_id else base

    async def _token(self) -> str:
        return await get_safety_tenant_token()

    async def get_record(
        self,
        record_id: str,
        table_id: str | None = None,
        *,
        field_name_type: str = "name",
    ) -> dict[str, Any]:
        """获取单条记录。返回 fields dict。

        默认 field_name_type="name" 确保返回中文 field_name 作为 key，
        以兼容后续代码中的 _map_bitable_fields / _download_and_save_attachments。
        """
        token = await self._token()
        url = self._record_url(table_id, record_id)
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={"field_name_type": field_name_type},
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(
                    "Bitable get_record 失败: code=%s msg=%s record_id=%s",
                    data.get("code"),
                    data.get("msg"),
                    record_id,
                )
                return {}
            fields = data.get("data", {}).get("record", {}).get("fields", {})
            logger.debug(
                "Bitable get_record 成功: record_id=%s fields=%d keys=%s",
                record_id,
                len(fields),
                list(fields.keys())[:10],
            )
            return fields if isinstance(fields, dict) else {}

    async def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
        table_id: str | None = None,
    ) -> bool:
        """更新单条记录的字段。返回是否成功。"""
        ok, _ = await self.update_record_with_result(record_id, fields, table_id)
        return ok

    async def update_record_with_result(
        self,
        record_id: str,
        fields: dict[str, Any],
        table_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """更新单条记录，返回 ``(是否成功, 飞书错误信息)``。

        页面回写需要把失败原因透出给用户（权限不足、选项非法等），
        因此与 ``update_record`` 并存，后者保持既有调用方的布尔语义。
        """
        if not fields:
            return True, None
        token = await self._token()
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.put(
                self._record_url(table_id, record_id),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={"fields": fields},
            )
            data = resp.json()
            if data.get("code") != 0:
                message = str(data.get("msg") or "飞书返回未知错误")
                logger.error(
                    "Bitable update_record 失败: record_id=%s code=%s msg=%s",
                    record_id,
                    data.get("code"),
                    message,
                )
                return False, message
            logger.info(
                "Bitable update_record 成功: record_id=%s fields=%s",
                record_id,
                list(fields.keys()),
            )
            return True, None

    async def create_record(
        self,
        fields: dict[str, Any],
        table_id: str | None = None,
    ) -> str | None:
        """新增一条记录，成功返回 record_id，失败返回 None。"""
        record_id, _ = await self.create_record_with_result(fields, table_id)
        return record_id

    async def create_record_with_result(
        self,
        fields: dict[str, Any],
        table_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        """新增一条记录，返回 ``(record_id, 飞书错误信息)``。

        页面新建需要把失败原因透出给用户（必填缺失、选项非法等），
        因此与 ``create_record`` 并存，后者保持既有调用方的布尔语义。
        """
        if not fields:
            return None, "没有需要写入的字段"
        token = await self._token()
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                self._record_url(table_id),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={"fields": fields},
            )
            data = resp.json()
            if data.get("code") != 0:
                message = str(data.get("msg") or "飞书返回未知错误")
                logger.error(
                    "Bitable create_record 失败: code=%s msg=%s fields=%s",
                    data.get("code"),
                    message,
                    list(fields.keys()),
                )
                return None, message
            record_id = (data.get("data") or {}).get("record", {}).get("record_id")
            logger.info(
                "Bitable create_record 成功: record_id=%s fields=%s",
                record_id,
                list(fields.keys()),
            )
            return (str(record_id) if record_id else None), (
                None if record_id else "飞书未返回 record_id"
            )

    async def upload_media(
        self,
        file_bytes: bytes,
        file_name: str,
        parent_type: str = "bitable_file",
    ) -> str | None:
        """上传附件到多维表格，成功返回 file_token，失败返回 None。"""
        if not file_bytes:
            return None
        token = await self._token()
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(
                DRIVE_UPLOAD_URL,
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "file_name": file_name,
                    "parent_type": parent_type,
                    "size": str(len(file_bytes)),
                },
                files={"file": (file_name, file_bytes)},
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(
                    "Bitable upload_media 失败: file=%s code=%s msg=%s",
                    file_name,
                    data.get("code"),
                    data.get("msg"),
                )
                return None
            file_token = (data.get("data") or {}).get("file_token")
            logger.info(
                "Bitable upload_media 成功: file=%s token=%s", file_name, file_token
            )
            return file_token

    async def delete_record(
        self,
        record_id: str,
        table_id: str | None = None,
    ) -> bool:
        """删除单条记录（用于回滚误写入的批次）。"""
        token = await self._token()
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.delete(
                self._record_url(table_id, record_id),
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(
                    "Bitable delete_record 失败: record_id=%s code=%s msg=%s",
                    record_id,
                    data.get("code"),
                    data.get("msg"),
                )
                return False
            logger.info("Bitable delete_record 成功: record_id=%s", record_id)
            return True

    async def download_attachment(
        self,
        file_token: str,
        extra: str | None = None,
    ) -> bytes | None:
        """下载附件内容。返回文件字节，失败返回 None。

        使用飞书 Drive API 下载 Bitable 附件。
        优先使用 extra（从 Bitable API 返回的 url 中提取）；若无 extra 则直接尝试。
        """
        token = await self._token()
        base_url = (
            f"https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download"
        )

        async def _try_download(url: str) -> bytes | None:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
                resp = await http.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    return resp.content
                logger.warning(
                    "Bitable 下载附件失败: url=%s... status=%s body=%s",
                    url[:100],
                    resp.status_code,
                    (resp.text or "")[:200],
                )
                return None

        # 1. 有 extra → 直接用 extra 下载
        if extra:
            result = await _try_download(f"{base_url}?extra={extra}")
            if result is not None:
                return result

        # 2. 无 extra → 直接下载
        result = await _try_download(base_url)
        if result is not None:
            return result

        logger.error("Bitable 下载附件最终失败: file_token=%s", file_token)
        return None

    async def download_attachment_from_url(self, download_url: str) -> bytes | None:
        """通过 Bitable API 返回的预签名 URL 下载附件。

        策略（依次尝试）：
        1. 带 Authorization header 请求（兼容 open.feishu.cn 域名）
        2. 不带 Authorization header 请求（兼容内部预签名 URL，auth 已内嵌在 query）
        3. 验证 Content-Type 是图片/文件，避免将 HTML 错误页误存为图片
        """
        token = await self._token()

        async def _try(headers: dict[str, str] | None = None) -> bytes | None:
            h = headers if headers is not None else {}
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
                resp = await http.get(download_url, headers=h)
                if resp.status_code != 200:
                    logger.warning(
                        "Bitable URL 下载附件失败: url=%s... status=%s body=%s",
                        download_url[:120],
                        resp.status_code,
                        (resp.text or "")[:200],
                    )
                    return None
                content = resp.content
                ct = resp.headers.get("content-type", "")
                # 验证：拒绝空内容 或 明显是 JSON/HTML 错误响应
                if not content:
                    logger.warning(
                        "Bitable URL 下载到空内容: url=%s...", download_url[:120]
                    )
                    return None
                if ct.startswith("application/json") or ct.startswith("text/html"):
                    text = content[:500].decode(errors="replace")
                    logger.warning(
                        "Bitable URL 返回非文件内容(ct=%s): url=%s... body=%s",
                        ct,
                        download_url[:120],
                        text,
                    )
                    return None
                logger.debug(
                    "Bitable URL 下载成功: size=%d ct=%s url=%s...",
                    len(content),
                    ct,
                    download_url[:120],
                )
                return content

        # 策略1: 带 Authorization header
        result = await _try({"Authorization": f"Bearer {token}"})
        if result is not None:
            return result

        # 策略2: 不带 Authorization（预签名 URL 可能不需要）
        logger.info("Bitable URL 尝试无 Auth 下载: url=%s...", download_url[:120])
        result = await _try()
        if result is not None:
            return result

        return None

    async def download_attachment_via_tmp_url(self, tmp_url: str) -> bytes | None:
        """通过 Bitable 记录返回的 ``tmp_url`` 换取临时下载地址后下载。

        ``tmp_url`` 指向 ``medias/batch_get_tmp_download_url``：携带 tenant
        token 调用后返回内嵌鉴权的内部下载地址（internal-api-drive-stream）。
        部分多维表格/应用组合下，附件 ``url`` 直接下载会 403，这是唯一可用路径。
        """
        if not tmp_url:
            return None
        token = await self._token()
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            resp = await http.get(
                tmp_url, headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code != 200:
                logger.warning(
                    "Bitable tmp_url 换取下载地址失败: status=%s body=%s",
                    resp.status_code,
                    (resp.text or "")[:200],
                )
                return None
            try:
                payload = resp.json()
            except ValueError:
                logger.warning("Bitable tmp_url 返回非 JSON 响应")
                return None
            entries = (payload.get("data") or {}).get("tmp_download_urls") or []
            download_url = next(
                (
                    entry.get("tmp_download_url")
                    for entry in entries
                    if isinstance(entry, dict) and entry.get("tmp_download_url")
                ),
                None,
            )
            if not download_url:
                logger.warning(
                    "Bitable tmp_url 响应中无下载地址: %s", str(payload)[:200]
                )
                return None
            download = await http.get(download_url)
            if download.status_code != 200:
                logger.warning(
                    "Bitable tmp_download_url 下载失败: status=%s",
                    download.status_code,
                )
                return None
            content = download.content
            content_type = download.headers.get("content-type", "")
            if (
                not content
                or content_type.startswith("application/json")
                or content_type.startswith("text/html")
            ):
                logger.warning(
                    "Bitable tmp_download_url 返回非文件内容(ct=%s)", content_type
                )
                return None
            return content

    async def search_records(
        self,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
        page_size: int = 100,
        max_pages: int = 50,
        sort: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """搜索记录（自动翻页），返回 [{"record_id": "...", "fields": {...}}, ...]."""
        rows, _ = await self.search_records_with_result(
            table_id,
            filter_str=filter_str,
            page_size=page_size,
            max_pages=max_pages,
            sort=sort,
        )
        return rows

    async def search_records_with_result(
        self,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
        page_size: int = 100,
        max_pages: int = 50,
        sort: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """搜索记录，返回 ``(记录列表, 飞书错误信息)``。

        与 ``search_records`` 并存：既有调用方只需要列表，页面则需要区分
        「表里确实没有数据」和「读取失败」，否则会把故障显示成空表。
        ``sort`` 形如 ``[{"field_name": "作业日期", "desc": True}]``；缺省时
        飞书按默认顺序（通常为创建先后）返回，配合 max_pages 截断会丢新记录。
        """
        token = await self._token()
        tid = table_id or self.table_id
        results: list[dict[str, Any]] = []
        page_token: str | None = None
        async with httpx.AsyncClient(timeout=30) as http:
            for _ in range(max_pages):
                # page_size/page_token 是 query 参数：放进 body 会被服务端忽略，
                # 每页都返回第一页（表现为翻页内容整页重复）
                params: dict[str, Any] = {"page_size": page_size}
                if page_token:
                    params["page_token"] = page_token
                payload: dict[str, Any] = {}
                if filter_str:
                    payload["filter"] = filter_str
                if sort:
                    payload["sort"] = sort
                resp = await http.post(
                    f"{BITABLE_BASE}/apps/{self.app_token}/tables/{tid}/records/search",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    params=params,
                    json=payload,
                )
                data = resp.json()
                if data.get("code") != 0:
                    message = str(data.get("msg") or "飞书返回未知错误")
                    logger.error("Bitable search_records 失败: %s", message)
                    return results, message
                page = data.get("data", {})
                items = page.get("items", [])
                if isinstance(items, list):
                    results.extend(
                        item for item in items if isinstance(item, dict)
                    )
                page_token = page.get("page_token") or None
                if not page.get("has_more") or not page_token:
                    break
        return results, None

    async def list_fields(self, table_id: str | None = None) -> list[dict[str, Any]]:
        """列出表格的所有字段。"""
        token = await self._token()
        tid = table_id or self.table_id
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"{BITABLE_BASE}/apps/{self.app_token}/tables/{tid}/fields",
                headers={"Authorization": f"Bearer {token}"},
                params={"page_size": 50},
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error("Bitable list_fields 失败: %s", data.get("msg"))
                return []
            items = data.get("data", {}).get("items", [])
            if not isinstance(items, list):
                return []
            return [item for item in items if isinstance(item, dict)]

    async def list_tables(self, app_token: str | None = None) -> list[dict[str, Any]]:
        """列出某个多维表格（Base）下的所有数据表。

        用于配置页粘贴 Base 链接后选择子表；返回
        ``[{"table_id": ..., "name": ...}, ...]``，失败返回空列表。
        """
        target = (app_token or self.app_token or "").strip()
        if not target:
            return []
        token = await self._token()
        tables: list[dict[str, Any]] = []
        page_token: str | None = None
        async with httpx.AsyncClient(timeout=15) as http:
            for _ in range(20):
                params: dict[str, Any] = {"page_size": 100}
                if page_token:
                    params["page_token"] = page_token
                resp = await http.get(
                    f"{BITABLE_BASE}/apps/{target}/tables",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                data = resp.json()
                if data.get("code") != 0:
                    logger.error(
                        "Bitable list_tables 失败: code=%s msg=%s",
                        data.get("code"),
                        data.get("msg"),
                    )
                    return tables
                page = data.get("data", {})
                items = page.get("items", [])
                if isinstance(items, list):
                    tables.extend(item for item in items if isinstance(item, dict))
                page_token = page.get("page_token") or None
                if not page.get("has_more") or not page_token:
                    break
        return tables

    async def create_field(
        self,
        field_name: str,
        field_type: int,
        table_id: str | None = None,
        *,
        property_: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建表格字段。返回创建的字段信息 dict，失败返回 {}。"""
        token = await self._token()
        tid = table_id or self.table_id
        payload: dict[str, Any] = {
            "field_name": field_name,
            "type": field_type,
        }
        if property_ is not None:
            payload["property"] = property_
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                f"{BITABLE_BASE}/apps/{self.app_token}/tables/{tid}/fields",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(
                    "Bitable create_field 失败: field=%s code=%s msg=%s",
                    field_name,
                    data.get("code"),
                    data.get("msg"),
                )
                return {}
            field = data.get("data", {}).get("field", {})
            logger.info(
                "Bitable create_field 成功: %s (id=%s)",
                field_name,
                field.get("field_id"),
            )
            return field if isinstance(field, dict) else {}

    async def update_field(
        self,
        field_id: str,
        table_id: str | None = None,
        *,
        field_name: str | None = None,
        field_type: int | None = None,
        property_: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """更新表格字段（名称、类型、属性）。返回更新后的字段 dict，失败返回 {}。"""
        token = await self._token()
        tid = table_id or self.table_id
        payload: dict[str, Any] = {}
        if field_name is not None:
            payload["field_name"] = field_name
        if field_type is not None:
            payload["type"] = field_type
        if property_ is not None:
            payload["property"] = property_
        if not payload:
            return {}
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.put(
                f"{BITABLE_BASE}/apps/{self.app_token}/tables/{tid}/fields/{field_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json=payload,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(
                    "Bitable update_field 失败: field_id=%s code=%s msg=%s",
                    field_id,
                    data.get("code"),
                    data.get("msg"),
                )
                return {}
            field = data.get("data", {}).get("field", {})
            logger.info("Bitable update_field 成功: field_id=%s", field_id)
            return field if isinstance(field, dict) else {}
