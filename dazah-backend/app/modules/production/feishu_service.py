"""Compatibility helpers for the retired production Feishu service.

The production router now uses the split Feishu services from this module's
replacement implementation.  These pure mapping helpers remain available to
old callers and migration tooling; they do not create a second API or sync
path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ProductionFeishuTableItem:
    table_id: str
    name: str
    revision: int | None


@dataclass(frozen=True)
class ProductionFeishuFieldPreview:
    field_id: str
    field_name: str
    type: int | None
    property: dict[str, Any] | None


@dataclass(frozen=True)
class ProductionFeishuRecordPreview:
    record_id: str
    fields: dict[str, Any]
    created_time: int | None
    last_modified_time: int | None


class ProductionFeishuService:
    """Expose the old pure helpers while all writes use current services."""

    @staticmethod
    def _normalize_sync_value(value: Any) -> Any:
        if isinstance(value, str):
            cleaned = value.strip()
            if "," in cleaned:
                try:
                    return float(cleaned.replace(",", ""))
                except ValueError:
                    return cleaned
            return cleaned
        return value

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_feishu_value(value: Any) -> Any:
        if isinstance(value, dict):
            if "value" in value:
                return ProductionFeishuService._extract_feishu_value(value["value"])
            for text_key in ("text", "name", "en_us", "zh_cn", "link", "url"):
                if value.get(text_key) not in (None, ""):
                    return ProductionFeishuService._extract_feishu_value(
                        value[text_key]
                    )
            return {
                key: ProductionFeishuService._extract_feishu_value(item)
                for key, item in value.items()
                if key != "type"
            }
        if isinstance(value, list):
            extracted = [
                ProductionFeishuService._extract_feishu_value(item) for item in value
            ]
            return extracted[0] if len(extracted) == 1 else extracted
        return value

    @staticmethod
    def _table_from_raw(item: dict[str, Any]) -> ProductionFeishuTableItem:
        table_id = str(item.get("table_id") or "")
        return ProductionFeishuTableItem(
            table_id=table_id,
            name=str(item.get("name") or table_id),
            revision=ProductionFeishuService._safe_int(item.get("revision")),
        )

    @staticmethod
    def _field_from_raw(item: dict[str, Any]) -> ProductionFeishuFieldPreview:
        field_id = str(item.get("field_id") or item.get("id") or "")
        field_name = str(item.get("field_name") or item.get("name") or field_id)
        return ProductionFeishuFieldPreview(
            field_id=field_id,
            field_name=field_name,
            type=ProductionFeishuService._safe_int(item.get("type")),
            property=item.get("property")
            if isinstance(item.get("property"), dict)
            else None,
        )

    @staticmethod
    def _record_from_raw(item: dict[str, Any]) -> ProductionFeishuRecordPreview:
        raw_fields = item.get("fields")
        fields = raw_fields if isinstance(raw_fields, dict) else {}
        return ProductionFeishuRecordPreview(
            record_id=str(item.get("record_id") or ""),
            fields={
                key: ProductionFeishuService._extract_feishu_value(value)
                for key, value in fields.items()
            },
            created_time=ProductionFeishuService._safe_int(item.get("created_time")),
            last_modified_time=ProductionFeishuService._safe_int(
                item.get("last_modified_time")
            ),
        )

    @staticmethod
    def _feishu_response_body(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {"raw": response.text}
        return body if isinstance(body, dict) else {"raw": body}

    @staticmethod
    def _feishu_http_error_message(
        response: httpx.Response,
        body: dict[str, Any],
        prefix: str,
    ) -> str:
        detail = body.get("msg") or body.get("message") or body.get("raw") or body
        code = body.get("code")
        code_text = f"，飞书 code={code}" if code is not None else ""
        return f"{prefix}：HTTP {response.status_code}{code_text}，{detail}"

    @staticmethod
    def _feishu_business_error_message(body: dict[str, Any], prefix: str) -> str:
        code = body.get("code")
        message = body.get("msg") or body.get("message") or body
        return f"{prefix}：飞书 code={code}，{message}"

    @staticmethod
    def _append_bitable_app_token_hint(message: str) -> str:
        return (
            f"{message}。请确认填写的是多维表格链接中 /base/ 后的 App Token，"
            "并且当前飞书应用已被授权访问该多维表格。"
        )

    @staticmethod
    def _safe_sync_error(message: str, config: Any) -> str:
        safe_message = message.replace(str(config.app_id), "***")
        return safe_message.replace(str(config.bitable_app_token), "***")[:500]

    @staticmethod
    def _map_sales_plan_record(
        binding: Any, record: ProductionFeishuRecordPreview
    ) -> dict[str, str | float | None]:
        numeric_fields = {
            "last_month_delivered_uninvoiced",
            "current_year_delivered",
            "month_planned_delivery",
            "month_delivered_qty",
            "undelivered_qty",
            "month_planned_invoice",
            "invoiced_qty",
            "delivery_completion_rate",
            "last_month_end_inventory",
            "month_planned_capacity",
            "month_end_inventory",
        }
        allowed_fields = numeric_fields | {"product_name", "unit", "remarks"}
        mapped: dict[str, str | float | None] = {}
        for platform_field, feishu_field in binding.field_mapping.items():
            if platform_field not in allowed_fields:
                continue
            value = record.fields.get(feishu_field)
            if value in (None, ""):
                continue
            if platform_field in numeric_fields:
                try:
                    mapped[platform_field] = float(str(value).replace(",", ""))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"字段 {platform_field} 不是数字") from exc
            else:
                mapped[platform_field] = str(value).strip() or None
        if not mapped.get("product_name"):
            raise ValueError("缺少 product_name 映射或产品名称为空")
        return mapped
