"""Feishu Bitable (多维表格) CRUD operations."""

import logging
from datetime import UTC, date, datetime
from typing import Any, TypedDict

from app.core.config import get_settings
from app.platform.integrations.feishu.client import FeishuClient

_settings = get_settings()
logger = logging.getLogger(__name__)


class BitableRecordPage(TypedDict):
    items: list[dict[str, Any]]
    has_more: bool
    page_token: str | None
    total: int | None


def _to_ms_timestamp(value: date | datetime | str | None) -> int | str:
    """Convert date/datetime to Feishu Bitable millisecond timestamp (UTC)."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return value
    if isinstance(value, (date, datetime)):
        if isinstance(value, date) and not isinstance(value, datetime):
            dt = datetime(value.year, value.month, value.day, tzinfo=UTC)
        else:
            dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    return value


class BitableClient:
    def __init__(
        self,
        app_token: str | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
    ) -> None:
        self.client = FeishuClient(app_id=app_id, app_secret=app_secret)
        self.app_token = app_token or _settings.FEISHU_BITABLE_APP_TOKEN

    def _path(self, table_id: str, suffix: str = "") -> str:
        base = f"/bitable/v1/apps/{self.app_token}/tables/{table_id}"
        return f"{base}{suffix}"

    async def list_tables(self, page_size: int = 100) -> list[dict]:
        """List tables in the configured Bitable app."""
        if not self.app_token:
            raise RuntimeError("Bitable app_token not configured")
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict[str, object] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = await self.client.request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables",
                params=params,
            )
            items.extend(
                item for item in data.get("items", []) if isinstance(item, dict)
            )
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items

    async def create_record(self, table_id: str, fields: dict) -> dict:
        """Create a single record."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        data = await self.client.request(
            "POST",
            self._path(table_id, "/records"),
            json={"fields": fields},
        )
        return data.get("record", {})

    async def update_record(
        self, table_id: str, record_id: str, fields: dict
    ) -> dict:
        """Update a single record."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        data = await self.client.request(
            "PUT",
            self._path(table_id, f"/records/{record_id}"),
            json={"fields": fields},
        )
        return data.get("record", {})

    async def delete_record(self, table_id: str, record_id: str) -> None:
        """Delete a single record."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        await self.client.request(
            "DELETE",
            self._path(table_id, f"/records/{record_id}"),
        )

    async def list_fields(self, table_id: str, page_size: int = 500) -> list[dict]:
        """List fields for a table."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict[str, object] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = await self.client.request(
                "GET",
                self._path(table_id, "/fields"),
                params=params,
            )
            items.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items

    async def search_records(
        self,
        table_id: str,
        *,
        filter_str: str | None = None,
        filter_info: dict[str, object] | None = None,
        view_id: str | None = None,
        field_names: list[str] | None = None,
        page_size: int = 500,
        page_token: str | None = None,
        automatic_fields: bool = False,
    ) -> list[dict[str, Any]]:
        """Search records with optional filter."""
        page = await self.search_records_page(
            table_id,
            filter_str=filter_str,
            filter_info=filter_info,
            view_id=view_id,
            field_names=field_names,
            page_size=page_size,
            page_token=page_token,
            automatic_fields=automatic_fields,
        )
        return page["items"]

    async def search_records_page(
        self,
        table_id: str,
        *,
        filter_str: str | None = None,
        filter_info: dict[str, object] | None = None,
        view_id: str | None = None,
        field_names: list[str] | None = None,
        page_size: int = 500,
        page_token: str | None = None,
        automatic_fields: bool = False,
    ) -> BitableRecordPage:
        """Search one record page and preserve Feishu pagination metadata."""
        if not self.app_token or not table_id:
            raise RuntimeError("Bitable app_token or table_id not configured")
        if filter_str is not None and filter_info is not None:
            raise ValueError("filter_str and filter_info are mutually exclusive")
        if filter_str is not None:
            # Formula filters are supported by the legacy list-records API.
            # The modern POST /records/search API requires filter_info below.
            params: dict[str, object] = {
                "page_size": page_size,
                "filter": filter_str,
            }
            if view_id:
                params["view_id"] = view_id
            if page_token:
                params["page_token"] = page_token
            data = await self.client.request(
                "GET",
                self._path(table_id, "/records"),
                params=params,
            )
        else:
            payload: dict[str, object] = {}
            if automatic_fields:
                payload["automatic_fields"] = True
            if filter_info is not None:
                payload["filter"] = filter_info
            if view_id:
                payload["view_id"] = view_id
            if field_names:
                payload["field_names"] = field_names
            params = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = await self.client.request(
                "POST",
                self._path(table_id, "/records/search"),
                json=payload,
                params=params,
            )
        raw_items = data.get("items") or []
        items = raw_items if isinstance(raw_items, list) else []
        raw_page_token = data.get("page_token")
        raw_total = data.get("total")
        return {
            "items": [item for item in items if isinstance(item, dict)],
            "has_more": bool(data.get("has_more")),
            "page_token": (
                str(raw_page_token) if raw_page_token is not None else None
            ),
            "total": int(raw_total) if isinstance(raw_total, (int, float)) else None,
        }


class FeishuBitableSync:
    """Sync HR data to Feishu Bitable."""

    def __init__(self) -> None:
        self.bitable = BitableClient()
        self.employee_table = _settings.FEISHU_BITABLE_EMPLOYEE_TABLE_ID
        self.department_table = _settings.FEISHU_BITABLE_DEPARTMENT_TABLE_ID
        self.offboarding_table = _settings.FEISHU_BITABLE_OFFBOARDING_TABLE_ID
        self.approval_table = _settings.FEISHU_BITABLE_APPROVAL_TABLE_ID

    def _is_enabled(self) -> bool:
        return bool(self.bitable.app_token)

    # ─── Department ───

    async def sync_department_created(self, dept: dict) -> None:
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

    async def sync_department_updated(self, dept: dict) -> None:
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

    def _build_employee_fields(self, emp: dict) -> dict:
        fields: dict = {
            "工号": emp.get("employee_number"),
            "姓名": emp.get("name"),
            "部门": emp.get("department") or "",
            "职位": emp.get("position") or "",
            "邮箱": emp.get("email") or "",
            "状态": emp.get("status") or "在职",
            "身份证号": emp.get("id_card") or "",
            "学历": emp.get("education") or "",
            "紧急联系人": emp.get("emergency_contact_name") or "",
        }
        phone = emp.get("phone")
        if phone:
            fields["电话"] = phone
        emergency_phone = emp.get("emergency_contact_phone")
        if emergency_phone:
            fields["紧急联系人电话"] = emergency_phone
        hire_date = _to_ms_timestamp(emp.get("hire_date"))
        if hire_date != "":
            fields["入职日期"] = hire_date
        contract_start = _to_ms_timestamp(emp.get("contract_start_date"))
        if contract_start != "":
            fields["合同开始日期"] = contract_start
        contract_end = _to_ms_timestamp(emp.get("contract_end_date"))
        if contract_end != "":
            fields["合同结束日期"] = contract_end
        return fields

    async def sync_employee_created(self, emp: dict) -> None:
        if not self._is_enabled() or not self.employee_table:
            return
        fields = self._build_employee_fields(emp)
        try:
            record = await self.bitable.create_record(self.employee_table, fields)
            logger.info(
                "Employee synced to Feishu: %s, record_id=%s",
                emp.get("name"),
                record.get("record_id"),
            )
        except Exception as e:
            logger.error("Failed to sync employee to Feishu: %s", e)
            raise

    async def sync_employee_updated(self, emp: dict) -> None:
        if not self._is_enabled() or not self.employee_table:
            return
        record_id = emp.get("_feishu_record_id") or await self._find_employee_record(
            emp.get("employee_number")
        )
        if not record_id:
            return
        fields = self._build_employee_fields(emp)
        try:
            await self.bitable.update_record(self.employee_table, record_id, fields)
            logger.info("Employee updated in Feishu: %s", emp.get("name"))
        except Exception as e:
            logger.error("Failed to update employee in Feishu: %s", e)
            raise

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
        items = await self.bitable.search_records(
            self.employee_table,
            filter_str=f'CurrentValue.[工号] = "{employee_number}"',
        )
        return items[0].get("record_id") if items else None

    # ─── Offboarding ───

    async def sync_offboarding_created(self, record: dict) -> None:
        if not self._is_enabled() or not self.offboarding_table:
            return
        employee = record.get("employee") or {}
        fields = {
            "员工姓名": employee.get("name") or "",
            "工号": employee.get("employee_number") or "",
            "离职日期": _to_ms_timestamp(record.get("offboarding_date")),
            "离职类型": record.get("offboarding_type") or "",
            "离职原因": record.get("reason") or "",
            "交接状态": record.get("handover_status") or "",
            "备注": record.get("notes") or "",
        }
        try:
            rec = await self.bitable.create_record(self.offboarding_table, fields)
            logger.info(
                "Offboarding synced to Feishu: %s, record_id=%s",
                employee.get("name"),
                rec.get("record_id"),
            )
        except Exception as e:
            logger.error("Failed to sync offboarding to Feishu: %s", e)
            raise

    async def sync_offboarding_updated(self, record: dict) -> None:
        if not self._is_enabled() or not self.offboarding_table:
            return
        record_id = record.get("_feishu_record_id")
        if not record_id:
            return
        employee = record.get("employee") or {}
        fields = {
            "员工姓名": employee.get("name") or "",
            "工号": employee.get("employee_number") or "",
            "离职日期": _to_ms_timestamp(record.get("offboarding_date")),
            "离职类型": record.get("offboarding_type") or "",
            "离职原因": record.get("reason") or "",
            "交接状态": record.get("handover_status") or "",
            "备注": record.get("notes") or "",
        }
        try:
            await self.bitable.update_record(self.offboarding_table, record_id, fields)
            logger.info("Offboarding updated in Feishu: %s", employee.get("name"))
        except Exception as e:
            logger.error("Failed to update offboarding in Feishu: %s", e)
            raise

    # ─── Approval ───

    async def sync_approval_created(self, emp: dict) -> None:
        if not self._is_enabled() or not self.approval_table:
            return
        fields = {
            "文本": f"{emp.get('name')} ({emp.get('employee_number')})",
            "审批情况": "未完成",
        }
        try:
            record = await self.bitable.create_record(self.approval_table, fields)
            logger.info(
                "Approval record synced to Feishu: %s, record_id=%s",
                emp.get("name"),
                record.get("record_id"),
            )
        except Exception as e:
            logger.error("Failed to sync approval record to Feishu: %s", e)
            raise

    async def check_approval_status(self, employee_number: str) -> str | None:
        if not self._is_enabled() or not self.approval_table:
            return None
        items = await self.bitable.search_records(
            self.approval_table,
            filter_str=f'CurrentValue.[文本].contains("{employee_number}")',
        )
        if not items:
            return None
        # 取最新的一条
        latest = max(items, key=lambda x: x.get("created_time", ""))
        return latest.get("fields", {}).get("审批情况")
