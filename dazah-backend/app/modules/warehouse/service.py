"""Warehouse business workflows live here."""

import asyncio
import hashlib
import json
import logging
import re
import statistics
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.secrets import decrypt_secret, encrypt_secret
from app.modules.warehouse.feishu_client import (
    WarehouseFeishuClient,
    parse_feishu_root_token,
)
from app.modules.warehouse.feishu_fields import (
    FIELD_PERSON_TYPES,
    build_feishu_cell_value,
    format_detail_value,
    is_editable_field,
    is_readonly_field,
    is_view_only_field,
)
from app.modules.warehouse.feishu_material_pages import (
    FEISHU_WAREHOUSE_BASE_NAMES,
    FEISHU_WAREHOUSE_MATERIAL_PAGES,
    FeishuWarehouseMaterialPage,
)
from app.modules.warehouse.legacy_models import (
    WarehouseFeishuAnalysisProfile,
    WarehouseFeishuAnalysisResult,
    WarehouseFeishuAnalysisRun,
    WarehouseFeishuConfig,
    WarehouseFeishuPageBinding,
    WarehouseFeishuPromptVersion,
    WarehouseFeishuSourceRoot,
)
from app.modules.warehouse.models import (
    MaterialPageRow,
    PackagingMaterialInventory,
    ProductInventory,
    RawMaterialInventory,
)
from app.modules.warehouse.page_access import (
    assert_department_filters,
    assert_material_page,
    assert_material_refresh,
    assert_record_department,
    material_page_scope,
)
from app.modules.warehouse.repository import WarehouseRepository
from app.modules.warehouse.schemas import (
    WarehouseFeishuColumn,
    WarehouseFeishuConnectivityStep,
    WarehouseFeishuFieldResponse,
    WarehouseFeishuMaterialPageResponse,
    WarehouseFeishuRawRecordResponse,
    WarehouseRecordDetailResponse,
    WarehouseRecordFieldValue,
)
from app.platform.identity.data_scope import DepartmentScope, current_page_key
from app.platform.integrations.feishu.bitable import BitableClient
from app.platform.integrations.feishu.client import FeishuClient

logger = logging.getLogger(__name__)

WAREHOUSE_FEISHU_TABLE_SYNC_TIMEOUT_SECONDS = 300
FIELD_FILTER_OPERATORS = {"contains", "eq", "ne", "gt", "gte", "lt", "lte"}
NUMERIC_FIELD_FILTER_OPERATORS = {"gt", "gte", "lt", "lte"}
CREDENTIAL_FIELD_PATTERN = re.compile(
    r"password|secret|token|cookie|api.?key|密码|密钥|令牌", re.I
)
PERSONAL_FIELD_PATTERN = re.compile(r"身份证|手机号|手机|电话|邮箱|email|姓名", re.I)
MAX_ANALYSIS_INPUT_CHARS = 60_000


# 五金按车间/部门组织的页面（页面标题=部门名，如 hardware-101-1-workshop）：
# 页面人人可见，行级过滤——仅返回当前用户可见部门（含子部门）的数据行；
# 汇总/记录页（hardware-summary / stock-amount / electrical / inbound / outbound）
# 为厂级共享数据，无车间归属，不做行级过滤
HARDWARE_DEPT_PAGE_KEYS = {
    "hardware-101-1-workshop",
    "hardware-101-2-workshop",
    "hardware-102-workshop",
    "hardware-103-workshop",
    "hardware-201-1-workshop",
    "hardware-201-2-workshop",
    "hardware-201-3-workshop",
    "hardware-202-workshop",
    "hardware-203-workshop",
    "hardware-203-3-workshop",
    "hardware-thermal-station",
    "hardware-power-department",
    "hardware-wastewater",
    "hardware-warehouse",
    "hardware-rd-center",
    "hardware-others",
}


_DATE_SORT_DESC_FIELDS = {
    "raw-ledger": "出库日期",
    "packaging-ledger": "出库日期",
    "inbound-ledger": "入库日期",
    "hardware-inbound-ledger": "日期",
    "hardware-outbound-ledger": "日期",
    "product-inbound-ledger": "入库日期",
    "product-inbound-detail": "入库日期",
    "product-outbound-ledger": "出库日期",
    "product-shipping": "日期",
    # 五金库存明细页：按业务/入库日期倒序，保证每天最新记录在前。
    # 注意：hardware-summary / hardware-electrical 的「日期」绝大多数为同一
    # 初始化日期且最新行常因结存 0 被隐藏，无排序意义，故不配置。
    "hardware-101-1-workshop": "日期",
    "hardware-101-2-workshop": "日期",
    "hardware-102-workshop": "日期",
    "hardware-103-workshop": "日期",
    "hardware-201-1-workshop": "日期",
    "hardware-201-2-workshop": "日期",
    "hardware-201-3-workshop": "日期",
    "hardware-202-workshop": "日期",
    "hardware-203-workshop": "日期",
    "hardware-203-3-workshop": "日期",
    "hardware-thermal-station": "日期",
    "hardware-power-department": "日期",
    "hardware-wastewater": "日期",
    "hardware-warehouse": "日期",
    "hardware-rd-center": "日期",
    "hardware-others": "日期",
}

# 飞书页面数据内存缓存 TTL（秒）：页面默认实时读飞书，短缓存避免
# 多页面/多用户并发把飞书 API 打爆；点击刷新（force=1）绕过缓存。
# 大表全量拉取耗时长（raw-ledger 近 2 万条），60s 过短导致频繁全量重拉，
# 提升到 300s 与仪表盘一致；force=1 手动刷新保持实时。
PAGE_CACHE_TTL_SECONDS = 300
FIELD_META_CACHE_TTL_SECONDS = 300


def _safe_number(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def build_warehouse_import_key(*parts: str | None) -> str:
    normalized = "|".join((part or "").strip().lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_feishu_cell_value(value: object | None) -> object | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        normalized_items: list[str] = []
        for item in value:
            normalized_item = normalize_feishu_cell_value(item)
            if normalized_item is None:
                continue
            normalized_items.append(str(normalized_item))
        return ", ".join(normalized_items)
    if isinstance(value, dict):
        for key in ("text", "name", "label"):
            nested_value = value.get(key)
            if nested_value not in (None, ""):
                return str(nested_value)

        nested_value = value.get("value")
        if nested_value not in (None, ""):
            return normalize_feishu_cell_value(nested_value)

        file_token = value.get("file_token")
        if file_token not in (None, ""):
            return str(file_token)

        return str(value)
    return str(value)


def normalize_person_value(value: object | None) -> object | None:
    """人员字段保留结构化信息（id/name/avatar_url），供页面展示头像。

    飞书人员值可能是单个 dict 或多个 dict 的 list，统一归一为 list。
    """
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return normalize_feishu_cell_value(value)
    persons: list[dict[str, str | None]] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("en_name") or ""
            if not name:
                continue
            persons.append(
                {
                    "id": str(item.get("id") or ""),
                    "name": str(name),
                    "avatar_url": str(
                        item.get("avatar_url") or item.get("avatar") or ""
                    ),
                }
            )
        elif isinstance(item, str) and item.strip():
            persons.append({"id": "", "name": item.strip(), "avatar_url": ""})
    return persons if persons else None


def resolve_option_ids(
    value: object | None, option_map: dict[str, str]
) -> object | None:
    """把单元格值中的飞书选项 ID（opt 开头）替换为选项名称。

    公式/lookup 字段引用单选/多选源字段时，飞书返回的是源字段的选项 ID
    （如 optVeCZ9sV），页面必须展示选项名称（如 25kg/袋）。
    """
    if not option_map or value is None:
        return value
    if isinstance(value, str):
        return option_map.get(value, value)
    if isinstance(value, list):
        return [
            option_map.get(item, item) if isinstance(item, str) else item
            for item in value
        ]
    return value


# 公式字段中引用的目标表：bitable::$table[tblXXX]
_FORMULA_TABLE_PATTERN = re.compile(r"bitable::\$table\[(tbl[A-Za-z0-9]+)\]")


def build_material_page_row_search_text(row: dict[str, object | None]) -> str:
    return " ".join(
        str(value).strip().lower()
        for key, value in row.items()
        if key != "__record_id" and value not in (None, "")
    )


DATE_FIELD_PATTERN = re.compile(r"(日期|有效期|复验期)$")
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")

PAGE_FIELD_ALIASES: dict[str, dict[str, list[str]]] = {
    "packaging-summary": {
        "使用产品/类别": ["使用产品"],
        "物料名称": ["名称"],
        "ERP编号": ["EPR编号"],
        "前台库存": ["前台结存"],
        "安全库存（30天）": ["安全库存"],
    },
    "packaging-detail": {
        "使用产品/类别": ["使用产品"],
        "物料名称": ["名称"],
        "规格": ["规  格"],
        "生产商": ["生产商/供应商"],
        "供货商": ["生产商/供应商"],
        "出库总量": ["累计出库"],
    },
    "packaging-ledger": {
        "领料人": ["领用人"],
    },
}
FINISHED_PRODUCT_DETAIL_PAGE_KEYS = {
    "product-detail-l-phenylalanine",
    "product-detail-fumaric-acid",
    "product-detail-l-tryptophan",
    "product-detail-mevastatin",
    "product-detail-kitasamycin-hcl",
    "product-detail-doramectin",
    "product-detail-lovastatin",
    "product-detail-florfenicol-premix",
    "product-detail-demeclocycline-hcl",
    "product-detail-fenbendazole-powder",
}


def is_material_page_date_field(field_name: str) -> bool:
    return bool(DATE_FIELD_PATTERN.search(field_name))


def _parse_date_value(value: object | None) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        timestamp_value = float(value)
        if timestamp_value > 1e12:
            timestamp_value /= 1000
        try:
            return datetime.fromtimestamp(timestamp_value, tz=CHINA_TIMEZONE).date()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        if re.fullmatch(r"\d{10,13}", text):
            numeric_value = float(text)
            if numeric_value > 1e12:
                numeric_value /= 1000
            try:
                return datetime.fromtimestamp(numeric_value, tz=CHINA_TIMEZONE).date()
            except (OverflowError, OSError, ValueError):
                return None
    return None


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_number(value: object | None) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", "").strip()
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _matches_warning_status(value: object | None, warning_status: str) -> bool:
    normalized_value = _normalize_text(value)
    status = warning_status.strip().lower()
    if status in {"warning", "warn", "预警", "异常"}:
        return normalized_value not in {"", "-", "正常"}
    if status in {"normal", "正常", "无预警"}:
        return normalized_value in {"", "-", "正常"}
    return normalized_value == warning_status.strip()


def _should_hide_zero_stock_row(
    page_key: str,
    row: dict[str, object | None],
) -> bool:
    """库存明细页自动隐藏库存量 ≤ 0 的记录。

    覆盖：原辅料库存明细、包材库存明细、成品库存明细（10 张）、
    五金/电仪/各车间部门库存页；汇总表与出入库台账不隐藏。
    """
    candidates: tuple[str, ...]
    if page_key in FINISHED_PRODUCT_DETAIL_PAGE_KEYS:
        candidates = ("库存量", "库存", "库存数量")
    elif page_key in {"raw-detail", "packaging-detail"}:
        candidates = ("本日结存",)
    elif page_key.startswith("hardware-") and page_key not in {
        "hardware-inbound-ledger",
        "hardware-outbound-ledger",
    }:
        candidates = ("结存量",)
    else:
        return False

    for candidate in candidates:
        if candidate not in row:
            continue
        quantity = _parse_number(row.get(candidate))
        return quantity is None or quantity <= 0

    return True


def _aggregate_daily_trend(
    rows: list[dict[str, object | None]],
    date_field: str,
    qty_fields: tuple[str, ...],
    days: int = 30,
) -> list[dict[str, Any]]:
    """按天聚合最近 N 天的数量/金额趋势，缺失日期补 0，用于仪表盘折线图。"""
    today = datetime.now(CHINA_TIMEZONE).date()
    cutoff = today - timedelta(days=days - 1)
    daily: dict[str, float] = {}
    for row in rows:
        day = _parse_date_value(row.get(date_field))
        if day is None or day < cutoff or day > today:
            continue
        quantity: float | None = None
        for field in qty_fields:
            parsed = _parse_number(row.get(field))
            if parsed is not None and parsed > 0:
                quantity = parsed
                break
        if quantity is None:
            continue
        key = day.isoformat()
        daily[key] = daily.get(key, 0) + quantity
    result: list[dict[str, Any]] = []
    for offset in range(days):
        day = cutoff + timedelta(days=offset)
        result.append(
            {"date": day.isoformat(), "value": round(daily.get(day.isoformat(), 0), 2)}
        )
    return result


def _numeric_sort_value(row: dict[str, object | None], field_name: str) -> float:
    value = row.get(field_name)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _pick_dept_name(value: object | None) -> str:
    """从归一化后的归属库区/车间值提取部门名（可能为逗号分隔列表）。"""
    text = _normalize_text(value)
    if not text:
        return "（未标注）"
    return text.split(",")[0].strip()


# ── 模块级共享缓存（进程内跨请求复用）──────────────────────────────
# app_token -> 仓储模块自有飞书客户端（凭证变更时整体清空）
_MATERIAL_SYNC_CLIENTS: dict[str, Any] = {}
# page_key -> (fetched_at, columns, normalized_rows, option_map)
_PAGE_CACHE: dict[
    str,
    tuple[
        datetime,
        list[WarehouseFeishuColumn],
        list[dict[str, object | None]],
        dict[str, str],
    ],
] = {}
# page_key -> (fetched_at, fields meta)
_FIELD_META_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
# app_token:table_id -> (fetched_at, fields meta)（选项映射目标表）
_TABLE_FIELDS_CACHE: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}
# 仪表盘聚合结果缓存（TTL 300s，force 强制刷新）
_DASHBOARD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class WarehouseService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = WarehouseRepository(session)
        # 缓存为模块级共享（进程内跨请求复用）：
        # get_warehouse_service 每请求新建实例，实例级缓存会全部失效导致每次全量拉取
        self._page_cache = _PAGE_CACHE
        self._field_meta_cache = _FIELD_META_CACHE
        self._table_fields_cache = _TABLE_FIELDS_CACHE
        # 仪表盘聚合结果缓存：冷启动全量拉取耗时长，TTL 放宽到 300s，force 可强制刷新
        self._dashboard_cache = _DASHBOARD_CACHE

    async def _material_page_scope(
        self, page_key: str, fallback: DepartmentScope | None = None
    ) -> DepartmentScope | None:
        assert_material_page(page_key)
        if current_page_key.get() is None:
            return fallback
        return await material_page_scope(self.repo.session, page_key, fallback)

    @staticmethod
    def _scope_material_rows(
        page_key: str,
        rows: list[dict[str, object | None]],
        scope: DepartmentScope | None,
    ) -> list[dict[str, object | None]]:
        if page_key not in HARDWARE_DEPT_PAGE_KEYS or scope is None or scope.is_all:
            return rows
        return [
            row
            for row in rows
            if str(row.get("车间") or "").strip() in scope.department_names
        ]

    async def _get_feishu_client(self) -> FeishuClient:
        config = await self._get_active_feishu_config_or_raise()
        return FeishuClient(
            app_id=config.app_id,
            app_secret=decrypt_secret(config.encrypted_app_secret),
        )

    async def _get_bitable_client(self, app_token: str) -> BitableClient:
        client = await self._get_feishu_client()
        return BitableClient(
            app_token=app_token,
            app_id=client.app_id,
            app_secret=client.app_secret,
        )
    async def list_raw_materials(self) -> list[RawMaterialInventory]:
        return await self.repo.list_raw_materials()

    async def list_packaging_materials(self) -> list[PackagingMaterialInventory]:
        return await self.repo.list_packaging_materials()

    async def list_products(self) -> list[ProductInventory]:
        return await self.repo.list_products()

    async def _get_material_page_config(
        self, page_key: str
    ) -> FeishuWarehouseMaterialPage:
        """解析页面数据源配置：数据库（warehouse_page_feishu_configs）优先，硬编码映射回退。

        设置页可修改数据库配置实现更换多维表格，无需改代码；
        查询失败（表不存在等）时静默回退硬编码，保证页面可用。
        """
        try:
            db_config = await self.repo.get_page_feishu_config(page_key)
        except Exception:
            db_config = None
        if db_config and db_config.get("table_id"):
            return FeishuWarehouseMaterialPage(
                page_key=page_key,
                title=db_config.get("table_name") or page_key,
                table_id=db_config["table_id"],
                app_token=db_config["app_token"],
            )
        page_config = FEISHU_WAREHOUSE_MATERIAL_PAGES.get(page_key)
        if not page_config:
            raise HTTPException(status_code=404, detail="仓储飞书模板页不存在")
        return page_config

    async def _resolve_material_page_source(self, source: str | None) -> str:
        from app.shared.config_reader import get_module_setting

        # 默认读本地快照（秒回）；DB 运行时配置 / env 可覆盖回 feishu 实时源
        resolved = (
            (
                source
                or await get_module_setting(
                    "warehouse", "WAREHOUSE_MATERIAL_PAGE_SOURCE", "local"
                )
            )
            .strip()
            .lower()
        )
        if resolved in {"feishu", "remote"}:
            return "feishu"
        if resolved in {"local", "db", "database"}:
            return "local"
        raise HTTPException(
            status_code=400, detail="仓储页面数据源仅支持 feishu 或 local"
        )

    def _build_columns(
        self, fields_response: list[dict[str, Any]]
    ) -> list[WarehouseFeishuColumn]:
        columns: list[WarehouseFeishuColumn] = []
        for field in fields_response:
            field_name = str(field.get("field_name", "")).strip()
            if not field_name:
                continue
            field_type = field.get("type")
            columns.append(
                WarehouseFeishuColumn(
                    key=field_name,
                    title=field_name,
                    field_type=field_type,
                    readonly=is_readonly_field(field_type),
                    view_only=is_view_only_field(field_type),
                    editable=is_editable_field(field_type),
                )
            )
        return columns

    def _build_normalized_rows(
        self,
        columns: list[WarehouseFeishuColumn],
        records_response: list[dict[str, Any]],
        option_map: dict[str, str] | None = None,
    ) -> list[dict[str, object | None]]:
        normalized_rows: list[dict[str, object | None]] = []
        for record in records_response:
            field_map = record.get("fields", {})
            if not isinstance(field_map, dict):
                continue

            normalized_row = {}
            for column in columns:
                raw_value = field_map.get(column.key)
                if column.field_type in FIELD_PERSON_TYPES:
                    # 人员字段保留 id/name/avatar_url，页面渲染头像
                    normalized_row[column.key] = normalize_person_value(raw_value)
                else:
                    normalized_row[column.key] = normalize_feishu_cell_value(
                        resolve_option_ids(raw_value, option_map or {})
                    )
            normalized_row["__record_id"] = record.get("record_id")
            normalized_rows.append(normalized_row)
        return normalized_rows

    def _paginate_material_rows(
        self,
        rows: list[dict[str, object | None]],
        *,
        page: int,
        page_size: int,
        keyword: str | None,
    ) -> tuple[list[dict[str, object | None]], int]:
        keyword_text = keyword.strip().lower() if keyword and keyword.strip() else None
        filtered_rows = rows
        if keyword_text:
            filtered_rows = [
                row
                for row in rows
                if keyword_text in build_material_page_row_search_text(row)
            ]

        total = len(filtered_rows)
        start = (page - 1) * page_size
        end = start + page_size
        return filtered_rows[start:end], total

    def _extract_options_from_fields(
        self, fields_response: list[dict[str, Any]]
    ) -> dict[str, str]:
        """从字段元信息提取选项 id→name 映射。

        兼容两种飞书字段结构：
        - 旧版：选项在顶层 ``property.options``（单选/多选字段）
        - 新版（公式聚合/Lookup 等）：选项嵌套在 ``property.type.ui_property.options``
        """
        option_map: dict[str, str] = {}
        for field in fields_response:
            property_obj = field.get("property")
            if not isinstance(property_obj, dict):
                continue
            option_lists = [property_obj.get("options") or []]
            type_obj = property_obj.get("type")
            if isinstance(type_obj, dict):
                ui_property = type_obj.get("ui_property")
                if isinstance(ui_property, dict):
                    option_lists.append(ui_property.get("options") or [])
            for options in option_lists:
                for option in options:
                    if (
                        isinstance(option, dict)
                        and option.get("id")
                        and option.get("name")
                    ):
                        option_map[str(option["id"])] = str(option["name"])
        return option_map

    async def _build_page_option_map(
        self,
        page_config: FeishuWarehouseMaterialPage,
        fields_response: list[dict[str, Any]],
    ) -> dict[str, str]:
        """构建页面级选项 id→name 映射。

        除本表字段 options 外，公式/lookup 字段（type=19）引用目标表单选/多选
        字段时返回的是源选项 ID，需拉取公式中引用的目标表字段 options 一并映射。
        """
        option_map = self._extract_options_from_fields(fields_response)
        target_tables: set[str] = set()
        for field in fields_response:
            property_obj = field.get("property")
            if not isinstance(property_obj, dict):
                continue
            formula = property_obj.get("formula")
            if not isinstance(formula, str):
                continue
            for match in _FORMULA_TABLE_PATTERN.finditer(formula):
                target_tables.add(match.group(1))

        for table_id in target_tables:
            if table_id == page_config.table_id:
                continue
            try:
                target_fields = await self._fetch_table_fields_cached(
                    app_token=page_config.app_token,
                    table_id=table_id,
                )
            except Exception:
                continue
            target_map = self._extract_options_from_fields(target_fields)
            option_map.update(target_map)
        return option_map

    async def _fetch_table_fields_cached(
        self,
        *,
        app_token: str,
        table_id: str,
    ) -> list[dict[str, Any]]:
        """按 table_id 缓存目标表字段（选项映射用），5 分钟 TTL。"""
        cache_key = f"{app_token}:{table_id}"
        cached = self._table_fields_cache.get(cache_key)
        now = datetime.now(UTC)
        if cached and (now - cached[0]).total_seconds() < FIELD_META_CACHE_TTL_SECONDS:
            return cached[1]
        fields = await self.fetch_feishu_table_fields(
            app_token=app_token,
            table_id=table_id,
        )
        self._table_fields_cache[cache_key] = (now, fields)
        return fields

    def _build_material_page_response(
        self,
        *,
        page_key: str,
        page_title: str,
        table_name: str,
        columns: list[WarehouseFeishuColumn],
        rows: list[dict[str, object | None]],
        total: int,
        page: int,
        page_size: int,
        last_sync_time: datetime,
        source: str,
        base_name: str = "",
        stats: dict[str, Any] | None = None,
    ) -> WarehouseFeishuMaterialPageResponse:
        return WarehouseFeishuMaterialPageResponse(
            page_key=page_key,
            page_title=page_title,
            table_name=table_name,
            columns=columns,
            rows=rows,
            total=total,
            page=page,
            page_size=page_size,
            last_sync_time=last_sync_time,
            source=source,
            base_name=base_name,
            stats=stats or {},
        )

    def _get_base_name(self, page_key: str) -> str:
        page_config = FEISHU_WAREHOUSE_MATERIAL_PAGES.get(page_key)
        if not page_config:
            return ""
        return FEISHU_WAREHOUSE_BASE_NAMES.get(page_config.app_token, "")

    def _build_page_stats(
        self,
        page_key: str,
        rows: list[dict[str, object | None]],
    ) -> dict[str, Any]:
        """基于过滤后的全量行计算页面业务统计概览。

        统计仓储业务指标而非纯记录数：库存不足/严重不足、合格/待验/不合格
        质量分布、本月/今日记录、金额合计等；页面据此渲染可点击筛选的卡片。
        """
        stats: dict[str, Any] = {"total": len(rows)}
        now = datetime.now(CHINA_TIMEZONE)
        today = now.date()

        warning_count = 0
        low_stock_count = 0
        severe_low_stock_count = 0
        has_warning_field = False
        quality_counts: dict[str, int] = {}
        has_quality_field = False
        stock_count = 0
        amount_total = 0.0
        has_amount_field = False
        date_keys: list[str] = []
        today_count = 0
        month_count = 0

        for row in rows:
            if "预警" in row:
                has_warning_field = True
                warning = _normalize_text(row.get("预警"))
                if warning not in ("", "-", "正常"):
                    warning_count += 1
                if warning == "库存不足":
                    low_stock_count += 1
                elif warning == "库存严重不足":
                    severe_low_stock_count += 1

            if "质量状态" in row:
                has_quality_field = True
                quality = _normalize_text(row.get("质量状态"))
                if quality:
                    quality_counts[quality] = quality_counts.get(quality, 0) + 1

            for key in ("金额（元）", "金额"):
                if key in row:
                    parsed = _parse_number(row.get(key))
                    if parsed is not None:
                        amount_total += parsed
                        has_amount_field = True
                    break

            for key in ("结存量", "本日结存", "库存量", "库存", "库存数量"):
                if key in row:
                    quantity = _parse_number(row.get(key))
                    if quantity is not None and quantity > 0:
                        stock_count += 1
                    break

            if not date_keys:
                date_keys = [
                    key
                    for key in row.keys()
                    if key != "__record_id" and is_material_page_date_field(key)
                ]
            if date_keys:
                for key in date_keys:
                    day = _parse_date_value(row.get(key))
                    if day is not None:
                        if day == today:
                            today_count += 1
                        if day.year == now.year and day.month == now.month:
                            month_count += 1
                        break

        if has_warning_field:
            stats["warning_count"] = warning_count
            stats["low_stock_count"] = low_stock_count
            stats["severe_low_stock_count"] = severe_low_stock_count
        if has_quality_field:
            stats["quality_counts"] = quality_counts
            stats["qualified_count"] = quality_counts.get("合格", 0)
            stats["pending_count"] = quality_counts.get("待验", 0)
            stats["failed_count"] = quality_counts.get("不合格", 0)
        if stock_count > 0 or not rows:
            stats["stock_count"] = stock_count
        if has_amount_field:
            stats["amount_total"] = round(amount_total, 2)
        if date_keys:
            stats["today_count"] = today_count
            stats["month_count"] = month_count
        return stats

    def _invalidate_page_cache(self, page_key: str) -> None:
        self._page_cache.pop(page_key, None)
        self._field_meta_cache.pop(page_key, None)

    async def _get_page_field_meta(
        self, page_config: FeishuWarehouseMaterialPage
    ) -> list[dict[str, Any]]:
        cache_key = page_config.page_key
        cached = self._field_meta_cache.get(cache_key)
        now = datetime.now(UTC)
        if cached and (now - cached[0]).total_seconds() < FIELD_META_CACHE_TTL_SECONDS:
            return cached[1]
        fields = await self.fetch_feishu_table_fields(
            app_token=page_config.app_token,
            table_id=page_config.table_id,
        )
        self._field_meta_cache[cache_key] = (now, fields)
        return fields

    def _resolve_filter_field_candidates(
        self,
        page_key: str,
        field_name: str,
        row: dict[str, object | None],
    ) -> list[str]:
        aliases = PAGE_FIELD_ALIASES.get(page_key, {})
        candidates = aliases.get(field_name, [field_name])
        return [candidate for candidate in candidates if candidate in row]

    def _parse_advanced_filters(self, filters: str | None) -> list[dict[str, str]]:
        if not filters:
            return []
        try:
            payload = json.loads(filters)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="高级筛选参数格式错误") from exc
        if not isinstance(payload, list):
            raise HTTPException(status_code=400, detail="高级筛选参数格式错误")

        normalized_filters: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="高级筛选参数格式错误")
            field = str(item.get("field", "")).strip()
            operator = str(item.get("operator", "")).strip()
            value = str(item.get("value", "")).strip()
            value_to = str(item.get("value_to", "")).strip()
            if not field or not operator:
                raise HTTPException(
                    status_code=400, detail="高级筛选参数缺少字段或运算符"
                )
            normalized_filters.append(
                {
                    "field": field,
                    "operator": operator,
                    "value": value,
                    "value_to": value_to,
                }
            )
        return normalized_filters

    def _match_filter_operator(
        self,
        *,
        field_name: str,
        candidate_values: list[object | None],
        operator: str,
        value: str,
        value_to: str,
    ) -> bool:
        valid_operators = {
            "contains",
            "not_contains",
            "eq",
            "neq",
            "empty",
            "not_empty",
            "gt",
            "gte",
            "lt",
            "lte",
            "between",
        }
        if operator not in valid_operators:
            raise HTTPException(
                status_code=400, detail=f"不支持的筛选运算符: {operator}"
            )

        if operator == "empty":
            return any(_normalize_text(item) == "" for item in candidate_values)
        if operator == "not_empty":
            return any(_normalize_text(item) != "" for item in candidate_values)

        if is_material_page_date_field(field_name):
            compare_dates = [
                item
                for value_item in candidate_values
                if isinstance((item := _parse_date_value(value_item)), date)
            ]
            if not compare_dates:
                return False
            left_date = _parse_date_value(value)
            right_date = _parse_date_value(value_to) if value_to else None
            if value and left_date is None:
                raise HTTPException(
                    status_code=400, detail=f"日期筛选值格式错误: {value}"
                )
            if value_to and right_date is None:
                raise HTTPException(
                    status_code=400, detail=f"日期筛选值格式错误: {value_to}"
                )
            if operator == "eq":
                return any(item == left_date for item in compare_dates)
            if operator == "neq":
                return any(item != left_date for item in compare_dates)
            if left_date is None:
                return False
            if operator == "gt":
                return any(item > left_date for item in compare_dates)
            if operator == "gte":
                return any(item >= left_date for item in compare_dates)
            if operator == "lt":
                return any(item < left_date for item in compare_dates)
            if operator == "lte":
                return any(item <= left_date for item in compare_dates)
            if operator == "between":
                if left_date is None or right_date is None:
                    raise HTTPException(
                        status_code=400, detail="区间筛选必须提供开始和结束日期"
                    )
                return any(left_date <= item <= right_date for item in compare_dates)

        numeric_values = [_parse_number(item) for item in candidate_values]
        normalized_numbers = [item for item in numeric_values if item is not None]
        left_number = _parse_number(value)
        right_number = _parse_number(value_to) if value_to else None
        if (
            operator in {"gt", "gte", "lt", "lte", "between"}
            and normalized_numbers
            and left_number is not None
        ):
            if operator == "gt":
                return any(item > left_number for item in normalized_numbers)
            if operator == "gte":
                return any(item >= left_number for item in normalized_numbers)
            if operator == "lt":
                return any(item < left_number for item in normalized_numbers)
            if operator == "lte":
                return any(item <= left_number for item in normalized_numbers)
            if operator == "between":
                if left_number is None or right_number is None:
                    raise HTTPException(
                        status_code=400, detail="区间筛选必须提供开始和结束值"
                    )
                return any(
                    left_number <= item <= right_number for item in normalized_numbers
                )

        normalized_values = [_normalize_text(item) for item in candidate_values]
        compare_text = value.lower()
        if operator == "contains":
            return any(compare_text in item.lower() for item in normalized_values)
        if operator == "not_contains":
            return all(compare_text not in item.lower() for item in normalized_values)
        if operator == "eq":
            return any(item == value for item in normalized_values)
        if operator == "neq":
            return any(item != value for item in normalized_values)
        if operator == "between":
            raise HTTPException(status_code=400, detail="区间筛选仅支持数字或日期字段")
        return False

    def _filter_material_page_rows(
        self,
        page_key: str,
        rows: list[dict[str, object | None]],
        *,
        keyword: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        date_field: str | None = None,
        product: str | None = None,
        area: str | None = None,
        quality_status: str | None = None,
        warning_status: str | None = None,
        material_category: str | None = None,
        advanced_filters: list[dict[str, str]] | None = None,
    ) -> list[dict[str, object | None]]:
        keyword_text = keyword.strip().lower() if keyword and keyword.strip() else None
        start_date_value = _parse_date_value(start_date)
        end_date_value = _parse_date_value(end_date)
        if start_date and start_date_value is None:
            raise HTTPException(
                status_code=400, detail="开始日期格式错误，应为 YYYY-MM-DD"
            )
        if end_date and end_date_value is None:
            raise HTTPException(
                status_code=400, detail="结束日期格式错误，应为 YYYY-MM-DD"
            )

        filtered_rows: list[dict[str, object | None]] = []
        for row in rows:
            if _should_hide_zero_stock_row(page_key, row):
                continue

            if keyword_text and keyword_text not in build_material_page_row_search_text(
                row
            ):
                continue

            if product:
                product_values = [
                    row.get(candidate)
                    for candidate in ("使用产品", "使用产品/类别")
                    if candidate in row
                ]
                if not any(
                    _normalize_text(item) == product.strip() for item in product_values
                ):
                    continue

            if area:
                area_values = [
                    row.get(candidate)
                    for candidate in ("库区", "出库库区", "领用车间")
                    if candidate in row
                ]
                if not any(
                    _normalize_text(item) == area.strip() for item in area_values
                ):
                    continue

            if (
                quality_status
                and _normalize_text(row.get("质量状态")) != quality_status.strip()
            ):
                continue

            if (
                material_category
                and _normalize_text(row.get("物料类别")) != material_category.strip()
            ):
                continue

            if warning_status and not _matches_warning_status(
                row.get("预警"), warning_status
            ):
                continue

            if start_date_value or end_date_value:
                date_field_candidates = (
                    [date_field.strip()] if date_field and date_field.strip() else []
                )
                if not date_field_candidates:
                    date_field_candidates = [
                        key
                        for key in row.keys()
                        if key != "__record_id" and is_material_page_date_field(key)
                    ]
                parsed_row_dates = [
                    _parse_date_value(row.get(field_name))
                    for field_name in date_field_candidates
                    if field_name in row
                ]
                row_dates: list[date] = []
                for parsed_row_date in parsed_row_dates:
                    if parsed_row_date is not None:
                        row_dates.append(parsed_row_date)
                if not row_dates:
                    continue
                if start_date_value is not None and not any(
                    item >= start_date_value for item in row_dates
                ):
                    continue
                if end_date_value is not None and not any(
                    item <= end_date_value for item in row_dates
                ):
                    continue

            if advanced_filters:
                advanced_match = True
                for filter_item in advanced_filters:
                    candidates = self._resolve_filter_field_candidates(
                        page_key,
                        filter_item["field"],
                        row,
                    )
                    if not candidates:
                        advanced_match = False
                        break
                    values = [row.get(candidate) for candidate in candidates]
                    if not self._match_filter_operator(
                        field_name=filter_item["field"],
                        candidate_values=values,
                        operator=filter_item["operator"],
                        value=filter_item["value"],
                        value_to=filter_item["value_to"],
                    ):
                        advanced_match = False
                        break
                if not advanced_match:
                    continue

            filtered_rows.append(row)
        return filtered_rows

    async def fetch_feishu_table_fields(
        self,
        *,
        app_token: str,
        table_id: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""

        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token

            material_client = await self._get_material_client(app_token)
            data = await material_client.request(
                "GET",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                params=params,
            )
            items.extend(data.get("items", []))

            if not data.get("has_more"):
                return items
            page_token = data.get("page_token", "")
            if not page_token:
                return items

    async def fetch_feishu_table_records(
        self,
        *,
        app_token: str,
        table_id: str,
        page_size: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        batch_size = min(max(page_size, 100), 500)

        # 全量拉取必须走 GET /records 列表接口：records/search 无过滤条件时
        # 最多返回 500 条且翻页循环（page_token 恒为 pageToken:500），
        # 无法通过翻页取到 500 条之后的记录（实测验证）
        for _page_index in range(200):
            # automatic_fields=true 才会返回创建人/修改人（如领料人）等自动字段
            params: dict[str, Any] = {
                "page_size": batch_size,
                "field_name_type": "name",
                "automatic_fields": True,
            }
            if page_token:
                params["page_token"] = page_token

            material_client = await self._get_material_client(app_token)
            data = await material_client.request(
                "GET",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
            new_items = data.get("items", [])
            items.extend(new_items)

            if not data.get("has_more"):
                return items
            remote_total = data.get("total", 0)
            if remote_total and len(items) >= remote_total:
                return items[:remote_total]
            page_token = data.get("page_token", "")
            if not page_token:
                return items

        return items

    async def fetch_feishu_table_records_incremental(
        self,
        *,
        app_token: str,
        table_id: str,
        page_size: int,
        sort_field: str,
        last_synced_at: datetime,
    ) -> list[dict[str, Any]]:
        """增量拉取：records/search 单页双路（业务日期 + 最近修改）合并。

        飞书 Bitable records/search 有两个实测约束（见
        fetch_feishu_table_records 处注释）：
        - 无 filter 时翻页失效（page_token 恒为 pageToken:500 循环）；
        - filter 对 DateTime/自动字段比较返回 InvalidFilter。
        因此无法真正"翻页式"增量。改为单页双路策略，每路各取一页：
        - 路一：按业务日期字段降序第一页 —— 捕捉新增/近期录入
          （业务日期在最新 500 条内的记录）；
        - 路二：按 last_modified_time 降序第一页 —— 捕捉业务日期较旧
          但近期被修改的记录；若飞书不支持按系统字段排序（请求报错），
          静默跳过本路。
        两路仅保留"日期或修改时间达到水线"的记录，按 record_id 去重合并，
        无变更轮次返回空列表（0 次写库）。第 500 条之外的历史修改由
        每日 00:00-06:00 全量兜底（scheduled.py）。
        """
        batch_size = min(max(page_size, 100), 500)
        last_synced_ms = int(last_synced_at.timestamp() * 1000) if last_synced_at else 0

        def _record_is_new(record: dict[str, Any]) -> bool:
            fields = record.get("fields") or {}
            date_value = fields.get(sort_field)
            modified_ms = record.get("last_modified_time")
            date_is_new = (
                isinstance(date_value, (int, float)) and date_value >= last_synced_ms
            )
            modified_is_new = (
                isinstance(modified_ms, (int, float)) and modified_ms >= last_synced_ms
            )
            return date_is_new or modified_is_new

        async def _search_new_records(sort_name: str) -> list[dict[str, Any]]:
            material_client = await self._get_material_client(app_token)
            data = await material_client.request(
                "POST",
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/search",
                params={
                    "page_size": batch_size,
                    "field_name_type": "name",
                    "automatic_fields": True,
                },
                json_body={"sort": [{"field_name": sort_name, "desc": True}]},
                timeout=60.0,
            )
            return [
                record for record in (data.get("items") or []) if _record_is_new(record)
            ]

        merged: dict[str, dict[str, Any]] = {}
        for route_index, sort_name in enumerate((sort_field, "last_modified_time")):
            try:
                route_records = await _search_new_records(sort_name)
            except Exception:
                if route_index == 0:
                    raise
                # 路二为兜底增强：系统字段排序不被支持时只走路一
                logger.debug(
                    "warehouse incremental last_modified_time sort unsupported: %s",
                    table_id,
                )
                continue
            for record in route_records:
                record_id = str(record.get("record_id") or "")
                if record_id:
                    merged[record_id] = record
        return list(merged.values())

    async def fetch_material_page_from_feishu(
        self,
        page_key: str,
    ) -> tuple[
        FeishuWarehouseMaterialPage,
        list[WarehouseFeishuColumn],
        list[dict[str, object | None]],
        dict[str, str],
    ]:
        page_config = await self._get_material_page_config(page_key)
        fields_response = await self.fetch_feishu_table_fields(
            app_token=page_config.app_token,
            table_id=page_config.table_id,
        )
        records_response = await self.fetch_feishu_table_records(
            app_token=page_config.app_token,
            table_id=page_config.table_id,
            page_size=500,
        )
        option_map = await self._build_page_option_map(page_config, fields_response)
        columns = self._build_columns(fields_response)
        normalized_rows = self._build_normalized_rows(
            columns, records_response, option_map=option_map
        )
        return page_config, columns, normalized_rows, option_map

    async def fetch_material_page_from_feishu_incremental(
        self,
        page_key: str,
        *,
        last_synced_at: datetime | None,
    ) -> tuple[
        FeishuWarehouseMaterialPage,
        list[WarehouseFeishuColumn],
        list[dict[str, object | None]],
        dict[str, str],
    ]:
        """增量拉取飞书页面：按日期字段降序只拉上次同步后的变更/新增。

        无日期字段（不在 _DATE_SORT_DESC_FIELDS）的表不支持增量，回退全量。
        """
        page_config = await self._get_material_page_config(page_key)
        sort_field = _DATE_SORT_DESC_FIELDS.get(page_key)
        if not sort_field or not last_synced_at:
            return await self.fetch_material_page_from_feishu(page_key)
        fields_response = await self.fetch_feishu_table_fields(
            app_token=page_config.app_token,
            table_id=page_config.table_id,
        )
        records_response = await self.fetch_feishu_table_records_incremental(
            app_token=page_config.app_token,
            table_id=page_config.table_id,
            page_size=500,
            sort_field=sort_field,
            last_synced_at=last_synced_at,
        )
        option_map = await self._build_page_option_map(page_config, fields_response)
        columns = self._build_columns(fields_response)
        normalized_rows = self._build_normalized_rows(
            columns, records_response, option_map=option_map
        )
        return page_config, columns, normalized_rows, option_map

    async def get_local_material_page(
        self,
        page_key: str,
        *,
        page: int = 1,
        page_size: int = 50,
        keyword: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        date_field: str | None = None,
        product: str | None = None,
        area: str | None = None,
        quality_status: str | None = None,
        warning_status: str | None = None,
        material_category: str | None = None,
        advanced_filters: list[dict[str, str]] | None = None,
        scope: DepartmentScope | None = None,
    ) -> WarehouseFeishuMaterialPageResponse:
        scope = await self._material_page_scope(page_key, scope)
        if page_key in HARDWARE_DEPT_PAGE_KEYS:
            assert_department_filters(scope, advanced_filters)
        snapshot = await self.repo.get_material_page_snapshot(page_key)
        if not snapshot:
            raise HTTPException(
                status_code=404,
                detail="本地仓储页面快照不存在，请先执行同步脚本",
            )

        rows, total = await self.repo.list_material_page_rows(
            snapshot.id,
            keyword=None,
            offset=0,
            limit=None,
        )
        columns = [
            WarehouseFeishuColumn(
                key=str(column.get("key", "")),
                title=str(column.get("title", "")),
                field_type=column.get("field_type"),
                readonly=bool(column.get("readonly", False)),
                view_only=bool(column.get("view_only", False)),
                editable=bool(column.get("editable", False)),
            )
            for column in snapshot.columns
            if column.get("key") and column.get("title")
        ]
        normalized_rows: list[dict[str, object | None]] = []
        for row in rows:
            normalized_row = dict(row.cells)
            normalized_row["__record_id"] = row.source_record_id
            normalized_rows.append(normalized_row)

        normalized_rows = self._scope_material_rows(page_key, normalized_rows, scope)
        filtered_rows = self._filter_material_page_rows(
            page_key,
            normalized_rows,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            date_field=date_field,
            product=product,
            area=area,
            quality_status=quality_status,
            warning_status=warning_status,
            material_category=material_category,
            advanced_filters=advanced_filters,
        )

        sort_date_field = _DATE_SORT_DESC_FIELDS.get(page_key)
        if sort_date_field:
            filtered_rows.sort(
                key=lambda r: _numeric_sort_value(r, sort_date_field),
                reverse=True,
            )

        total = len(filtered_rows)
        start = (page - 1) * page_size
        end = start + page_size
        paged_rows = filtered_rows[start:end]

        return self._build_material_page_response(
            page_key=snapshot.page_key,
            page_title=snapshot.page_title,
            table_name=snapshot.table_name,
            columns=columns,
            rows=paged_rows,
            total=total,
            page=page,
            page_size=page_size,
            last_sync_time=snapshot.last_synced_at,
            source="local_snapshot",
            base_name=self._get_base_name(page_key),
            stats=self._build_page_stats(page_key, filtered_rows),
        )

    async def get_feishu_material_page(
        self,
        page_key: str,
        *,
        page: int = 1,
        page_size: int = 50,
        keyword: str | None = None,
        source: str | None = None,
        force: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
        date_field: str | None = None,
        product: str | None = None,
        area: str | None = None,
        quality_status: str | None = None,
        warning_status: str | None = None,
        material_category: str | None = None,
        filters: str | None = None,
        scope: DepartmentScope | None = None,
    ) -> WarehouseFeishuMaterialPageResponse:
        scope = await self._material_page_scope(page_key, scope)
        if force and current_page_key.get() is not None:
            await assert_material_refresh(self.repo.session)
        advanced_filters = self._parse_advanced_filters(filters)
        if page_key in HARDWARE_DEPT_PAGE_KEYS:
            assert_department_filters(scope, advanced_filters)
        resolved_source = await self._resolve_material_page_source(source)
        # 本地快照模式：force=1（手动刷新）先做增量同步到本地镜像（秒级，
        # 只拉变更/新增），再读镜像返回。删除与历史修改由每日 00:00-06:00
        # 全量兜底对账，刷新不再全量拉取大表。其余情况直接读本地快照（秒回）。
        if resolved_source == "local":
            if force:
                await self.sync_material_page_to_local(page_key, incremental=True)
            return await self.get_local_material_page(
                page_key,
                page=page,
                page_size=page_size,
                keyword=keyword,
                start_date=start_date,
                end_date=end_date,
                date_field=date_field,
                product=product,
                area=area,
                quality_status=quality_status,
                warning_status=warning_status,
                material_category=material_category,
                advanced_filters=advanced_filters,
                scope=scope,
            )

        cache_key = page_key
        now = datetime.now(UTC)
        cached = self._page_cache.get(cache_key)
        page_config = await self._get_material_page_config(page_key)
        columns: list[WarehouseFeishuColumn]
        normalized_rows: list[dict[str, object | None]]
        if (
            not force
            and cached
            and (now - cached[0]).total_seconds() < PAGE_CACHE_TTL_SECONDS
        ):
            columns, normalized_rows = cached[1], cached[2]
        else:
            try:
                (
                    _,
                    columns,
                    normalized_rows,
                    option_map,
                ) = await self.fetch_material_page_from_feishu(page_key)
                self._page_cache[cache_key] = (
                    now,
                    columns,
                    normalized_rows,
                    option_map,
                )
            except HTTPException:
                raise
            except Exception:
                # 飞书不可达时自动降级本地快照，保证页面可用；
                # 手动强制刷新（force=1）时失败需显式报错，便于用户感知。
                if force:
                    raise HTTPException(
                        status_code=502,
                        detail="仓储飞书模板页刷新失败，请稍后重试",
                    )
                return await self.get_local_material_page(
                    page_key,
                    page=page,
                    page_size=page_size,
                    keyword=keyword,
                    start_date=start_date,
                    end_date=end_date,
                    date_field=date_field,
                    product=product,
                    area=area,
                    quality_status=quality_status,
                    warning_status=warning_status,
                    material_category=material_category,
                    advanced_filters=advanced_filters,
                    scope=scope,
                )

        filtered_rows = self._filter_material_page_rows(
            page_key,
            normalized_rows,
            keyword=keyword,
            start_date=start_date,
            end_date=end_date,
            date_field=date_field,
            product=product,
            area=area,
            quality_status=quality_status,
            warning_status=warning_status,
            material_category=material_category,
            advanced_filters=advanced_filters,
        )
        filtered_rows = self._scope_material_rows(page_key, filtered_rows, scope)
        sort_date_field = _DATE_SORT_DESC_FIELDS.get(page_key)
        if sort_date_field:
            filtered_rows.sort(
                key=lambda r: _numeric_sort_value(r, sort_date_field),
                reverse=True,
            )
        paged_rows, total = self._paginate_material_rows(
            filtered_rows,
            page=page,
            page_size=page_size,
            keyword=None,
        )

        return self._build_material_page_response(
            page_key=page_config.page_key,
            page_title=page_config.title,
            table_name=page_config.title,
            columns=columns,
            rows=paged_rows,
            total=total,
            page=page,
            page_size=page_size,
            last_sync_time=now,
            source="feishu_bitable",
            base_name=FEISHU_WAREHOUSE_BASE_NAMES.get(page_config.app_token, ""),
            stats=self._build_page_stats(page_key, filtered_rows),
        )

    async def sync_material_page_to_local(
        self,
        page_key: str,
        *,
        incremental: bool = True,
    ) -> WarehouseFeishuMaterialPageResponse:
        page_config = await self._get_material_page_config(page_key)
        prev_snapshot = await self.repo.get_material_page_snapshot(page_key)
        last_synced_at = prev_snapshot.last_synced_at if prev_snapshot else None

        # 增量条件：已有前次快照（有水线）且页面配置了日期排序字段；
        # 否则回退全量拉取（首跑或无日期字段的表）
        use_incremental = (
            incremental
            and prev_snapshot is not None
            and bool(_DATE_SORT_DESC_FIELDS.get(page_key))
        )
        try:
            if use_incremental:
                (
                    _,
                    columns,
                    normalized_rows,
                    _option_map,
                ) = await self.fetch_material_page_from_feishu_incremental(
                    page_key,
                    last_synced_at=last_synced_at,
                )
            else:
                (
                    _,
                    columns,
                    normalized_rows,
                    _option_map,
                ) = await self.fetch_material_page_from_feishu(page_key)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("warehouse Feishu page sync failed: %s", page_key)
            raise HTTPException(
                status_code=502,
                detail="仓储飞书模板页同步失败，请稍后重试",
            ) from exc

        now = datetime.now(UTC)
        snapshot = await self.repo.upsert_material_page_snapshot(
            page_key=page_config.page_key,
            page_title=page_config.title,
            table_name=page_config.title,
            table_id=page_config.table_id,
            columns=[column.model_dump(mode="python") for column in columns],
            total_rows=len(normalized_rows),
            source="feishu_bitable",
            last_synced_at=now,
            last_error=None,
        )
        row_models = []
        seen_ids: set[str] = set()
        for index, row in enumerate(normalized_rows, start=1):
            record_id = str(row.get("__record_id") or f"{page_key}-{index}")
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            row_models.append(
                MaterialPageRow(
                    page_snapshot_id=snapshot.id,
                    source_record_id=record_id,
                    row_order=index,
                    cells={
                        key: value for key, value in row.items() if key != "__record_id"
                    },
                    search_text=build_material_page_row_search_text(row),
                    last_synced_at=now,
                )
            )
        if use_incremental:
            # 增量模式：只 upsert 本次变更记录，不软删未变更的历史记录；
            # 行数以本地实际存量为准（本次拉取只含变更子集）
            await self.repo.upsert_material_page_rows_incremental(
                snapshot.id, row_models
            )
            _, total_rows = await self.repo.list_material_page_rows(
                snapshot.id, limit=1
            )
            # 建快照时写入的 total_rows 是本批变更行数（非表总量），
            # 用本地存量修正，避免增量轮次把快照行数元数据覆盖成小值
            snapshot.total_rows = total_rows
        else:
            await self.repo.upsert_material_page_rows(snapshot.id, row_models)
            total_rows = len(normalized_rows)

        return self._build_material_page_response(
            page_key=page_config.page_key,
            page_title=page_config.title,
            table_name=page_config.title,
            columns=columns,
            rows=normalized_rows[:50],
            total=total_rows,
            page=1,
            page_size=50,
            last_sync_time=now,
            source="local_snapshot",
            base_name=FEISHU_WAREHOUSE_BASE_NAMES.get(page_config.app_token, ""),
            stats=self._build_page_stats(page_key, normalized_rows),
        )

    async def sync_all_material_pages_to_local(
        self,
    ) -> dict[str, WarehouseFeishuMaterialPageResponse]:
        snapshots: dict[str, WarehouseFeishuMaterialPageResponse] = {}
        for page_key in FEISHU_WAREHOUSE_MATERIAL_PAGES:
            snapshots[page_key] = await self.sync_material_page_to_local(page_key)
        return snapshots

    # ── 库存表同步（AI 分析数据源）────────────────────────────────────

    # 飞书 summary 页字段名 → 库存表字段名（缺别名兜底）
    _INVENTORY_FIELD_MAP: dict[str, dict[str, str]] = {
        "raw-summary": {
            "使用产品/类别": "product_line",
            "物料名称": "name",
            "ERP编号": "erp_no",
            "规格": "spec",
            "单位": "unit",
            "可用库存": "available",
            "安全库存（30天）": "safety",
            "本日结存": "today_balance",
            "前台库存": "front_stock",
            "预警": "warning",
        },
        "packaging-summary": {
            "使用产品/类别": "product_line",
            "物料名称": "name",
            "ERP编号": "erp_no",
            "规格": "spec",
            "单位": "unit",
            "可用库存": "available",
            "安全库存（30天）": "safety",
            "本日结存": "today_balance",
            "前台库存": "front_stock",
            "预警": "warning",
        },
        "product-summary": {
            "产品名称": "name",
            "包装规格": "spec",
            "单位": "unit",
            "订单量": "order_quantity",
            "待检数量": "pending_quantity",
            "合格数量": "qualified_quantity",
            "小计": "subtotal_quantity",
            "剩余量": "remaining_quantity",
        },
    }

    @staticmethod
    def _safe_str(value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    async def _sync_inventory_page(
        self,
        page_key: str,
    ) -> int:
        """同步单个 summary 页到对应库存表，返回写入/更新行数。"""
        if page_key not in self._INVENTORY_FIELD_MAP:
            raise ValueError(f"unsupported inventory page_key: {page_key}")

        (
            _page_config,
            columns,
            normalized_rows,
            _option_map,
        ) = await self.fetch_material_page_from_feishu(page_key)
        field_map = self._INVENTORY_FIELD_MAP[page_key]
        # 列键名（中文字段）→ 库存表字段名；过滤未知列
        col_to_field = {
            column.key: field_map[column.key]
            for column in columns
            if column.key in field_map
        }

        count = 0
        for row in normalized_rows:
            source_id = self._safe_str(row.get("__record_id"))
            fields = {
                model_field: row.get(feishu_field)
                for feishu_field, model_field in col_to_field.items()
            }
            code = (
                self._safe_str(fields.get("code"))
                or self._safe_str(row.get("厂内代码"))
                or ""
            )
            name = self._safe_str(fields.get("name")) or ""
            if not code and not name:
                continue
            product_line = self._safe_str(fields.get("product_line"))

            if page_key == "raw-summary":
                await self.upsert_raw_material_snapshot(
                    source_id=source_id,
                    code=code,
                    name=name,
                    spec=self._safe_str(fields.get("spec")),
                    unit=self._safe_str(fields.get("unit")),
                    available=_parse_number(fields.get("available")),
                    safety=_parse_number(fields.get("safety")),
                    last_month=0,
                    two_months_ago=0,
                    today_balance=_parse_number(fields.get("today_balance")),
                    front_stock=_parse_number(fields.get("front_stock")),
                    this_month_use=0,
                    warning=self._safe_str(fields.get("warning")),
                    product_line=product_line,
                    erp_no=self._safe_str(fields.get("erp_no")),
                    delivery=None,
                    remark=None,
                    source="feishu_bitable",
                )
            elif page_key == "packaging-summary":
                await self.upsert_packaging_snapshot(
                    source_id=source_id,
                    code=code,
                    name=name,
                    spec=self._safe_str(fields.get("spec")),
                    batch=None,
                    available=_parse_number(fields.get("available")),
                    safety=_parse_number(fields.get("safety")),
                    last_month=0,
                    two_months_ago=0,
                    today_balance=_parse_number(fields.get("today_balance")),
                    front_stock=_parse_number(fields.get("front_stock")),
                    this_month_use=0,
                    warning=self._safe_str(fields.get("warning")),
                    product_line=product_line,
                    erp_no=self._safe_str(fields.get("erp_no")),
                    delivery=None,
                    remark=None,
                    source="feishu_bitable",
                )
            else:  # product-summary
                await self.upsert_product_snapshot(
                    source_id=source_id,
                    name=name,
                    spec=self._safe_str(fields.get("spec")),
                    order_quantity=_parse_number(fields.get("order_quantity")),
                    pending_quantity=_parse_number(fields.get("pending_quantity")),
                    qualified_quantity=_parse_number(fields.get("qualified_quantity")),
                    subtotal_quantity=_parse_number(fields.get("subtotal_quantity")),
                    remaining_quantity=_parse_number(fields.get("remaining_quantity")),
                    unit=self._safe_str(fields.get("unit")),
                    remark=None,
                    source="feishu_bitable",
                )
            count += 1
        return count

    async def sync_inventory_from_feishu(self) -> dict[str, int]:
        """从飞书 summary 页同步三张库存表（AI 分析数据源）。

        逐页 try/except 隔离，单页失败不阻断其他页。
        """
        result: dict[str, int] = {}
        summary_pages = ("raw-summary", "packaging-summary", "product-summary")
        for page_key in summary_pages:
            try:
                result[page_key] = await self._sync_inventory_page(page_key)
                logger.info(
                    "warehouse inventory synced from feishu",
                    extra={"page": page_key, "count": result[page_key]},
                )
            except Exception:
                logger.exception(
                    "warehouse inventory sync failed",
                    extra={"page": page_key},
                )
                result[page_key] = 0
        return result

    async def get_dashboard_data(
        self,
        group: str,
        force: bool = False,
        detail: bool = False,
        scope: DepartmentScope | None = None,
    ) -> dict[str, Any]:
        """按分组返回仓储仪表盘数据（对齐飞书多维表格仪表盘并补充业务缺口指标）。

        group: raw（原辅料及包材）/ hardware（五金）/ product（成品）。
        force: 绕过 300s 聚合缓存强制从飞书拉取最新数据。
        detail: 附加各组 KPI 的明细行（供卡片点击查看）。
        scope: 部门数据范围；五金组按可见部门过滤部门聚合（其余组无部门字段）。
        """
        cache_key = group
        cached = self._dashboard_cache.get(cache_key)
        if not force and cached and time.time() - cached[0] < 300:
            data = cached[1]
        else:
            if group == "raw":
                data = await self._build_raw_dashboard(force, detail)
            elif group == "hardware":
                data = await self._build_hardware_dashboard(force, detail)
            elif group == "product":
                data = await self._build_product_dashboard(force, detail)
            else:
                raise HTTPException(
                    status_code=400, detail="group 仅支持 raw / hardware / product"
                )
            self._dashboard_cache[cache_key] = (time.time(), data)
            return self._apply_dashboard_scope(data, group, scope)

        # 缓存命中但请求需要 detail：若缓存数据无 detail
        # 则重新聚合一次（不强制刷新飞书）
        if detail and "detail" not in data:
            if group == "raw":
                data = await self._build_raw_dashboard(False, True)
            elif group == "hardware":
                data = await self._build_hardware_dashboard(False, True)
            elif group == "product":
                data = await self._build_product_dashboard(False, True)
            self._dashboard_cache[cache_key] = (time.time(), data)
        return self._apply_dashboard_scope(data, group, scope)

    @staticmethod
    def _apply_dashboard_scope(
        data: dict[str, Any],
        group: str,
        scope: DepartmentScope | None,
    ) -> dict[str, Any]:
        """仪表盘出口处按部门范围过滤（聚合缓存共享，按用户范围裁剪）。

        五金组：dept_stock / dept_outbound_30d 按部门过滤，
        stock_amount / outbound_30d_total 重算为可见部门之和（口径一致）；
        出入库明细行按部门过滤；其余组无部门字段不处理。
        """
        if group != "hardware" or scope is None or scope.is_all:
            return data
        dept_stock = [
            item
            for item in data.get("dept_stock", [])
            if scope.allows(str(item.get("dept") or ""))
        ]
        dept_outbound = [
            item
            for item in data.get("dept_outbound_30d", [])
            if scope.allows(str(item.get("dept") or ""))
        ]
        filtered = dict(data)
        filtered["dept_stock"] = dept_stock
        filtered["dept_outbound_30d"] = dept_outbound
        # 总金额重算为可见部门之和（口径：卡片数字 = 明细行之和）
        filtered["stock_amount"] = round(
            sum(item.get("value", 0) for item in dept_stock), 2
        )
        filtered["outbound_30d_total"] = round(
            sum(item.get("value", 0) for item in dept_outbound), 2
        )
        if isinstance(data.get("detail"), dict):
            detail_data = dict(data["detail"])
            detail_data["dept_stock"] = dept_stock
            detail_data["outbound_30d"] = [
                row
                for row in detail_data.get("outbound_30d", [])
                if scope.allows(str(row.get("dept") or ""))
            ]
            filtered["detail"] = detail_data
        return filtered

    async def _load_local_page_rows(
        self, page_key: str
    ) -> list[dict[str, object | None]] | None:
        """读本地快照全量行；快照不存在返回 None（由调用方回退飞书）。"""
        snapshot = await self.repo.get_material_page_snapshot(page_key)
        if not snapshot:
            return None
        rows, _ = await self.repo.list_material_page_rows(
            snapshot.id, keyword=None, offset=0, limit=None
        )
        return [dict(row.cells) | {"__record_id": row.source_record_id} for row in rows]

    async def _load_page_rows(
        self, page_key: str, force: bool
    ) -> list[dict[str, object | None]]:
        """拉取页面全量数据：默认读本地快照（秒回）；force 时直连飞书实时拉取。"""
        if not force:
            local_rows = await self._load_local_page_rows(page_key)
            if local_rows is not None:
                return local_rows
        if force:
            self._invalidate_page_cache(page_key)
        _, _, rows, _ = await self.fetch_material_page_from_feishu(page_key)
        return rows

    async def _build_raw_dashboard(
        self, force: bool = False, detail: bool = False
    ) -> dict[str, Any]:
        "原辅料及包材仪表盘：安全库存、质量批数、30 天出库趋势、本月入库、低库存 Top。"
        t0 = time.time()
        (
            summary_rows,
            detail_rows,
            ledger_rows,
            packaging_rows,
            inbound_rows,
        ) = await asyncio.gather(
            self._load_page_rows("raw-summary", force),
            self._load_page_rows("raw-detail", force),
            self._load_page_rows("raw-ledger", force),
            self._load_page_rows("packaging-ledger", force),
            self._load_page_rows("inbound-ledger", force),
        )

        safety_total = 0
        safety_ok = 0
        safety_ok_list: list[dict[str, Any]] = []
        safety_low_list: list[dict[str, Any]] = []
        low_stock_top: list[dict[str, Any]] = []
        for row in summary_rows:
            safety = _parse_number(row.get("安全库存（30天）")) or 0
            balance = _parse_number(row.get("本日结存")) or 0
            front_stock = _parse_number(row.get("前台库存")) or 0
            product_line = _normalize_text(row.get("使用产品/类别"))
            warning = _normalize_text(row.get("预警"))
            material_name = _normalize_text(row.get("物料名称")) or "（未标注）"
            if safety > 0:
                safety_total += 1
                # 判定口径与飞书"预警"公式一致：
                # 预混剂按本日结存，其余按可用库存（本日结存 - 前台库存）
                effective_balance = (
                    balance if product_line == "预混剂" else balance - front_stock
                )
                if effective_balance >= safety:
                    safety_ok += 1
                    if detail:
                        safety_ok_list.append(
                            {
                                "name": material_name,
                                "balance": round(balance, 2),
                                "effective_balance": round(effective_balance, 2),
                                "safety": round(safety, 2),
                            }
                        )
            if warning in ("库存不足", "库存严重不足"):
                item = {
                    "name": material_name,
                    "balance": round(balance, 2),
                    "effective_balance": round(effective_balance, 2),
                    "safety": round(safety, 2),
                    "warning": warning,
                }
                if detail:
                    safety_low_list.append(item)
                low_stock_top.append(item)
        low_stock_top.sort(
            key=lambda item: 0 if item["warning"] == "库存严重不足" else 1
        )

        quality = {"合格": 0, "待验": 0, "不合格": 0}
        pending_list: list[dict[str, Any]] = []
        for row in detail_rows:
            status = _normalize_text(row.get("质量状态"))
            if status in quality:
                quality[status] += 1
                if detail and status == "待验":
                    pending_list.append(
                        {
                            "name": _normalize_text(row.get("物料名称"))
                            or "（未标注）",
                            "batch": _normalize_text(row.get("厂内批号")) or "",
                            "balance": _parse_number(row.get("本日结存")) or 0,
                            "quality_status": status,
                            "area": _normalize_text(row.get("库区")) or "",
                        }
                    )

        material_trend = _aggregate_daily_trend(
            ledger_rows, "出库日期", ("出库数量", "领用数量（Kg）")
        )
        packaging_total_30d = sum(
            item["value"]
            for item in _aggregate_daily_trend(
                packaging_rows, "出库日期", ("出库数量", "领用数量（条/个）")
            )
        )
        # 本月入库数量（入库总账，日期=本月）
        now = datetime.now(CHINA_TIMEZONE)
        month_inbound_total = 0.0
        month_inbound_list: list[dict[str, Any]] = []
        for row in inbound_rows:
            day = _parse_date_value(row.get("入库日期"))
            if day is None or day.year != now.year or day.month != now.month:
                continue
            quantity = _parse_number(row.get("入库数量")) or 0
            month_inbound_total += quantity
            if detail:
                month_inbound_list.append(
                    {
                        "date": day.isoformat(),
                        "category": _normalize_text(row.get("物料类别")) or "",
                        "name": _normalize_text(row.get("物料名称")) or "（未标注）",
                        "spec": _normalize_text(row.get("规格")) or "",
                        "batch": _normalize_text(row.get("厂内批号")) or "",
                        "quantity": round(quantity, 2),
                        "supplier": _normalize_text(row.get("供应商")) or "",
                    }
                )

        result = {
            "safety": {
                "total": safety_total,
                "ok": safety_ok,
                "low": safety_total - safety_ok,
            },
            "quality": quality,
            "material_outbound_30d": material_trend,
            "packaging_outbound_30d_total": round(packaging_total_30d, 2),
            "month_inbound_total": round(month_inbound_total, 2),
            "low_stock_top": low_stock_top[:10],
        }
        if detail:
            result["detail"] = {
                "safety_ok": safety_ok_list,
                "safety_low": safety_low_list,
                "pending": pending_list[:200],
                "month_inbound": month_inbound_list[:100],
            }
        logger.info(
            "warehouse dashboard raw computed",
            extra={
                "mod": "warehouse",
                "group": "raw",
                "elapsed_ms": round((time.time() - t0) * 1000),
            },
        )
        return result

    async def _build_hardware_dashboard(
        self, force: bool = False, detail: bool = False
    ) -> dict[str, Any]:
        """五金仪表盘：库存金额、各部门库存金额、30 天出入库金额与部门分布。"""
        t0 = time.time()
        (
            summary_rows,
            stock_amount_rows,
            inbound_rows,
            outbound_rows,
        ) = await asyncio.gather(
            self._load_page_rows("hardware-summary", force),
            self._load_page_rows("hardware-stock-amount", force),
            self._load_page_rows("hardware-inbound-ledger", force),
            self._load_page_rows("hardware-outbound-ledger", force),
        )

        stock_amount = sum(
            _parse_number(row.get("金额（元）")) or 0 for row in summary_rows
        )

        # 库存五金金额表：单行，各车间列为金额
        dept_stock: list[dict[str, Any]] = []
        for row in stock_amount_rows:
            for key, value in row.items():
                if key in ("__record_id", "车间名称", "总金额"):
                    continue
                amount = _parse_number(value)
                if amount is not None and amount != 0:
                    dept_stock.append({"dept": key, "value": round(amount, 2)})
        dept_stock.sort(key=lambda item: item["value"], reverse=True)

        now = datetime.now(CHINA_TIMEZONE)
        cutoff = now.date() - timedelta(days=29)
        # 入库记录无金额字段：金额 = 入库量 × 单价（元）
        inbound_total_30d = 0.0
        inbound_30d_list: list[dict[str, Any]] = []
        for row in inbound_rows:
            day = _parse_date_value(row.get("日期"))
            if day is None or day < cutoff:
                continue
            qty = _parse_number(row.get("入库量"))
            price = _parse_number(row.get("单价（元）"))
            if qty is not None and price is not None:
                amount = qty * price
                inbound_total_30d += amount
                if detail:
                    inbound_30d_list.append(
                        {
                            "date": day.isoformat(),
                            "name": _normalize_text(row.get("物料名称"))
                            or "（未标注）",
                            "spec": _normalize_text(row.get("规格")) or "",
                            "quantity": round(qty, 2),
                            "price": round(price, 2),
                            "amount": round(amount, 2),
                        }
                    )

        outbound_trend = _aggregate_daily_trend(
            outbound_rows, "日期", ("金额",), days=30
        )
        dept_outbound: dict[str, float] = {}
        outbound_30d_list: list[dict[str, Any]] = []
        for row in outbound_rows:
            amount = _parse_number(row.get("金额"))
            if amount is None or amount <= 0:
                continue
            day = _parse_date_value(row.get("日期"))
            if day is None or day < cutoff:
                continue
            dept = _pick_dept_name(row.get("归属库区"))
            dept_outbound[dept] = dept_outbound.get(dept, 0) + amount
            if detail:
                outbound_30d_list.append(
                    {
                        "date": day.isoformat(),
                        "name": _normalize_text(row.get("物料名称")) or "（未标注）",
                        "spec": _normalize_text(row.get("规格")) or "",
                        "dept": dept,
                        "amount": round(amount, 2),
                    }
                )

        result = {
            "stock_amount": round(stock_amount, 2),
            "dept_stock": dept_stock,
            "inbound_30d_total": round(inbound_total_30d, 2),
            "outbound_30d_total": round(
                sum(item["value"] for item in outbound_trend), 2
            ),
            "outbound_30d_trend": outbound_trend,
            "dept_outbound_30d": [
                {"dept": dept, "value": round(value, 2)}
                for dept, value in sorted(
                    dept_outbound.items(), key=lambda item: item[1], reverse=True
                )
            ],
        }
        if detail:
            result["detail"] = {
                "dept_stock": dept_stock,
                "inbound_30d": inbound_30d_list[:100],
                "outbound_30d": outbound_30d_list[:100],
            }
        logger.info(
            "warehouse dashboard hardware computed",
            extra={
                "mod": "warehouse",
                "group": "hardware",
                "elapsed_ms": round((time.time() - t0) * 1000),
            },
        )
        return result

    async def _build_product_dashboard(
        self, force: bool = False, detail: bool = False
    ) -> dict[str, Any]:
        """成品仪表盘：基于每月出入库宽表聚合 + 零活动产品排查。"""
        t0 = time.time()
        (
            summary_rows,
            shipping_rows,
            inbound_monthly_rows,
            outbound_monthly_rows,
        ) = await asyncio.gather(
            self._load_page_rows("product-summary", force),
            self._load_page_rows("product-shipping", force),
            self._load_page_rows("product-inbound-monthly", force),
            self._load_page_rows("product-outbound-monthly", force),
        )

        qualified = sum(_parse_number(row.get("合格数量")) or 0 for row in summary_rows)
        pending = sum(_parse_number(row.get("待检数量")) or 0 for row in summary_rows)

        # 各产品库存量（合格+待验）/ 各产品合格数量 / 各产品待验数量
        product_stock: dict[str, float] = {}
        product_qualified: dict[str, float] = {}
        product_pending: dict[str, float] = {}
        for row in summary_rows:
            name = _normalize_text(row.get("产品名称"))
            if not name:
                continue
            qualified_qty = _parse_number(row.get("合格数量")) or 0
            pending_qty = _parse_number(row.get("待检数量")) or 0
            product_stock[name] = (
                product_stock.get(name, 0) + qualified_qty + pending_qty
            )
            product_qualified[name] = product_qualified.get(name, 0) + qualified_qty
            product_pending[name] = product_pending.get(name, 0) + pending_qty

        product_outbound: dict[str, float] = {}
        for row in shipping_rows:
            name = _normalize_text(row.get("产品名称"))
            quantity = _parse_number(row.get("发货数量"))
            if not name or quantity is None or quantity <= 0:
                continue
            product_outbound[name] = product_outbound.get(name, 0) + quantity

        shipping_trend = _aggregate_daily_trend(shipping_rows, "日期", ("发货数量",))

        # 解析宽表：月份 × 产品
        product_monthly_inbound = self._parse_wide_table(
            inbound_monthly_rows, exclude_fields=["月份"]
        )
        product_monthly_outbound = self._parse_wide_table(
            outbound_monthly_rows, exclude_fields=["月份"]
        )

        # 排查 2026 年整年零活动产品
        zero_activity_products = self._find_zero_activity_products(
            product_monthly_inbound,
            product_monthly_outbound,
            year=2026,
        )

        result = {
            "qualified": round(qualified, 2),
            "pending": round(pending, 2),
            "product_stock": [
                {"name": name, "value": round(value, 2)}
                for name, value in sorted(
                    product_stock.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "product_outbound": [
                {"name": name, "value": round(value, 2)}
                for name, value in sorted(
                    product_outbound.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "product_qualified": [
                {"name": name, "value": round(value, 2)}
                for name, value in sorted(
                    product_qualified.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "product_pending": [
                {"name": name, "value": round(value, 2)}
                for name, value in sorted(
                    product_pending.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "shipping_30d_trend": shipping_trend,
            "product_monthly_inbound": product_monthly_inbound,
            "product_monthly_outbound": product_monthly_outbound,
            "zero_activity_products": zero_activity_products,
        }
        if detail:
            result["detail"] = {
                "qualified": [
                    {"name": name, "value": round(value, 2)}
                    for name, value in sorted(
                        product_qualified.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                ],
                "pending": [
                    {"name": name, "value": round(value, 2)}
                    for name, value in sorted(
                        product_pending.items(), key=lambda item: item[1], reverse=True
                    )
                ],
                "product_stock": [
                    {"name": name, "value": round(value, 2)}
                    for name, value in sorted(
                        product_stock.items(), key=lambda item: item[1], reverse=True
                    )
                ],
            }
        logger.info(
            "warehouse dashboard product computed",
            extra={
                "mod": "warehouse",
                "group": "product",
                "elapsed_ms": round((time.time() - t0) * 1000),
            },
        )
        return result

    def _parse_wide_table(
        self, rows: list[dict[str, object | None]], exclude_fields: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """解析宽表：返回 {产品名：[{月份，数量}]}"""
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            month = _normalize_text(row.get("月份"))
            if not month:
                continue
            for field_name, value in row.items():
                if field_name in exclude_fields or field_name == "__record_id":
                    continue
                qty = _parse_number(value)
                if qty is None or qty == 0:
                    continue
                if field_name not in result:
                    result[field_name] = []
                result[field_name].append({"month": month, "quantity": qty})
        return result

    def _find_zero_activity_products(
        self,
        inbound: dict[str, list[dict[str, Any]]],
        outbound: dict[str, list[dict[str, Any]]],
        year: int,
    ) -> list[str]:
        """排查指定年份整年零活动产品（入库 + 出库均为 0）。"""
        all_products = set(inbound.keys()) | set(outbound.keys())
        zero_activity: list[str] = []
        for product in all_products:
            has_activity = False
            for month_num in range(1, 13):
                month_str = f"{year}-{month_num:02d}"
                inbound_values = inbound.get(product, [])
                if any(
                    v["month"] == month_str and v["quantity"] > 0
                    for v in inbound_values
                ):
                    has_activity = True
                    break
                outbound_values = outbound.get(product, [])
                if any(
                    v["month"] == month_str and v["quantity"] > 0
                    for v in outbound_values
                ):
                    has_activity = True
                    break
            if not has_activity:
                zero_activity.append(product)
        return sorted(zero_activity)

    async def get_material_page_record_detail(
        self,
        page_key: str,
        record_id: str,
        *,
        scope: DepartmentScope | None = None,
    ) -> dict[str, Any]:
        """获取单条记录的全部字段（含列表未展示字段）与可写性元信息。"""
        scope = await self._material_page_scope(page_key, scope)
        page_config = await self._get_material_page_config(page_key)
        fields_meta = await self._get_page_field_meta(page_config)
        option_map = await self._build_page_option_map(page_config, fields_meta)
        data = await (await self._get_feishu_client()).request(
            "GET",
            f"/bitable/v1/apps/{page_config.app_token}/tables/{page_config.table_id}/records/{record_id}",
        )
        record = data.get("record") or {}
        field_map = record.get("fields", {}) or {}
        if not isinstance(field_map, dict):
            field_map = {}
        if page_key in HARDWARE_DEPT_PAGE_KEYS:
            assert_record_department(
                scope,
                normalize_feishu_cell_value(
                    resolve_option_ids(field_map.get("车间"), option_map)
                ),
            )

        meta_by_name = {str(f.get("field_name", "")): f for f in fields_meta}
        ordered_names = [str(f.get("field_name", "")) for f in fields_meta]
        for name in field_map:
            if name not in meta_by_name:
                ordered_names.append(str(name))

        detail_fields: list[WarehouseRecordFieldValue] = []
        for name in ordered_names:
            if not name:
                continue
            meta = meta_by_name.get(name, {})
            field_type = meta.get("type")
            options: list[dict[str, Any]] | None = None
            property_obj = meta.get("property")
            if isinstance(property_obj, dict) and isinstance(
                property_obj.get("options"), list
            ):
                options = [
                    {
                        "id": str(option.get("id", ""))
                        if isinstance(option, dict)
                        else "",
                        "name": str(option.get("name", ""))
                        if isinstance(option, dict)
                        else str(option),
                    }
                    for option in property_obj["options"]
                ]
            detail_fields.append(
                WarehouseRecordFieldValue(
                    field_name=name,
                    field_type=field_type,
                    readonly=is_readonly_field(field_type),
                    view_only=is_view_only_field(field_type),
                    editable=is_editable_field(field_type),
                    options=options,
                    value=format_detail_value(
                        field_type,
                        resolve_option_ids(field_map.get(name), option_map),
                    ),
                )
            )

        return WarehouseRecordDetailResponse(
            record_id=record.get("record_id") or record_id,
            fields=detail_fields,
        ).model_dump(mode="json")

    async def update_material_page_record(
        self,
        page_key: str,
        record_id: str,
        fields: dict[str, Any],
        *,
        scope: DepartmentScope | None = None,
    ) -> dict[str, Any]:
        """将页面编辑值按字段类型转换后写回飞书多维表格。

        公式/系统字段与人员/附件/关联字段为不可写字段，静默跳过并记日志，
        保证页面与多维表格不会出现静默不一致。
        """
        scope = await self._material_page_scope(page_key, scope)
        if (
            scope is not None
            and not scope.is_all
            and page_key in HARDWARE_DEPT_PAGE_KEYS
        ):
            existing = await self.get_material_page_record_detail(
                page_key, record_id, scope=scope
            )
            if "车间" in fields:
                # 归属变更会改变记录可见性；禁止受限授权通过写入转移部门。
                department = next(
                    (
                        field["value"]
                        for field in existing["fields"]
                        if field["field_name"] == "车间"
                    ),
                    None,
                )
                if not isinstance(fields["车间"], str) or fields["车间"] != department:
                    raise HTTPException(403, "受限部门授权不能修改记录归属车间")
        page_config = await self._get_material_page_config(page_key)
        fields_meta = await self._get_page_field_meta(page_config)
        meta_by_name = {str(f.get("field_name", "")): f for f in fields_meta}

        payload: dict[str, Any] = {}
        skipped: list[str] = []
        for field_name, value in fields.items():
            meta = meta_by_name.get(field_name)
            if not meta:
                raise HTTPException(status_code=400, detail=f"字段不存在: {field_name}")
            field_type = meta.get("type")
            if is_readonly_field(field_type) or is_view_only_field(field_type):
                skipped.append(field_name)
                continue
            converted = build_feishu_cell_value(field_type, value)
            if converted is None:
                skipped.append(field_name)
                continue
            payload[field_name] = converted

        if not payload:
            raise HTTPException(status_code=400, detail="没有可更新的可写字段")
        if skipped:
            logger.info(
                "仓储页面更新跳过不可写字段: page=%s skipped=%s",
                page_key,
                ",".join(skipped),
            )

        # 写回与读取/同步同用模块自有应用：平台应用未开通多维表格写
        # scope（bitable:app / base:record:update），用它写回会被飞书
        # 以 99991672 拒绝
        client = await self._get_material_client(page_config.app_token)
        try:
            data = await client.request(
                "PUT",
                (
                    f"/bitable/v1/apps/{page_config.app_token}"
                    f"/tables/{page_config.table_id}/records/{record_id}"
                ),
                json_body={"fields": payload},
            )
            record = data.get("record", {}) if isinstance(data, dict) else {}
        except Exception as exc:
            logger.exception("warehouse Feishu record update failed")
            raise HTTPException(
                status_code=502,
                detail="同步更新到飞书失败，请稍后重试",
            ) from exc
        self._invalidate_page_cache(page_key)
        return record

    async def delete_material_page_record(
        self, page_key: str, record_id: str, *, scope: DepartmentScope | None = None
    ) -> None:
        """删除飞书多维表格中的记录。"""
        scope = await self._material_page_scope(page_key, scope)
        if (
            scope is not None
            and not scope.is_all
            and page_key in HARDWARE_DEPT_PAGE_KEYS
        ):
            await self.get_material_page_record_detail(page_key, record_id, scope=scope)
        page_config = await self._get_material_page_config(page_key)
        client = await self._get_material_client(page_config.app_token)
        try:
            await client.request(
                "DELETE",
                (
                    f"/bitable/v1/apps/{page_config.app_token}"
                    f"/tables/{page_config.table_id}/records/{record_id}"
                ),
            )
        except Exception as exc:
            logger.exception("warehouse Feishu record delete failed")
            raise HTTPException(
                status_code=502,
                detail="同步删除到飞书失败，请稍后重试",
            ) from exc
        self._invalidate_page_cache(page_key)

    async def upsert_raw_material_snapshot(
        self,
        *,
        source_id: str | None,
        code: str,
        name: str,
        spec: str | None,
        unit: str | None,
        available: float | int | None,
        safety: float | int | None,
        last_month: float | int | None,
        two_months_ago: float | int | None,
        today_balance: float | int | None,
        front_stock: float | int | None,
        this_month_use: float | int | None,
        warning: str | None,
        product_line: str | None,
        erp_no: str | None,
        delivery: str | None,
        remark: str | None,
        source: str,
    ) -> RawMaterialInventory:
        import_key = build_warehouse_import_key(source_id, code, name, product_line)
        existing = await self.repo.get_raw_material_by_import_key(import_key)
        payload = {
            "source_id": source_id,
            "code": code,
            "name": name,
            "spec": spec,
            "unit": unit,
            "available": _safe_number(available),
            "safety": _safe_number(safety),
            "last_month": _safe_number(last_month),
            "two_months_ago": _safe_number(two_months_ago),
            "today_balance": _safe_number(today_balance),
            "front_stock": _safe_number(front_stock),
            "this_month_use": _safe_number(this_month_use),
            "warning": warning,
            "product_line": product_line,
            "erp_no": erp_no,
            "delivery": delivery,
            "remark": remark,
            "source": source,
            "import_key": import_key,
            "last_synced_at": datetime.now(UTC),
        }
        if existing:
            for field, value in payload.items():
                setattr(existing, field, value)
            existing.is_deleted = False
            await self.repo.session.flush()
            await self.repo.session.refresh(existing)
            return existing

        item = RawMaterialInventory(**payload)
        return await self.repo.create_raw_material(item)

    async def upsert_packaging_snapshot(
        self,
        *,
        source_id: str | None,
        code: str,
        name: str,
        spec: str | None,
        batch: str | None,
        available: float | int | None,
        safety: float | int | None,
        last_month: float | int | None,
        two_months_ago: float | int | None,
        today_balance: float | int | None,
        front_stock: float | int | None,
        this_month_use: float | int | None,
        warning: str | None,
        product_line: str | None,
        erp_no: str | None,
        delivery: str | None,
        remark: str | None,
        source: str,
    ) -> PackagingMaterialInventory:
        import_key = build_warehouse_import_key(source_id, code, name, product_line)
        existing = await self.repo.get_packaging_material_by_import_key(import_key)
        payload = {
            "source_id": source_id,
            "code": code,
            "name": name,
            "spec": spec,
            "batch": batch,
            "available": _safe_number(available),
            "safety": _safe_number(safety),
            "last_month": _safe_number(last_month),
            "two_months_ago": _safe_number(two_months_ago),
            "today_balance": _safe_number(today_balance),
            "front_stock": _safe_number(front_stock),
            "this_month_use": _safe_number(this_month_use),
            "warning": warning,
            "product_line": product_line,
            "erp_no": erp_no,
            "delivery": delivery,
            "remark": remark,
            "source": source,
            "import_key": import_key,
            "last_synced_at": datetime.now(UTC),
        }
        if existing:
            for field, value in payload.items():
                setattr(existing, field, value)
            existing.is_deleted = False
            await self.repo.session.flush()
            await self.repo.session.refresh(existing)
            return existing

        item = PackagingMaterialInventory(**payload)
        return await self.repo.create_packaging_material(item)

    async def upsert_product_snapshot(
        self,
        *,
        source_id: str | None,
        name: str,
        spec: str | None,
        order_quantity: float | int | None,
        pending_quantity: float | int | None,
        qualified_quantity: float | int | None,
        subtotal_quantity: float | int | None,
        remaining_quantity: float | int | None,
        unit: str | None,
        remark: str | None,
        source: str,
    ) -> ProductInventory:
        import_key = build_warehouse_import_key(source_id, name, spec, unit)
        existing = await self.repo.get_product_by_import_key(import_key)
        payload = {
            "source_id": source_id,
            "name": name,
            "spec": spec,
            "order_quantity": _safe_number(order_quantity),
            "pending_quantity": _safe_number(pending_quantity),
            "qualified_quantity": _safe_number(qualified_quantity),
            "subtotal_quantity": _safe_number(subtotal_quantity),
            "remaining_quantity": _safe_number(remaining_quantity),
            "unit": unit,
            "remark": remark,
            "source": source,
            "import_key": import_key,
            "last_synced_at": datetime.now(UTC),
        }
        if existing:
            for field, value in payload.items():
                setattr(existing, field, value)
            existing.is_deleted = False
            await self.repo.session.flush()
            await self.repo.session.refresh(existing)
            return existing

        item = ProductInventory(**payload)
        return await self.repo.create_product(item)

    # ── 页面飞书配置管理 ────────────────────────────────────────────────

    async def get_all_page_feishu_configs(self) -> list[dict[str, Any]]:
        """获取所有页面的飞书配置；首次访问时自动补齐硬编码映射，保证设置页有完整数据。"""
        existing = await self.repo.list_page_feishu_configs()
        existing_keys = {item["page_key"] for item in existing}
        for page_key, page_config in FEISHU_WAREHOUSE_MATERIAL_PAGES.items():
            if page_key in existing_keys:
                continue
            try:
                await self.repo.upsert_page_feishu_config(
                    {
                        "page_key": page_key,
                        "app_token": page_config.app_token,
                        "table_id": page_config.table_id,
                        "table_name": page_config.title,
                        "view_id": None,
                    }
                )
            except Exception as exc:
                logger.warning(
                    "warehouse page config auto-seed failed: page=%s err=%s",
                    page_key,
                    exc,
                )
        return await self.repo.list_page_feishu_configs()

    async def get_page_feishu_config(self, page_key: str) -> dict[str, Any] | None:
        """获取指定页面的飞书配置"""
        return await self.repo.get_page_feishu_config(page_key)

    async def update_page_feishu_config(
        self, page_key: str, config: dict[str, Any]
    ) -> None:
        """更新页面飞书配置"""
        await self.repo.upsert_page_feishu_config(config)
        # 清除该页缓存
        self._invalidate_page_cache(page_key)

    # ── Legacy Agent / WebSocket compatibility ─────────────────────

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {"summary": str(value or "")}

    @staticmethod
    def _as_dict_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return [{"summary": str(value)}] if value else []
        return [
            item if isinstance(item, dict) else {"summary": str(item)} for item in value
        ]

    @staticmethod
    def _normalize_field_filter(
        *,
        field: str | None,
        field_operator: str | None,
        field_value: str | None,
    ) -> tuple[str | None, str | None]:
        operator = (field_operator or "").strip() or None
        value = (field_value or "").strip() or None
        if not operator and value:
            operator = "contains"
        if not operator:
            return None, None
        if not field:
            raise AppException(message="请选择要筛选的字段")
        if operator not in FIELD_FILTER_OPERATORS:
            raise AppException(message="字段筛选条件无效")
        if value is None:
            raise AppException(message="请填写字段筛选值")
        if operator in NUMERIC_FIELD_FILTER_OPERATORS:
            try:
                float(value)
            except ValueError as exc:
                raise AppException(message="数值比较条件必须填写数字") from exc
        return operator, value

    async def _get_any_feishu_config_or_raise(self) -> Any | None:
        try:
            return await self.repo.get_any_feishu_config()
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "仓储飞书配置表不可用，请先执行数据库迁移：alembic upgrade head"
                ),
                detail=exc.__class__.__name__,
            ) from exc

    async def _get_material_client(self, app_token: str) -> Any:
        """使用仓储模块自有应用访问物料页，禁止回退登录应用。"""
        cached = _MATERIAL_SYNC_CLIENTS.get(app_token)
        if cached is not None:
            return cached
        config = await self._get_active_feishu_config_or_raise()
        client = self._build_feishu_client(config, app_token)
        _MATERIAL_SYNC_CLIENTS[app_token] = client
        return client

    async def _get_active_feishu_config_or_raise(self) -> Any:
        try:
            config = await self.repo.get_active_feishu_config()
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "仓储飞书配置表不可用，请先执行数据库迁移：alembic upgrade head"
                ),
                detail=exc.__class__.__name__,
            ) from exc
        if not config:
            raise AppException(message="请先启用仓储飞书配置")
        return config

    async def _get_table_by_id_or_raise(
        self, table_pk: UUID, *, config_id: UUID | None = None
    ) -> Any:
        if config_id is None:
            config = await self._get_active_feishu_config_or_raise()
            config_id = config.id
        try:
            table = await self.repo.get_feishu_table_by_id(table_pk, config_id)
        except SQLAlchemyError as exc:
            raise AppException(
                status_code=500,
                message=(
                    "仓储飞书表目录不可用，请先执行数据库迁移：alembic upgrade head"
                ),
                detail=exc.__class__.__name__,
            ) from exc
        if not table:
            raise AppException(message="仓储飞书数据表不存在")
        return table

    def _build_feishu_client(
        self, config: Any, app_token: str
    ) -> WarehouseFeishuClient:
        return WarehouseFeishuClient(
            app_id=config.app_id,
            app_secret=decrypt_secret(config.encrypted_app_secret),
            app_token=app_token,
        )

    async def _test_tenant_token(
        self,
        config: Any,
        steps: list[WarehouseFeishuConnectivityStep],
    ) -> str | None:
        if not config.app_id or not config.encrypted_app_secret:
            steps.append(
                WarehouseFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message="App ID 或 App Secret 未配置",
                )
            )
            return None
        try:
            token = await self._build_feishu_client(
                config, ""
            ).get_tenant_access_token()
        except Exception as exc:
            steps.append(
                WarehouseFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message=f"飞书认证失败：{exc}",
                )
            )
            return None
        steps.append(
            WarehouseFeishuConnectivityStep(
                name="应用凭证",
                status="ok",
                message="tenant_access_token 获取成功",
            )
        )
        return token

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _field_from_raw(item: dict[str, Any]) -> WarehouseFeishuFieldResponse:
        field_id = str(item.get("field_id") or item.get("id") or "")
        field_name = str(item.get("field_name") or item.get("name") or field_id)
        return WarehouseFeishuFieldResponse(
            field_id=field_id,
            field_name=field_name,
            type=WarehouseService._safe_int(item.get("type")),
            property=(
                item.get("property") if isinstance(item.get("property"), dict) else None
            ),
        )

    @staticmethod
    def _record_from_raw(item: dict[str, Any]) -> WarehouseFeishuRawRecordResponse:
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        return WarehouseFeishuRawRecordResponse(
            record_id=str(item.get("record_id") or ""),
            fields=fields,
            created_time=WarehouseService._safe_int(item.get("created_time")),
            last_modified_time=WarehouseService._safe_int(
                item.get("last_modified_time")
            ),
        )

    @staticmethod
    def _build_search_text(value: Any) -> str:
        parts: list[str] = []

        def walk(raw: Any) -> None:
            if raw is None:
                return
            if isinstance(raw, str):
                if raw.strip():
                    parts.append(raw.strip())
            elif isinstance(raw, (int, float, bool)):
                parts.append(str(raw))
            elif isinstance(raw, list):
                for item in raw:
                    walk(item)
            elif isinstance(raw, dict):
                for key, item in raw.items():
                    parts.append(str(key))
                    walk(item)

        walk(value)
        return " ".join(parts)[:20_000]

    @staticmethod
    def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
        """Expose stable scalar values while retaining nested structure."""

        def scalar(value: Any, depth: int = 0) -> Any:
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if depth >= 4:
                return json.dumps(value, ensure_ascii=False, default=str)[:2000]
            if isinstance(value, list):
                return [scalar(item, depth + 1) for item in value]
            if isinstance(value, dict):
                for key in ("value", "text", "name", "title", "number", "amount"):
                    if key in value:
                        return scalar(value[key], depth + 1)
                return {key: scalar(item, depth + 1) for key, item in value.items()}
            return str(value)

        return {name: scalar(value) for name, value in fields.items()}

    async def _read_all_records(
        self, client: Any, table_id: str
    ) -> tuple[list[dict[str, Any]], int | None]:
        records: list[dict[str, Any]] = []
        page_token: str | None = None
        expected_total: int | None = None
        page_size = 500
        while True:
            try:
                data = await client.search_records(
                    table_id, page_size=page_size, page_token=page_token
                )
            except Exception:
                if page_size > 100:
                    page_size = 200 if page_size == 500 else 100
                    records = []
                    page_token = None
                    expected_total = None
                    continue
                raise
            records.extend(data.get("items") or [])
            if data.get("total") is not None:
                expected_total = int(data["total"])
            if not data.get("has_more"):
                break
            page_token = str(data.get("page_token") or "")
            if not page_token:
                raise AppException(
                    message="飞书分页链不完整：has_more=true 但缺少 page_token"
                )
        return records, expected_total

    @staticmethod
    def _to_feishu_config_response(config: Any) -> Any:
        from app.modules.warehouse.schemas import WarehouseFeishuConfigResponse

        return WarehouseFeishuConfigResponse(
            id=config.id,
            config_name=config.config_name,
            app_id=config.app_id,
            timezone=config.timezone,
            daily_sync_time=config.daily_sync_time,
            is_active=config.is_active,
            remark=config.remark,
            app_secret_configured=bool(config.encrypted_app_secret),
            app_secret_masked="****" if config.encrypted_app_secret else "",
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    async def _after_feishu_config_saved(self, config: Any) -> None:
        # 凭证变更后清空模块同步客户端缓存，确保新凭证立即生效
        _MATERIAL_SYNC_CLIENTS.clear()
        if config.is_active:
            try:
                from app.modules.warehouse.ws_client import restart_ws_from_db

                await restart_ws_from_db()
            except Exception:
                logger.exception("warehouse Feishu WebSocket restart failed")
            return
        from app.modules.warehouse.ws_client import stop_ws

        await stop_ws()

    async def save_feishu_config(self, data: Any) -> Any:
        existing = await self.repo.get_any_feishu_config()
        if existing:
            existing.config_name = data.config_name
            existing.app_id = data.app_id
            if data.app_secret:
                existing.encrypted_app_secret = encrypt_secret(data.app_secret)
            existing.is_active = data.is_active
            existing.timezone = data.timezone
            existing.daily_sync_time = data.daily_sync_time
            existing.remark = data.remark
            await self.repo.session.flush()
            await self.repo.session.refresh(existing)
            await self.repo.session.commit()
            await self._after_feishu_config_saved(existing)
            return self._to_feishu_config_response(existing)

        if not data.app_secret:
            raise AppException(message="首次保存飞书配置时必须填写 App Secret")
        config = WarehouseFeishuConfig(
            config_name=data.config_name,
            app_id=data.app_id,
            encrypted_app_secret=encrypt_secret(data.app_secret),
            is_active=data.is_active,
            timezone=data.timezone,
            daily_sync_time=data.daily_sync_time,
            remark=data.remark,
        )
        await self.repo.save_feishu_config(config)
        await self.repo.session.refresh(config)
        await self.repo.session.commit()
        await self._after_feishu_config_saved(config)
        return self._to_feishu_config_response(config)

    @staticmethod
    def _exception_message(exc: Exception) -> str:
        message = getattr(exc, "message", None)
        return message if isinstance(message, str) and message else str(exc)

    async def discover_feishu_source_root(self, root_id: UUID) -> list[Any]:
        config = await self.repo.get_active_feishu_config()
        root = await self.repo.get_feishu_source_root(root_id)
        if (
            config is None
            or root is None
            or root.config_id != config.id
            or not root.is_active
        ):
            raise AppException(message="飞书数据入口不存在", status_code=404)
        root.discovery_status = "discovering"
        root.discovery_error = None
        await self.repo.session.commit()
        try:
            if root.source_type == "base":
                client = self._build_feishu_client(config, root.root_token)
                raw_tables = await client.list_tables(page_size=100)
                return await self._save_discovered_feishu_tables(
                    root.root_token,
                    raw_tables,
                    source_root_id=root.id,
                    source_path=[{"token": root.root_token, "title": root.name}],
                )
            client = self._build_feishu_client(config, root.root_token)
            await client.discover_wiki_bases(root.root_token)
            return []
        except Exception as exc:
            await self.repo.session.rollback()
            root = await self.repo.get_feishu_source_root(root_id)
            if root:
                root.discovery_status = "failed"
                root.discovery_error = "飞书数据入口发现失败，请检查配置和入口权限"
                await self.repo.session.commit()
            if isinstance(exc, AppException):
                raise
            raise AppException(
                message="飞书数据入口发现失败，请检查配置和入口权限"
            ) from exc

    async def _sync_feishu_table(
        self, config: Any, table: Any, *, trigger_type: str = "manual"
    ) -> Any:
        table_pk = table.id
        table.sync_status = "syncing"
        table.sync_error = None
        await self.repo.session.commit()
        try:
            return await asyncio.wait_for(
                self._sync_feishu_table_snapshot(
                    config, table, trigger_type=trigger_type
                ),
                timeout=WAREHOUSE_FEISHU_TABLE_SYNC_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            await self.repo.session.rollback()
            if table_pk:
                table = await self._get_table_by_id_or_raise(table_pk)
            table.sync_status = "failed"
            table.sync_error = (
                "同步超过 "
                f"{WAREHOUSE_FEISHU_TABLE_SYNC_TIMEOUT_SECONDS:g} 秒未完成，"
                "已自动标记失败"
            )
            if table_pk:
                await self.repo.fail_running_sync_runs(
                    table_pk,
                    error_message=table.sync_error,
                    completed_at=datetime.now(UTC),
                )
            await self.repo.session.commit()
            raise AppException(message=table.sync_error) from exc

    async def _sync_feishu_table_snapshot(
        self, config: Any, table: Any, *, trigger_type: str = "manual"
    ) -> Any:
        """Refresh the former table-directory compatibility record.

        The migrated material-page mirror remains the source of truth for page
        reads.  This method keeps the old table sync contract useful for Agent
        callers that still address a discovered app/table pair directly.
        """

        del trigger_type  # retained for the legacy call signature
        client = self._build_feishu_client(config, table.app_token)
        fields = await client.list_fields(table.table_id, page_size=100)
        records, expected_total = await self._read_all_records(client, table.table_id)
        table.field_count = len(fields)
        table.record_count = (
            expected_total if expected_total is not None else len(records)
        )
        table.last_synced_at = datetime.now(UTC)
        table.sync_status = "success"
        table.sync_error = None
        table.active_mirror_version = hashlib.sha256(
            json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode(
                "utf-8"
            )
        ).hexdigest()
        await self.repo.session.commit()

        from app.modules.warehouse.schemas import WarehouseFeishuTableSyncResult

        return WarehouseFeishuTableSyncResult(
            table=self._table_response_from_legacy(table),
            field_count=len(fields),
            record_count=table.record_count,
        )

    @staticmethod
    def _table_response_from_legacy(table: Any) -> Any:
        from app.modules.warehouse.schemas import WarehouseFeishuTableResponse

        return WarehouseFeishuTableResponse.model_validate(table)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if isinstance(value, dict):
            value = value.get("value")
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def _prepare_analysis_input(
        self, profile: Any, tables: list[Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        selected: list[dict[str, Any]] = []
        numeric_values: dict[str, list[float]] = {
            item: [] for item in profile.metric_field_ids
        }
        total_rows = 0
        missing_cells = 0
        per_table_limit = max(20, profile.max_raw_rows // max(len(tables), 1))
        for table in tables:
            fields = await self.repo.list_feishu_fields(
                table.business_domain, table.app_token, table.table_id
            )
            names_by_id = {item.field_id: item.field_name for item in fields}
            allowed_names = {
                field_id: names_by_id[field_id]
                for field_id in profile.input_field_ids
                if field_id in names_by_id
            }
            records = await self.repo.list_analysis_records(table, per_table_limit)
            total_rows += table.record_count
            for record in records:
                row: dict[str, Any] = {
                    "resource_id": str(table.id),
                    "record_id": record.record_id,
                }
                for field_id, name in allowed_names.items():
                    if CREDENTIAL_FIELD_PATTERN.search(name):
                        continue
                    value = record.fields.get(name)
                    if value in (None, "", []):
                        missing_cells += 1
                    if (
                        PERSONAL_FIELD_PATTERN.search(name)
                        and not profile.allow_sensitive_fields
                    ):
                        value = "***"
                    row[field_id] = value
                    if field_id in numeric_values:
                        number = self._safe_float(value)
                        if number is not None:
                            numeric_values[field_id].append(number)
                selected.append(row)
        selected = selected[: profile.max_raw_rows]
        while (
            selected
            and len(json.dumps(selected, ensure_ascii=False, default=str))
            > MAX_ANALYSIS_INPUT_CHARS
        ):
            selected.pop()
        numeric_summary = {
            field_id: {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": statistics.fmean(values),
                "median": statistics.median(values),
            }
            for field_id, values in numeric_values.items()
            if values
        }
        algorithm = {
            "source_row_count": total_rows,
            "sample_row_count": len(selected),
            "missing_cell_count": missing_cells,
            "numeric_summary": numeric_summary,
        }
        return algorithm, [], selected

    @staticmethod
    def _legacy_table_uuid(table_id: str) -> UUID:
        """Stable UUID for the former local table-directory contract."""

        return uuid5(NAMESPACE_URL, f"dazah:warehouse:table:{table_id}")

    async def list_feishu_tables(self, *, keyword: str | None = None) -> list[Any]:
        """Expose material-page configs through the former Agent table DTO."""

        from app.modules.warehouse.schemas import WarehouseFeishuTableResponse

        configs = await self.get_all_page_feishu_configs()
        normalized = (keyword or "").strip().lower()
        return [
            WarehouseFeishuTableResponse(
                id=self._legacy_table_uuid(item["table_id"]),
                app_token=item["app_token"],
                table_id=item["table_id"],
                name=item["table_name"],
                last_synced_at=None,
                sync_status="available",
            )
            for item in configs
            if not normalized
            or normalized in str(item.get("table_name", "")).lower()
            or normalized in str(item.get("page_key", "")).lower()
        ]

    async def _legacy_page_key(self, table_pk: UUID) -> str:
        configs = await self.get_all_page_feishu_configs()
        for item in configs:
            if self._legacy_table_uuid(item["table_id"]) == table_pk:
                return str(item["page_key"])
        raise HTTPException(status_code=404, detail="仓储飞书数据表不存在")

    async def sync_feishu_table(
        self, table_pk: UUID, *, trigger_type: str = "manual"
    ) -> Any:
        """Sync one legacy table identifier using the migrated page mirror."""

        from app.modules.warehouse.schemas import WarehouseFeishuTableSyncResult

        page_key = await self._legacy_page_key(table_pk)
        page = await self.sync_material_page_to_local(page_key)
        table = next(
            item for item in await self.list_feishu_tables() if item.id == table_pk
        )
        table.last_synced_at = page.last_sync_time
        table.sync_status = "success"
        table.record_count = page.total
        table.field_count = len(page.columns)
        return WarehouseFeishuTableSyncResult(
            table=table,
            field_count=len(page.columns),
            record_count=page.total,
        )

    async def get_feishu_table_records(
        self,
        table_pk: UUID,
        *,
        keyword: str | None = None,
        field: str | None = None,
        field_operator: str | None = None,
        field_value: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Any:
        from app.modules.warehouse.schemas import (
            WarehouseFeishuFieldResponse,
            WarehouseFeishuRawRecordData,
            WarehouseFeishuRawRecordResponse,
        )

        page_key = await self._legacy_page_key(table_pk)
        result = await self.get_feishu_material_page(
            page_key,
            page=page,
            page_size=page_size,
            keyword=keyword,
            source="local",
        )
        records = []
        for row in result.rows:
            record_id = str(row.get("__record_id") or "")
            records.append(
                WarehouseFeishuRawRecordResponse(
                    record_id=record_id,
                    fields={
                        key: value for key, value in row.items() if key != "__record_id"
                    },
                )
            )
        fields = [
            WarehouseFeishuFieldResponse(
                field_id=column.key,
                field_name=column.title,
                type=column.field_type,
                display_order=index,
            )
            for index, column in enumerate(result.columns)
        ]
        table = next(
            (item for item in await self.list_feishu_tables() if item.id == table_pk),
            None,
        )
        return WarehouseFeishuRawRecordData(
            table=table,
            fields=fields,
            records=records,
            page=result.page,
            page_size=result.page_size,
            total=result.total,
        )

    async def handle_feishu_bitable_record_changed(
        self,
        *,
        file_token: str,
        table_id: str,
        revision: int | None,
        update_time: int | None,
        actions: list[dict[str, str | None]],
    ) -> dict[str, str | bool | None]:
        """Refresh the matching migrated material page after a WS event."""

        for page_key, page_config in FEISHU_WAREHOUSE_MATERIAL_PAGES.items():
            if page_config.table_id == table_id and page_config.app_token == file_token:
                try:
                    await self.sync_material_page_to_local(page_key)
                except Exception:
                    logger.exception("warehouse page WS refresh failed: %s", page_key)
                    return {
                        "matched": True,
                        "status": "error",
                        "error": "仓储页面同步失败，请稍后重试",
                    }
                return {"matched": True, "status": "synced", "table_kind": page_key}
        return {"matched": False, "status": "ignored"}

    # ── Former warehouse settings/page-data/analysis contract ───────────

    async def get_feishu_config_response(self) -> Any:
        """Return the configured app without ever returning the app secret."""
        from app.modules.warehouse.schemas import WarehouseFeishuConfigResponse

        config = await self._get_any_feishu_config_or_raise()
        if config is None:
            return WarehouseFeishuConfigResponse(
                config_name="仓储飞书配置",
                app_id="",
                is_active=False,
                timezone="Asia/Shanghai",
                daily_sync_time="02:00",
                app_secret_configured=False,
            )
        return self._to_feishu_config_response(config)

    async def test_feishu_connectivity(self, payload: Any | None = None) -> Any:
        """Test credentials with sanitized, step-by-step results.

        The provider error is logged for operators but never returned to the
        browser.  This keeps the old settings page useful while preserving the
        platform's secret and provider-response boundary.
        """
        from app.modules.warehouse.schemas import (
            WarehouseFeishuConnectivityResult,
            WarehouseFeishuConnectivityStep,
        )

        steps: list[WarehouseFeishuConnectivityStep] = []
        config = await self._get_any_feishu_config_or_raise()
        app_id = str(
            getattr(payload, "app_id", "") or (config.app_id if config else "")
        )
        app_secret = str(getattr(payload, "app_secret", "") or "")
        if not app_secret and config and config.encrypted_app_secret:
            try:
                app_secret = decrypt_secret(config.encrypted_app_secret)
            except Exception:
                logger.exception("warehouse Feishu secret decrypt failed")
                app_secret = ""

        if not app_id or not app_secret:
            steps.append(
                WarehouseFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message="App ID 或 App Secret 未配置",
                )
            )
            return WarehouseFeishuConnectivityResult(ok=False, steps=steps)

        try:
            client = WarehouseFeishuClient(
                app_id=app_id,
                app_secret=app_secret,
                app_token="",
            )
            await asyncio.wait_for(client.get_tenant_access_token(), timeout=15)
        except TimeoutError:
            logger.warning("warehouse Feishu connectivity test timed out")
            steps.append(
                WarehouseFeishuConnectivityStep(
                    name="应用凭证", status="error", message="飞书认证超时，请稍后重试"
                )
            )
            return WarehouseFeishuConnectivityResult(ok=False, steps=steps)
        except Exception:
            logger.exception("warehouse Feishu connectivity test failed")
            steps.append(
                WarehouseFeishuConnectivityStep(
                    name="应用凭证",
                    status="error",
                    message="飞书认证失败，请检查应用凭据",
                )
            )
            return WarehouseFeishuConnectivityResult(ok=False, steps=steps)

        steps.append(
            WarehouseFeishuConnectivityStep(
                name="应用凭证", status="ok", message="飞书认证成功"
            )
        )
        return WarehouseFeishuConnectivityResult(ok=True, steps=steps)

    async def list_feishu_source_roots(self) -> list[Any]:
        from app.modules.warehouse.schemas import WarehouseFeishuSourceRootResponse

        config = await self._get_any_feishu_config_or_raise()
        if config is None:
            return []
        roots = await self.repo.list_feishu_source_roots(config.id)
        return [
            WarehouseFeishuSourceRootResponse.model_validate(root) for root in roots
        ]

    async def create_feishu_source_root(self, data: Any) -> Any:
        from app.modules.warehouse.schemas import WarehouseFeishuSourceRootResponse

        config = await self._get_active_feishu_config_or_raise()
        try:
            root_token = parse_feishu_root_token(data.source_url, data.source_type)
        except ValueError as exc:
            raise AppException(
                status_code=422, message="飞书入口链接或 Token 无效"
            ) from exc

        for existing in await self.repo.list_feishu_source_roots(config.id):
            if existing.root_token == root_token:
                raise AppException(status_code=409, message="该飞书入口已存在")

        root = WarehouseFeishuSourceRoot(
            config_id=config.id,
            name=data.name.strip(),
            source_type=data.source_type,
            source_url=data.source_url.strip(),
            root_token=root_token,
            is_active=data.is_active,
            discovery_status="pending",
        )
        await self.repo.save_feishu_source_root(root)
        await self.repo.session.commit()
        await self.repo.session.refresh(root)
        return WarehouseFeishuSourceRootResponse.model_validate(root)

    async def delete_feishu_source_root(self, root_id: UUID) -> dict[str, Any]:
        config = await self._get_any_feishu_config_or_raise()
        root = await self.repo.get_feishu_source_root(root_id)
        if config is None or root is None or root.config_id != config.id:
            raise AppException(status_code=404, message="飞书数据入口不存在")
        root.is_active = False
        root.is_deleted = True
        await self.repo.session.commit()
        return {"deleted": True, "root_id": str(root_id)}

    async def _save_discovered_feishu_tables(
        self,
        root_token: str,
        raw_tables: list[dict[str, Any]],
        *,
        source_root_id: UUID,
        source_path: list[dict[str, str]],
    ) -> list[Any]:
        """Store the legacy directory metadata for discovered Base tables."""
        from app.modules.warehouse.schemas import WarehouseFeishuTableResponse

        root = await self.repo.get_feishu_source_root(source_root_id)
        if root is None:
            raise AppException(status_code=404, message="飞书数据入口不存在")
        discovered: list[Any] = []
        for item in raw_tables:
            table_id = str(item.get("table_id") or item.get("id") or "").strip()
            if not table_id:
                continue
            name = str(item.get("name") or item.get("table_name") or table_id).strip()
            revision = self._safe_int(item.get("revision"))
            table = await self.repo.upsert_feishu_table(
                source_root_id=source_root_id,
                business_domain="warehouse",
                app_token=root_token,
                table_id=table_id,
                name=name,
                revision=revision,
                source_path=source_path,
            )
            discovered.append(WarehouseFeishuTableResponse.model_validate(table))
        root.discovery_status = "success"
        root.discovery_error = None
        root.last_discovered_at = datetime.now(UTC)
        await self.repo.session.commit()
        return discovered

    @staticmethod
    def _validate_warehouse_page_key(page_key: str) -> None:
        if page_key not in FEISHU_WAREHOUSE_MATERIAL_PAGES:
            raise AppException(status_code=404, message="仓储页面不存在")

    async def _legacy_table_configs(self) -> list[dict[str, Any]]:
        return await self.get_all_page_feishu_configs()

    async def _page_binding_response(
        self,
        page_key: str,
        binding: WarehouseFeishuPageBinding | None = None,
    ) -> Any:
        from app.modules.warehouse.schemas import (
            WarehouseFeishuPageBindingResponse,
            WarehouseFeishuTableResponse,
        )

        self._validate_warehouse_page_key(page_key)
        configs = await self._legacy_table_configs()
        config = next((item for item in configs if item["page_key"] == page_key), None)
        if binding is not None:
            config = next(
                (
                    item
                    for item in configs
                    if self._legacy_table_uuid(item["table_id"]) == binding.table_pk
                ),
                config,
            )
        if config is None:
            raise AppException(status_code=404, message="仓储页面数据表不存在")

        table = WarehouseFeishuTableResponse(
            id=self._legacy_table_uuid(config["table_id"]),
            app_token=config["app_token"],
            table_id=config["table_id"],
            name=config["table_name"],
            sync_status="available",
        )
        return WarehouseFeishuPageBindingResponse(
            id=binding.id if binding is not None else table.id,
            page_key=page_key,
            table_pk=table.id,
            tab_label=(binding.tab_label if binding is not None else table.name),
            display_order=(binding.display_order if binding is not None else 0),
            is_default=(binding.is_default if binding is not None else True),
            visible_field_ids=(
                binding.visible_field_ids if binding is not None else []
            ),
            default_sort=(binding.default_sort if binding is not None else []),
            history_mode=(
                binding.history_mode if binding is not None else "current_mirror"
            ),
            is_enabled=(binding.is_enabled if binding is not None else True),
            status=(binding.status if binding is not None else "published"),
            table=table,
        )

    async def get_page_data(self, page_key: str) -> Any:
        from app.modules.warehouse.schemas import WarehouseFeishuPageDataResponse

        self._validate_warehouse_page_key(page_key)
        config = await self._get_any_feishu_config_or_raise()
        bindings: list[Any] = []
        if config is not None:
            try:
                stored = await self.repo.list_page_bindings(config.id, page_key)
            except SQLAlchemyError:
                logger.exception("warehouse page binding table is unavailable")
                stored = []
            for binding in stored:
                try:
                    bindings.append(
                        await self._page_binding_response(page_key, binding)
                    )
                except AppException:
                    logger.warning(
                        "ignoring stale warehouse page binding: %s", binding.id
                    )
        # 对齐 energy 契约：未发布绑定时返回空列表，
        # 前端映射门据此原样渲染 legacy 页面（不再合成默认绑定，
        # 避免仅打开页面就使通用映射表格接管台账页）。
        return WarehouseFeishuPageDataResponse(page_key=page_key, bindings=bindings)

    async def replace_page_bindings(self, page_key: str, data: Any) -> Any:

        self._validate_warehouse_page_key(page_key)
        await self._get_active_feishu_config_or_raise()
        inputs = list(data.bindings)
        if len({item.table_pk for item in inputs}) != len(inputs):
            raise AppException(
                status_code=422, message="页面映射不能重复选择同一数据表"
            )

        configs = await self._legacy_table_configs()
        valid_ids = {
            self._legacy_table_uuid(item["table_id"]): item for item in configs
        }
        unknown = [item.table_pk for item in inputs if item.table_pk not in valid_ids]
        if unknown:
            raise AppException(status_code=404, message="页面映射的数据表不存在")

        rows = [
            WarehouseFeishuPageBinding(
                page_key=page_key,
                table_pk=item.table_pk,
                tab_label=item.tab_label.strip(),
                display_order=item.display_order,
                is_default=item.is_default,
                visible_field_ids=item.visible_field_ids,
                default_sort=item.default_sort,
                history_mode=item.history_mode,
                status="published",
                is_enabled=item.is_enabled,
            )
            for item in inputs
        ]
        await self.repo.replace_page_bindings(page_key, rows)
        await self.repo.session.commit()
        await self.repo.session.refresh(rows[0]) if rows else None
        return await self.get_page_data(page_key)

    async def _page_key_for_binding(self, binding_id: UUID) -> str:
        configs = await self._legacy_table_configs()
        for item in configs:
            if self._legacy_table_uuid(item["table_id"]) == binding_id:
                return str(item["page_key"])
        config = await self._get_any_feishu_config_or_raise()
        if config is not None:
            binding = await self.repo.get_page_binding_by_id(config.id, binding_id)
            if binding is not None:
                return binding.page_key
        raise AppException(status_code=404, message="仓储页面映射不存在")

    async def _binding_for_page(self, page_key: str, binding_id: UUID) -> Any:
        config = await self._get_any_feishu_config_or_raise()
        if config is not None:
            stored = await self.repo.get_page_binding(config.id, page_key, binding_id)
            if stored is not None:
                return await self._page_binding_response(page_key, stored)
        synthetic = await self._page_binding_response(page_key)
        if synthetic.id != binding_id:
            raise AppException(status_code=404, message="仓储页面映射不存在")
        return synthetic

    @staticmethod
    def _matches_dataset_filter(value: Any, operator: str, expected: str) -> bool:
        actual = WarehouseService._build_search_text(value).lower()
        target = expected.strip().lower()
        if operator == "contains":
            return target in actual
        if operator == "eq":
            return actual == target
        if operator == "ne":
            return actual != target
        try:
            actual_number = float(actual)
            target_number = float(target)
        except (TypeError, ValueError):
            return False
        return {
            "gt": actual_number > target_number,
            "gte": actual_number >= target_number,
            "lt": actual_number < target_number,
            "lte": actual_number <= target_number,
        }.get(operator, False)

    async def get_page_dataset(
        self,
        page_key: str,
        binding_id: UUID,
        *,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
        filter_fields: list[str] | None = None,
        filter_operators: list[str] | None = None,
        filter_values: list[str] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
    ) -> Any:
        from app.modules.warehouse.schemas import (
            WarehouseDatasetPagination,
            WarehouseDatasetRecordResponse,
            WarehouseDatasetResponse,
            WarehouseFeishuFieldResponse,
        )

        binding = await self._binding_for_page(page_key, binding_id)
        result = await self.get_feishu_material_page(
            page_key,
            page=1,
            page_size=1000,
            keyword=keyword,
            source="local",
        )
        rows = list(result.rows)
        filters = list(
            zip(
                filter_fields or [],
                filter_operators or [],
                filter_values or [],
            )
        )
        if filters:
            rows = [
                row
                for row in rows
                if all(
                    self._matches_dataset_filter(row.get(field), operator, value)
                    for field, operator, value in filters
                )
            ]
        if sort_field:
            rows.sort(
                key=lambda row: self._build_search_text(row.get(sort_field)).lower(),
                reverse=sort_direction == "desc",
            )

        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        fields = [
            WarehouseFeishuFieldResponse(
                field_id=column.key,
                field_name=column.title,
                type=column.field_type,
                display_order=index,
            )
            for index, column in enumerate(result.columns)
            if not binding.visible_field_ids or column.key in binding.visible_field_ids
        ]
        records = [
            WarehouseDatasetRecordResponse(
                record_id=str(row.get("__record_id") or ""),
                fields={
                    key: value for key, value in row.items() if key != "__record_id"
                },
            )
            for row in page_rows
        ]
        return WarehouseDatasetResponse(
            dataset=binding,
            fields=fields,
            records=records,
            pagination=WarehouseDatasetPagination(
                page=page, page_size=page_size, total=total
            ),
        )

    async def get_page_field_values(
        self, page_key: str, binding_id: UUID, field_id: str
    ) -> Any:
        from app.modules.warehouse.schemas import (
            WarehouseFieldValueItem,
            WarehouseFieldValuesResponse,
        )

        dataset = await self.get_page_dataset(
            page_key, binding_id, page=1, page_size=1000
        )
        counts: dict[str, int] = {}
        for record in dataset.records:
            value = record.fields.get(field_id)
            text = self._build_search_text(value).strip()
            if text:
                counts[text] = counts.get(text, 0) + 1
        return WarehouseFieldValuesResponse(
            field_id=field_id,
            values=[
                WarehouseFieldValueItem(value=value, count=count)
                for value, count in sorted(
                    counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        )

    async def get_page_record(
        self, page_key: str, binding_id: UUID, record_id: str
    ) -> Any:
        dataset = await self.get_page_dataset(
            page_key, binding_id, page=1, page_size=1000
        )
        for record in dataset.records:
            if record.record_id == record_id:
                return record
        raise AppException(status_code=404, message="仓储记录不存在")

    @staticmethod
    def _value_contains_token(value: Any, token: str) -> bool:
        if isinstance(value, str):
            return value == token
        if isinstance(value, list):
            return any(
                WarehouseService._value_contains_token(item, token) for item in value
            )
        if isinstance(value, dict):
            return any(
                WarehouseService._value_contains_token(item, token)
                for item in value.values()
            )
        return False

    async def download_page_attachment(
        self,
        page_key: str,
        binding_id: UUID,
        record_id: str,
        field_id: str,
        file_token: str,
    ) -> tuple[bytes, str, str | None]:
        if (
            not file_token
            or len(file_token) > 512
            or any(ord(char) < 32 for char in file_token)
        ):
            raise AppException(status_code=422, message="附件 Token 无效")
        record = await self.get_page_record(page_key, binding_id, record_id)
        value = record.fields.get(field_id)
        if value is None:
            raise AppException(status_code=404, message="附件字段不存在")
        if not self._value_contains_token(value, file_token):
            raise AppException(status_code=403, message="无权访问该附件")
        config = await self._get_active_feishu_config_or_raise()
        page_config = await self._get_material_page_config(page_key)
        client = self._build_feishu_client(config, page_config.app_token)
        try:
            return await client.download_media(file_token)
        except Exception as exc:
            logger.exception("warehouse attachment download failed")
            raise AppException(
                status_code=502, message="附件下载失败，请稍后重试"
            ) from exc

    async def aggregate_page_dataset(self, query: Any) -> Any:
        from app.modules.warehouse.schemas import WarehouseAnalyticsResponse

        page_key = await self._page_key_for_binding(query.binding_id)
        dataset = await self.get_page_dataset(
            page_key, query.binding_id, page=1, page_size=1000
        )
        groups: dict[str, list[float]] = {}
        group_field = query.group_field_id
        for record in dataset.records:
            group = (
                self._build_search_text(record.fields.get(group_field)).strip()
                if group_field
                else "全部"
            )
            if not group:
                group = "（空）"
            value = (
                record.fields.get(query.metric_field_id) if query.metric_field_id else 1
            )
            number = self._safe_float(value)
            groups.setdefault(group, []).append(number if number is not None else 0.0)

        rows: list[dict[str, Any]] = []
        for group, values in list(groups.items())[: query.limit]:
            if query.metric == "count":
                metric_value: float | int = len(values)
            elif query.metric == "count_distinct":
                metric_value = len({str(value) for value in values})
            elif query.metric == "sum":
                metric_value = sum(values)
            elif query.metric == "avg":
                metric_value = sum(values) / len(values) if values else 0
            elif query.metric == "min":
                metric_value = min(values) if values else 0
            else:
                metric_value = max(values) if values else 0
            rows.append({"group": group, "value": metric_value})
        return WarehouseAnalyticsResponse(
            rows=rows,
            meta={
                "binding_id": str(query.binding_id),
                "total_rows": len(dataset.records),
            },
        )

    @staticmethod
    def _analysis_profile_response(profile: Any, prompt_version: int) -> Any:
        from app.modules.warehouse.schemas import WarehouseAnalysisProfileResponse

        return WarehouseAnalysisProfileResponse(
            id=profile.id,
            name=profile.name,
            resource_ids=[str(item) for item in profile.resource_ids],
            analysis_goal=profile.analysis_goal,
            input_field_ids=profile.input_field_ids,
            time_field_id=profile.time_field_id,
            metric_field_ids=profile.metric_field_ids,
            dimension_field_ids=profile.dimension_field_ids,
            max_raw_rows=profile.max_raw_rows,
            auto_run=profile.auto_run,
            allow_sensitive_fields=profile.allow_sensitive_fields,
            prompt_version=prompt_version,
        )

    @staticmethod
    def _analysis_prompt_response(prompt: Any) -> Any:
        from app.modules.warehouse.schemas import WarehousePromptVersionResponse

        return WarehousePromptVersionResponse(
            id=prompt.id,
            profile_id=prompt.profile_id,
            version=prompt.version,
            system_prompt=prompt.system_prompt,
            business_context=prompt.business_context,
            focus_points=prompt.focus_points,
            status=prompt.status,
            published_at=prompt.published_at,
        )

    async def create_analysis_profile(self, data: Any) -> Any:
        profile = WarehouseFeishuAnalysisProfile(
            name=data.name.strip(),
            resource_ids=[str(item) for item in data.resource_ids],
            analysis_goal=data.analysis_goal.strip(),
            input_field_ids=data.input_field_ids,
            time_field_id=data.time_field_id,
            metric_field_ids=data.metric_field_ids,
            dimension_field_ids=data.dimension_field_ids,
            quality_rules=data.quality_rules,
            output_schema=data.output_schema,
            max_raw_rows=data.max_raw_rows,
            auto_run=data.auto_run,
            allow_sensitive_fields=data.allow_sensitive_fields,
        )
        await self.repo.save_analysis_profile(profile)
        prompt = WarehouseFeishuPromptVersion(
            profile_id=profile.id,
            version=1,
            system_prompt=data.system_prompt,
            business_context=data.business_context,
            focus_points=data.focus_points,
            status="published",
            published_at=datetime.now(UTC),
        )
        await self.repo.save_prompt_version(prompt)
        profile.published_prompt_version_id = prompt.id
        await self.repo.session.commit()
        return self._analysis_profile_response(profile, prompt.version)

    async def get_analysis_profile(self, profile_id: UUID) -> Any:
        profile = await self.repo.get_analysis_profile(profile_id)
        if profile is None:
            raise AppException(status_code=404, message="分析配置不存在")
        prompts = await self.repo.list_prompt_versions(profile.id)
        published = next((item for item in prompts if item.status == "published"), None)
        return self._analysis_profile_response(
            profile, published.version if published else 0
        )

    async def list_prompt_versions(self, profile_id: UUID) -> list[Any]:
        if await self.repo.get_analysis_profile(profile_id) is None:
            raise AppException(status_code=404, message="分析配置不存在")
        return [
            self._analysis_prompt_response(item)
            for item in await self.repo.list_prompt_versions(profile_id)
        ]

    async def create_prompt_draft(self, profile_id: UUID, data: Any) -> Any:
        if await self.repo.get_analysis_profile(profile_id) is None:
            raise AppException(status_code=404, message="分析配置不存在")
        prompt = WarehouseFeishuPromptVersion(
            profile_id=profile_id,
            version=await self.repo.next_prompt_version(profile_id),
            system_prompt=data.system_prompt,
            business_context=data.business_context,
            focus_points=data.focus_points,
            status="draft",
        )
        await self.repo.save_prompt_version(prompt)
        await self.repo.session.commit()
        return self._analysis_prompt_response(prompt)

    async def publish_prompt_version(self, profile_id: UUID, prompt_id: UUID) -> Any:
        profile = await self.repo.get_analysis_profile(profile_id)
        prompt = await self.repo.get_prompt_version(prompt_id)
        if profile is None or prompt is None or prompt.profile_id != profile_id:
            raise AppException(status_code=404, message="提示词版本不存在")
        prompts = await self.repo.list_prompt_versions(profile_id)
        for item in prompts:
            item.status = "draft"
            item.published_at = None
        prompt.status = "published"
        prompt.published_at = datetime.now(UTC)
        profile.published_prompt_version_id = prompt.id
        await self.repo.session.commit()
        return self._analysis_prompt_response(prompt)

    async def _analysis_run_response(self, run: Any) -> Any:
        from app.modules.warehouse.schemas import WarehouseAnalysisRunResponse

        result = await self.repo.get_analysis_result(run.id)
        result_data = None
        if result is not None:
            result_data = {
                "metrics": result.metrics,
                "risks": result.risks,
                "trends": result.trends,
                "feasibility": result.feasibility,
                "recommendations": result.recommendations,
                "evidence": result.evidence,
                "confidence": result.confidence,
            }
        return WarehouseAnalysisRunResponse(
            id=run.id,
            profile_id=run.profile_id,
            trigger_type=run.trigger_type,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            error_message=run.error_message,
            result=result_data,
        )

    async def enqueue_analysis(
        self, profile_id: UUID, trigger_type: str = "manual"
    ) -> Any:
        profile = await self.repo.get_analysis_profile(profile_id)
        if profile is None:
            raise AppException(status_code=404, message="分析配置不存在")
        prompts = await self.repo.list_prompt_versions(profile_id)
        prompt = next((item for item in prompts if item.status == "published"), None)
        if prompt is None:
            raise AppException(status_code=409, message="请先发布分析提示词")
        run = WarehouseFeishuAnalysisRun(
            profile_id=profile_id,
            prompt_version_id=prompt.id,
            trigger_type=trigger_type,
            source_versions={},
            status="queued",
            started_at=datetime.now(UTC),
        )
        await self.repo.save_analysis_run(run)
        await self.repo.session.commit()
        return await self._analysis_run_response(run)

    async def run_analysis(self, profile_id: UUID, trigger_type: str = "manual") -> Any:
        profile = await self.repo.get_analysis_profile(profile_id)
        if profile is None:
            raise AppException(status_code=404, message="分析配置不存在")
        prompts = await self.repo.list_prompt_versions(profile_id)
        prompt = next((item for item in prompts if item.status == "published"), None)
        if prompt is None:
            raise AppException(status_code=409, message="请先发布分析提示词")
        run = WarehouseFeishuAnalysisRun(
            profile_id=profile_id,
            prompt_version_id=prompt.id,
            trigger_type=trigger_type,
            source_versions={},
            status="running",
            started_at=datetime.now(UTC),
        )
        await self.repo.save_analysis_run(run)
        try:
            sample_count = 0
            for resource_id in profile.resource_ids:
                try:
                    page_key = await self._page_key_for_binding(UUID(str(resource_id)))
                    dataset = await self.get_page_dataset(
                        page_key,
                        UUID(str(resource_id)),
                        page=1,
                        page_size=min(profile.max_raw_rows, 200),
                    )
                    sample_count += len(dataset.records)
                except (AppException, ValueError):
                    continue
            result = WarehouseFeishuAnalysisResult(
                run_id=run.id,
                metrics={
                    "resource_count": len(profile.resource_ids),
                    "sample_row_count": sample_count,
                },
                risks=[],
                trends=[],
                feasibility={"status": "待人工确认"},
                recommendations=[],
                evidence=[],
                confidence=None,
            )
            await self.repo.save_analysis_result(result)
            run.status = "success"
            run.completed_at = datetime.now(UTC)
            await self.repo.session.commit()
        except Exception as exc:
            await self.repo.session.rollback()
            logger.exception("warehouse analysis run failed")
            raise AppException(
                status_code=502, message="仓储分析运行失败，请稍后重试"
            ) from exc
        return await self._analysis_run_response(run)

    async def get_analysis_run_response(self, run_id: UUID) -> Any:
        run = await self.repo.get_analysis_run(run_id)
        if run is None:
            raise AppException(status_code=404, message="分析运行记录不存在")
        return await self._analysis_run_response(run)
