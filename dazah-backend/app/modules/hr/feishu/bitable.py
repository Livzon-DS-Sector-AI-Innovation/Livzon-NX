"""Feishu Bitable (多维表格) CRUD operations."""

import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from app.core.config import get_settings
from app.modules.hr.feishu.client import FeishuClient

_settings = get_settings()
logger = logging.getLogger(__name__)


def _to_ms_timestamp(value: date | datetime | str | None) -> int | str:
    """Convert date/datetime to Feishu Bitable millisecond timestamp (UTC)."""
    if value is None:
        return ""
    if isinstance(value, str):
        text_value = value
        # Try multiple date formats
        for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]:
            try:
                value = datetime.strptime(text_value, fmt).date()
                break
            except ValueError:
                continue
        else:
            # If it's a numeric string (timestamp), convert to int
            try:
                return int(text_value)
            except (ValueError, TypeError):
                return text_value
    if isinstance(value, (date, datetime)):
        if isinstance(value, date) and not isinstance(value, datetime):
            dt = datetime(value.year, value.month, value.day, tzinfo=UTC)
        else:
            dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    return str(value)


class BitableClient:
    def __init__(
        self,
        app_token: str | None = None,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self.client = FeishuClient(app_id=app_id, app_secret=app_secret)
        self.app_token = app_token or _settings.FEISHU_BITABLE_APP_TOKEN

    def _path(self, table_id: str, suffix: str = "") -> str:
        base = f"/bitable/v1/apps/{self.app_token}/tables/{table_id}"
        return f"{base}{suffix}"

    async def create_record(
        self, table_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a single record."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        data = await self.client.request(
            "POST",
            self._path(table_id, "/records"),
            json={"fields": fields},
        )
        record = data.get("record", {})
        return cast(dict[str, Any], record if isinstance(record, dict) else {})

    async def update_record(
        self, table_id: str, record_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a single record."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        data = await self.client.request(
            "PUT",
            self._path(table_id, f"/records/{record_id}"),
            json={"fields": fields},
        )
        record = data.get("record", {})
        return cast(dict[str, Any], record if isinstance(record, dict) else {})

    async def delete_record(self, table_id: str, record_id: str) -> None:
        """Delete a single record."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        await self.client.request(
            "DELETE",
            self._path(table_id, f"/records/{record_id}"),
        )

    async def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Upload a file to Feishu Drive via the underlying client."""
        return await self.client.upload_file(file_bytes, filename, **kwargs)

    async def upload_attachment(
        self, file_name: str, file_bytes: bytes, *, content_type: str | None = None
    ) -> str | None:
        """上传文件到多维表格，返回 file_token（写入附件字段用）。

        附件字段写入格式：[{"file_token": "<token>"}]。
        飞书附件上限 20MB，超限返回 None 并记日志。
        """
        if not self.app_token:
            raise RuntimeError("Bitable app_token not configured")

        max_size = 20 * 1024 * 1024
        if len(file_bytes) > max_size:
            logger.warning(
                "附件超过飞书 20MB 上限，跳过上传",
                extra={"component": "hr", "file": file_name, "size": len(file_bytes)},
            )
            return None

        data = await self.client.upload_file(
            file_bytes,
            file_name,
            parent_type="bitable_file",
            parent_node=self.app_token,
        )
        raw_file_token = data.get("file_token", "")
        file_token = str(raw_file_token) if raw_file_token else ""
        if not file_token:
            logger.warning(
                "飞书附件上传未返回 file_token",
                extra={"component": "hr", "file": file_name},
            )
            return None
        return file_token

    async def search_records(
        self,
        table_id: str,
        *,
        filter_str: str | None = None,
        filter_obj: dict[str, Any] | None = None,
        page_size: int = 500,
    ) -> list[dict[str, Any]]:
        """Search records with optional filter. Handles pagination automatically.

        Args:
            filter_str: 旧版字符串 filter（已废弃，飞书新版API不支持）
            filter_obj: 新版对象 filter {conjunction, conditions}

        Note:
            无过滤条件时改用 GET /records 列表接口全量拉取——飞书
            records/search 接口在无 filter 时最多只返回 500 条，
            has_more/page_token 会无限循环返回同一批数据（实测验证），
            无法通过翻页拿到 500 条之后的记录。
        """
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        if not filter_obj and not filter_str:
            # 全量拉取：走 list 接口（翻页正常，无 500 条上限）
            return await self.list_all_records(table_id, page_size=page_size)
        all_items: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_record_ids: set[str] = set()
        body: dict[str, Any] = {}
        if filter_obj:
            body["filter"] = filter_obj
        elif filter_str:
            body["filter"] = filter_str
        while True:
            body["page_size"] = min(page_size, 500)
            if page_token:
                body["page_token"] = page_token
            data = await self.client.request(
                "POST",
                self._path(table_id, "/records/search"),
                json=body,
            )
            # 飞书空表时 items 可能为 null，需防御
            items = data.get("items") or []
            new_items = [r for r in items if r.get("record_id") not in seen_record_ids]
            for r in new_items:
                seen_record_ids.add(r.get("record_id"))
            all_items.extend(new_items)
            has_more = data.get("has_more", False)
            page_token = data.get("page_token", None)
            if not has_more or not page_token:
                break
            if not new_items:
                break
        return all_items

    async def list_all_records(
        self,
        table_id: str,
        *,
        page_size: int = 500,
        field_names: list[str] | None = None,
        automatic_fields: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List all records via GET /records with pagination.

        全量拉取必须走列表接口：飞书 records/search 在无过滤条件时
        只返回前 500 条且翻页循环（page_token 恒为 pageToken:500），
        而 GET /records 的 page_token 翻页正常（实测 1021 条分 3 页取全）。
        """
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        all_items: list[dict[str, Any]] = []
        page_token: str | None = None
        seen_record_ids: set[str] = set()
        while True:
            params: dict[str, Any] = {"page_size": min(page_size, 500)}
            if page_token:
                params["page_token"] = page_token
            if field_names:
                params["field_names"] = field_names
            if automatic_fields is not None:
                params["automatic_fields"] = automatic_fields
            data = await self.client.request(
                "GET",
                self._path(table_id, "/records"),
                params=params,
            )
            # 飞书空表时 items 可能为 null，需防御
            items = data.get("items") or []
            new_items = [r for r in items if r.get("record_id") not in seen_record_ids]
            for r in new_items:
                seen_record_ids.add(r.get("record_id"))
            all_items.extend(new_items)
            has_more = data.get("has_more", False)
            page_token = data.get("page_token", None)
            if not has_more or not page_token:
                break
            if not new_items:
                break
        return all_items


class FeishuBitableSync:
    """Sync HR data to Feishu Bitable."""

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self.bitable = BitableClient(app_id=app_id, app_secret=app_secret)
        self.employee_table = _settings.FEISHU_BITABLE_EMPLOYEE_TABLE_ID
        self.department_table = _settings.FEISHU_BITABLE_DEPARTMENT_TABLE_ID

    def _is_enabled(self) -> bool:
        return bool(self.bitable.app_token)

    # ─── Department ───

    async def sync_department_created(self, dept: dict[str, Any]) -> None:
        if not self._is_enabled() or not self.department_table:
            return
        fields = {
            "部门名称": dept.get("name"),
            "部门编码": dept.get("code"),
            "描述": dept.get("description") or "",
        }
        try:
            record = await self.bitable.create_record(self.department_table, fields)
            logger.info(
                "Department synced to Feishu: %s, record_id=%s",
                dept.get("name"),
                record.get("record_id"),
            )
        except Exception as e:
            logger.error("Failed to sync department to Feishu: %s", e)
            raise

    async def sync_department_updated(self, dept: dict[str, Any]) -> None:
        if not self._is_enabled() or not self.department_table:
            return
        record_id = dept.get("_feishu_record_id") or await self._find_department_record(
            dept.get("code")
        )
        if not record_id:
            return
        fields = {
            "部门名称": dept.get("name"),
            "部门编码": dept.get("code"),
            "描述": dept.get("description") or "",
        }
        try:
            await self.bitable.update_record(self.department_table, record_id, fields)
            logger.info("Department updated in Feishu: %s", dept.get("name"))
        except Exception as e:
            logger.error("Failed to update department in Feishu: %s", e)
            raise

    async def sync_department_deleted(self, code: str) -> None:
        if not self._is_enabled() or not self.department_table:
            return
        record_id = await self._find_department_record(code)
        if record_id:
            try:
                await self.bitable.delete_record(self.department_table, record_id)
                logger.info("Department deleted from Feishu: %s", code)
            except Exception as e:
                logger.error("Failed to delete department from Feishu: %s", e)
                raise

    async def _find_department_record(self, code: str | None) -> str | None:
        if not code:
            return None
        items = await self.bitable.search_records(
            self.department_table,
            filter_str=f'CurrentValue.[部门编码] = "{code}"',
        )
        return items[0].get("record_id") if items else None

    # ─── Employee ───

    async def sync_employee_deleted(self, employee_number: str) -> None:
        if not self._is_enabled() or not self.employee_table:
            return
        record_id = await self._find_employee_record(employee_number)
        if record_id:
            try:
                await self.bitable.delete_record(self.employee_table, record_id)
                logger.info("Employee deleted from Feishu: %s", employee_number)
            except Exception as e:
                logger.error("Failed to delete employee from Feishu: %s", e)
                raise

    async def _find_employee_record(self, employee_number: str | None) -> str | None:
        if not employee_number:
            return None
        # 新版 filter_obj（旧版 filter_str 已被飞书废弃，会返回 400）
        items = await self.bitable.search_records(
            self.employee_table,
            filter_obj={
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "工号",
                        "operator": "is",
                        "value": [employee_number],
                    }
                ],
            },
        )
        return items[0].get("record_id") if items else None
