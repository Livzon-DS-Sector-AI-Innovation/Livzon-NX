"""页面飞书多维表格镜像服务。

一个页面（见 ``page_tables.py`` 注册表）绑定一张飞书多维表格，绑定存
``safety.page_feishu_configs``，由「安全飞书设置」页维护。列定义来自飞书
实时 schema，因此这里不写死任何字段名；写操作直接回写飞书表。

读取策略：字段 schema 用 Redis 缓存（表头极少变），记录每次实时拉取，保证
页面与飞书一致；关键字过滤、排序、分页在服务端内存完成（值班隐患这类台账
量级小，一次拉全表，超过上限会提示）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Numeric, and_, case, func, or_, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory as async_session_factory
from app.core.exceptions import AppException
from app.core.redis import (
    acquire_lock,
    cache_delete,
    cache_get,
    cache_set,
    release_lock,
)
from app.core.upload_security import read_upload_secure
from app.modules.safety.feishu.bitable_client import SafetyBitableClient
from app.modules.safety.feishu.field_codec import (
    KIND_ATTACHMENT,
    KIND_CHECKBOX,
    KIND_DATE,
    KIND_MULTI_SELECT,
    KIND_NUMBER,
    KIND_PERSON,
    KIND_SELECT,
    KIND_TEXT,
    FieldCodecError,
    FieldSchema,
    attachment_field_or_error,
    build_field_schema,
    decode_record_fields,
    decode_value,
    encode_record_fields,
    existing_attachment_tokens,
)
from app.modules.safety.feishu.runtime_config import load_safety_feishu_runtime_config
from app.modules.safety.models import (
    SafetyPageFeishuConfig,
    SafetyPageTableMirrorRecord,
    WorkshopClassification,
)
from app.modules.safety.page_tables import (
    PAGE_TABLE_DEFINITIONS,
    PageTableDefinition,
    get_page_table,
)
from app.modules.safety.schemas.page_table import (
    PageFeishuConfigItem,
    PageFeishuConfigListResponse,
    PageFeishuConfigTestResult,
    PageFeishuFieldSummary,
    PageFeishuSubTable,
    PageTableAttachmentItem,
    PageTableAttachmentUploadResponse,
    PageTableColumn,
    PageTableDueSummary,
    PageTableFieldValueCount,
    PageTableFieldValuesResponse,
    PageTableOverLimitFields,
    PageTableRecord,
    PageTableRecordCondition,
    PageTableRecordsResponse,
    PageTableStatBucket,
    PageTableStatGroup,
    PageTableStatsResponse,
    PageTableTab,
    ResolvedFeishuTable,
    ResolvedPageFeishuUrl,
    UpdatePageFeishuConfigRequest,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

# 字段 schema 缓存时长（表头变更极少，缓存可省掉每次请求的飞书往返）
FIELD_CACHE_TTL_SECONDS = 600
# 单次读取的记录上限，超出只返回前 N 条并置 truncated
MAX_RECORDS = 2000
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
# 附件上传限制（与安全模块其它附件入口保持一致）
ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024
ATTACHMENT_ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".txt",
}
_SETTINGS_HINT = (
    "请先在 安全管理 → 系统配置 → 飞书设置 的「页面数据表映射」中配置该页面的多维表格"
)

_WIKI_LINK_RE = re.compile(r"/wiki/([A-Za-z0-9_-]+)")
_BASE_LINK_RE = re.compile(r"/base/([A-Za-z0-9_-]+)")

# ── 仪表盘聚合 ──

# 车间号识别归一：「201-1车间」「201-1」「201一车间」都是同一车间（201一车间）。
# 车间/位置 是自由文本，值班人员会混用连字符、阿拉伯数字与中文数字，
# 还常带楼层/位置后缀（如「201一车间二楼」「102二车间陶瓷膜区域」）。
_WORKSHOP_RE = re.compile(
    r"^(?P<plant>\d{2,4})\s*[-—－–_]?\s*(?P<ordinal>[一二三四五六七八九十\d]+)?\s*(?:车间|工段|工区|区域)?$"
)
_WORKSHOP_PREFIX_RE = re.compile(
    r"^(?P<plant>\d{2,4})\s*[-—－–_]?\s*(?P<ordinal>[一二三四五六七八九十\d]+)?\s*(?:车间|工段|工区)"
)
_CN_DIGIT_VALUES = {
    char: index for index, char in enumerate("零一二三四五六七八九", start=0)
}
_FULLWIDTH_TRANS = str.maketrans(
    "０１２３４５６７８９（）：－—＿　", "0123456789():--_ "
)

# 仪表盘的默认分组维度（前端也可显式传 group_by 覆盖）：
# 日期字段按月、位置类文本字段按车间号、单选字段按选项。
_STATS_LOCATION_NAME_KEYS = ("车间", "位置", "区域", "地点", "工段")
STATS_GROUP_LIMIT = 10
STATS_MONTH_LIMIT = 12
# 筛选下拉框的选项上限（按出现次数取前 N）
MAX_FIELD_VALUES = 200
_UNFILLED_KEY = "（未填写）"
# AI 兜底归类的后台任务状态（进程内防重入；跨实例由 Redis 锁兜底）
_ai_classify_task: asyncio.Task[None] | None = None
_AI_CLASSIFY_LOCK_KEY = "safety:page-table:ai-classify"


def _ordinal_to_cn(ordinal: str) -> str:
    """把车间序号统一为中文数字（"1"→"一"，"11"→"十一"，"二"→"二"）。"""
    if all(char in _CN_DIGIT_VALUES or char == "十" for char in ordinal):
        return ordinal
    try:
        number = int(ordinal)
    except ValueError:
        return ordinal
    if number <= 0:
        return ordinal
    units = "零一二三四五六七八九"
    if number < 10:
        return units[number]
    if number == 10:
        return "十"
    tens, rest = divmod(number, 10)
    prefix = "十" if tens == 1 else f"{units[tens]}十"
    return prefix + (units[rest] if rest else "")


def normalize_workshop_name(
    value: str, aliases: dict[str, str] | None = None
) -> str:
    """把车间位置的自由文本归一为规范车间名。

    匹配顺序（别名映射来自页面配置，均可自行增删）：
    1. 精确命中别名（「DR提炼」「甲类罐区」等）；
    2. 值中包含别名，长别名优先（「201-2多拉车间」含「多拉」、「霉酚酸车间二楼」
       含「霉酚酸」）；
    3. 车间号规则：取「厂房号+序号+车间」段、剥掉楼层/位置后缀
       （「201一车间二楼」→「201一车间」），并做序号中文归一（「201-1」→「201一车间」）；
    4. 归一结果再过一次精确别名（用于把「201二车间」默认落到「201二车间（MC）」、
       「203一/二/三车间」折叠为「203车间」这类按厂房合并的规则）。
    都不匹配的值（如「原料罐区」）原样返回。
    """
    text = (value or "").translate(_FULLWIDTH_TRANS).strip()
    if not text:
        return ""
    if aliases:
        canonical = aliases.get(text)
        if canonical and canonical.strip():
            return canonical.strip()
        # 只有「产线别名」参与包含匹配；键本身是车间名的条目（默认产线、
        # 按厂房合并）留给车间号归一之后的精确别名步骤，避免抢线。
        line_aliases = {
            alias: canonical
            for alias, canonical in aliases.items()
            if _WORKSHOP_RE.match(alias) is None
        }
        for alias in sorted(line_aliases, key=len, reverse=True):
            if alias in text:
                canonical = line_aliases[alias].strip()
                if canonical:
                    return canonical
    match = _WORKSHOP_RE.match(text) or _WORKSHOP_PREFIX_RE.match(text)
    if match is None:
        return text
    plant = match.group("plant")
    ordinal = match.group("ordinal")
    base = f"{plant}车间" if not ordinal else f"{plant}{_ordinal_to_cn(ordinal)}车间"
    if aliases:
        return aliases.get(base, base)
    return base


def _clean(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


# ── 页面与配置 ──


def _require_definition(page_key: str) -> PageTableDefinition:
    definition = get_page_table(page_key)
    if definition is None:
        raise AppException(message="该页面未登记飞书表格镜像能力", status_code=404)
    return definition


async def _get_config_model(
    db: AsyncSession, page_key: str
) -> SafetyPageFeishuConfig | None:
    result = await db.execute(
        select(SafetyPageFeishuConfig)
        .where(
            SafetyPageFeishuConfig.page_key == page_key,
            SafetyPageFeishuConfig.is_deleted.is_(False),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


def _workshop_aliases_of(raw: Any) -> dict[str, str]:
    """读别名映射（模型 JSON 字段或请求值），剔除空白键值。"""
    if not isinstance(raw, dict):
        return {}
    aliases: dict[str, str] = {}
    for alias, canonical in raw.items():
        alias_text = str(alias).strip()
        canonical_text = str(canonical).strip()
        if alias_text and canonical_text:
            aliases[alias_text] = canonical_text
    return aliases


# ── 超储计算（危化品统计表等绑定页的派生标注）──

_NUMBER_RE = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class OverLimitFieldConfig:
    """绑定页配置的超储计算列（存量/上限成对，品名列可选）。"""

    quantity_field: str
    limit_field: str
    name_field: str | None


@dataclass(slots=True)
class MirrorInventoryRow:
    """绑定表格一行按超储列解析后的归一结果（总览卡片/统计共用）。"""

    record_id: str
    name: str
    workshop: str
    quantity: float | None
    upper_limit: float | None
    over_limit: bool = False
    over_pct: float | None = None


def _over_limit_config(model: SafetyPageFeishuConfig) -> OverLimitFieldConfig | None:
    quantity_field = _clean(model.over_limit_quantity_field)
    limit_field = _clean(model.over_limit_limit_field)
    if not quantity_field or not limit_field:
        return None
    return OverLimitFieldConfig(
        quantity_field=quantity_field,
        limit_field=limit_field,
        name_field=_clean(model.over_limit_name_field),
    )


def _parse_field_number(value: Any) -> float | None:
    """从字段值解析数量：兼容数字、带单位文本（“500kg”）、千分位与全角数字。"""
    if value is None or isinstance(value, bool | dict | list):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).translate(_FULLWIDTH_TRANS)
    match = _NUMBER_RE.search(text)
    if match is None:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _row_over_pct(quantity: float, upper_limit: float) -> float | None:
    if upper_limit <= 0:
        return None
    return round((quantity - upper_limit) / upper_limit * 100, 1)


def _annotate_over_limit(
    records: list[PageTableRecord],
    config: OverLimitFieldConfig,
    source_values: dict[str, dict[str, Any]],
) -> None:
    """按配置列给记录打超储标记；数值从原始字段值解析，不受页面隐藏列影响。"""
    for record in records:
        raw_fields = source_values.get(record.record_id)
        if not raw_fields:
            continue
        quantity = _parse_field_number(raw_fields.get(config.quantity_field))
        upper_limit = _parse_field_number(raw_fields.get(config.limit_field))
        if quantity is None or upper_limit is None:
            continue
        if quantity > upper_limit:
            record.over_limit = True
            record.over_pct = _row_over_pct(quantity, upper_limit)
        else:
            record.over_limit = False


def _display_field_text(value: Any) -> str:
    if value is None or isinstance(value, dict | list):
        return ""
    return str(value).strip()


async def collect_mirror_over_limit_rows(
    db: AsyncSession, page_key: str
) -> list[MirrorInventoryRow] | None:
    """读取绑定表格全量行并按超储列解析。

    未绑定、未配置超储列或读取失败时返回 None，调用方回退本地库存口径；
    读取失败会记录 warning 日志（不静默）。
    """
    model = await _get_config_model(db, page_key)
    if model is None or not model.is_enabled:
        return None
    config = _over_limit_config(model)
    if config is None:
        return None
    app_token = _clean(model.app_token)
    table_id = _clean(model.table_id)
    if not app_token or not table_id:
        return None
    try:
        columns = await _load_field_schema(app_token, table_id)
        field_rows: list[tuple[str, dict[str, Any]]] = []
        if model.is_mirrored and model.last_synced_at is not None:
            result = await db.execute(
                select(SafetyPageTableMirrorRecord).where(
                    SafetyPageTableMirrorRecord.page_key == page_key,
                    SafetyPageTableMirrorRecord.table_id == table_id,
                    SafetyPageTableMirrorRecord.is_deleted.is_(False),
                )
            )
            field_rows = [
                (row.record_id, dict(row.fields or {}))
                for row in result.scalars()
            ]
        else:
            raw_rows = await _fetch_raw_records(
                app_token, table_id, fetch_sort_field=None
            )
            field_rows = [
                (
                    str(row.get("record_id") or ""),
                    row_fields if isinstance(row_fields, dict) else {},
                )
                for row in raw_rows
                if row.get("record_id")
                for row_fields in [row.get("fields")]
            ]
    except Exception:
        logger.warning(
            "读取绑定表格超储数据失败，回退本地库存口径: page=%s",
            page_key,
            exc_info=True,
        )
        return None

    name_field = config.name_field or next(
        (field.name for field in columns if field.kind == KIND_TEXT), None
    )
    workshop_field = next(
        (
            field.name
            for field in columns
            if field.kind == KIND_TEXT
            and any(key in field.name for key in _STATS_LOCATION_NAME_KEYS)
        ),
        None,
    )
    rows: list[MirrorInventoryRow] = []
    for record_id, fields in field_rows:
        quantity = _parse_field_number(fields.get(config.quantity_field))
        upper_limit = _parse_field_number(fields.get(config.limit_field))
        row = MirrorInventoryRow(
            record_id=record_id,
            name=_display_field_text(fields.get(name_field)) if name_field else "",
            workshop=(
                _display_field_text(fields.get(workshop_field))
                if workshop_field
                else ""
            ),
            quantity=quantity,
            upper_limit=upper_limit,
        )
        if (
            quantity is not None
            and upper_limit is not None
            and quantity > upper_limit
        ):
            row.over_limit = True
            row.over_pct = _row_over_pct(quantity, upper_limit)
        rows.append(row)
    return rows


def _build_config_item(
    definition: PageTableDefinition,
    model: SafetyPageFeishuConfig | None,
) -> PageFeishuConfigItem:
    if model is None:
        return PageFeishuConfigItem(
            page_key=definition.page_key,
            page_name=definition.page_name,
            route_path=definition.route_path,
        )
    return PageFeishuConfigItem(
        page_key=definition.page_key,
        page_name=definition.page_name,
        route_path=definition.route_path,
        app_token=model.app_token,
        table_id=model.table_id,
        view_id=model.view_id,
        hidden_field_names=list(model.hidden_field_names or []),
        workshop_aliases=_workshop_aliases_of(model.workshop_aliases),
        sub_tables=[
            PageFeishuSubTable(**entry)
            for entry in _clean_sub_tables(model.sub_tables)
        ],
        over_limit_quantity_field=_clean(model.over_limit_quantity_field),
        over_limit_limit_field=_clean(model.over_limit_limit_field),
        over_limit_name_field=_clean(model.over_limit_name_field),
        is_enabled=model.is_enabled,
        is_configured=bool(_clean(model.app_token) and _clean(model.table_id)),
        is_mirrored=model.is_mirrored,
        last_synced_at=model.last_synced_at,
        last_sync_status=model.last_sync_status,
        last_sync_error=model.last_sync_error,
        last_sync_record_count=model.last_sync_record_count,
        last_test_status=model.last_test_status,
        last_test_error=model.last_test_error,
        last_tested_at=model.last_tested_at,
        last_test_field_count=model.last_test_field_count,
        last_test_record_count=model.last_test_record_count,
    )


async def list_page_feishu_configs(
    db: AsyncSession,
) -> PageFeishuConfigListResponse:
    """列出全部镜像页及其绑定（未配置的页面也返回，便于设置页集中维护）。"""
    result = await db.execute(
        select(SafetyPageFeishuConfig).where(
            SafetyPageFeishuConfig.is_deleted.is_(False)
        )
    )
    by_key = {row.page_key: row for row in result.scalars().all()}
    return PageFeishuConfigListResponse(
        items=[
            _build_config_item(definition, by_key.get(definition.page_key))
            for definition in PAGE_TABLE_DEFINITIONS
        ]
    )


async def save_page_feishu_config(
    db: AsyncSession,
    page_key: str,
    data: UpdatePageFeishuConfigRequest,
) -> PageFeishuConfigItem:
    """保存某个页面的多维表格绑定（仅更新请求中显式给出的字段）。"""
    definition = _require_definition(page_key)
    try:
        model = await _get_config_model(db, page_key)
        if model is None:
            model = SafetyPageFeishuConfig(page_key=page_key)
            db.add(model)
        if "app_token" in data.model_fields_set:
            model.app_token = _clean(data.app_token)
        if "table_id" in data.model_fields_set:
            model.table_id = _clean(data.table_id)
        if "view_id" in data.model_fields_set:
            model.view_id = _clean(data.view_id)
        if "hidden_field_names" in data.model_fields_set:
            model.hidden_field_names = [
                str(name).strip()
                for name in (data.hidden_field_names or [])
                if str(name).strip()
            ]
        if "workshop_aliases" in data.model_fields_set:
            model.workshop_aliases = _workshop_aliases_of(data.workshop_aliases)
            logger.info(
                "保存页面车间别名: page=%s 收到 %d 条, 生效 %d 条",
                page_key,
                len(data.workshop_aliases or {}),
                len(model.workshop_aliases or {}),
            )
        if "sub_tables" in data.model_fields_set:
            model.sub_tables = _clean_sub_tables(
                [entry.model_dump() for entry in (data.sub_tables or [])]
            )
        over_limit_touched = any(
            field in data.model_fields_set
            for field in (
                "over_limit_quantity_field",
                "over_limit_limit_field",
                "over_limit_name_field",
            )
        )
        if over_limit_touched:
            quantity_field = _clean(
                data.over_limit_quantity_field
                if "over_limit_quantity_field" in data.model_fields_set
                else model.over_limit_quantity_field
            )
            limit_field = _clean(
                data.over_limit_limit_field
                if "over_limit_limit_field" in data.model_fields_set
                else model.over_limit_limit_field
            )
            if bool(quantity_field) != bool(limit_field):
                raise AppException(
                    message="超储计算的「存量列」与「上限列」必须同时配置或同时清空",
                    status_code=400,
                )
            model.over_limit_quantity_field = quantity_field
            model.over_limit_limit_field = limit_field
            if "over_limit_name_field" in data.model_fields_set:
                model.over_limit_name_field = _clean(data.over_limit_name_field)
        if "is_enabled" in data.model_fields_set and data.is_enabled is not None:
            model.is_enabled = data.is_enabled
        if "is_mirrored" in data.model_fields_set and data.is_mirrored is not None:
            model.is_mirrored = data.is_mirrored
        # 绑定变化后旧的测试结论与字段缓存都不再适用
        model.last_test_status = None
        model.last_test_error = None
        model.last_tested_at = None
        model.last_test_field_count = None
        model.last_test_record_count = None
        if (
            "app_token" in data.model_fields_set
            or "table_id" in data.model_fields_set
            or "sub_tables" in data.model_fields_set
        ):
            # 绑定换了表（含子表页签变化）：旧镜像数据与同步结论全部失效
            model.last_synced_at = None
            model.last_sync_status = None
            model.last_sync_error = None
            model.last_sync_record_count = None
        await db.commit()
        await db.refresh(model)
        if model.app_token and model.table_id:
            await cache_delete(_field_cache_key(model.app_token, model.table_id))
            for entry in _clean_sub_tables(model.sub_tables):
                await cache_delete(
                    _field_cache_key(model.app_token, entry["table_id"])
                )
        return _build_config_item(definition, model)
    except (OperationalError, ProgrammingError) as exc:
        if _is_config_table_missing(exc):
            raise AppException(
                message="页面表格绑定数据表未创建，请先执行安全模块数据库迁移"
            ) from exc
        raise


def _is_config_table_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "page_feishu_configs" in text
        or "does not exist" in text
        or "undefinedtable" in text
        or "no such table" in text
    )


def _require_binding(
    definition: PageTableDefinition, model: SafetyPageFeishuConfig | None
) -> tuple[str, str]:
    if model is None or not model.is_enabled:
        raise AppException(
            message=f"「{definition.page_name}」尚未配置多维表格或已停用。{_SETTINGS_HINT}",
            status_code=503,
        )
    app_token = _clean(model.app_token)
    table_id = _clean(model.table_id)
    if not app_token or not table_id:
        raise AppException(
            message=f"「{definition.page_name}」的多维表格绑定不完整。{_SETTINGS_HINT}",
            status_code=503,
        )
    return app_token, table_id


async def _load_config_or_raise(
    db: AsyncSession, page_key: str
) -> tuple[PageTableDefinition, SafetyPageFeishuConfig, str, str]:
    definition = _require_definition(page_key)
    try:
        model = await _get_config_model(db, page_key)
    except (OperationalError, ProgrammingError) as exc:
        if _is_config_table_missing(exc):
            raise AppException(
                message="页面表格绑定数据表未创建，请先执行安全模块数据库迁移"
            ) from exc
        raise
    app_token, table_id = _require_binding(definition, model)
    assert model is not None  # _require_binding 已保证
    return definition, model, app_token, table_id


# ── 多子表页签（一页绑定多张子表，主绑定是第一个页签） ──


@dataclass(frozen=True, slots=True)
class BoundTable:
    """页面绑定的一张子表（页签）。"""

    table_id: str
    tab_name: str
    hidden_field_names: tuple[str, ...]
    is_primary: bool


def _clean_sub_tables(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        table_id = str(entry.get("table_id") or "").strip()
        if not table_id:
            continue
        cleaned.append(
            {
                "table_id": table_id,
                "tab_name": str(entry.get("tab_name") or table_id).strip()
                or table_id,
                "hidden_field_names": [
                    str(name).strip()
                    for name in (entry.get("hidden_field_names") or [])
                    if str(name).strip()
                ],
            }
        )
    return cleaned


def _bound_tables(
    definition: PageTableDefinition, model: SafetyPageFeishuConfig
) -> list[BoundTable]:
    """页签清单：主绑定在前，sub_tables 依次在后（table_id 去重）。"""
    primary_hidden = tuple(
        str(name) for name in (model.hidden_field_names or [])
    )
    tables = [
        BoundTable(
            table_id=(model.table_id or "").strip(),
            tab_name=definition.page_name,
            hidden_field_names=primary_hidden,
            is_primary=True,
        )
    ]
    seen = {tables[0].table_id}
    for entry in _clean_sub_tables(model.sub_tables):
        if entry["table_id"] in seen:
            continue
        seen.add(entry["table_id"])
        # 子表未单独配置隐藏字段时沿用主表配置（父记录列通常每张表都要隐藏）
        hidden = entry["hidden_field_names"] or list(primary_hidden)
        tables.append(
            BoundTable(
                table_id=entry["table_id"],
                tab_name=entry["tab_name"],
                hidden_field_names=tuple(hidden),
                is_primary=False,
            )
        )
    return tables


def _resolve_bound_table(
    definition: PageTableDefinition,
    model: SafetyPageFeishuConfig,
    table_id: str | None,
) -> BoundTable:
    """按 table_id 取页签；缺省返回主绑定，未知 table_id 报 404。"""
    tables = _bound_tables(definition, model)
    wanted = (table_id or "").strip()
    if not wanted:
        return tables[0]
    for item in tables:
        if item.table_id == wanted:
            return item
    raise AppException(
        message=f"子表 {wanted} 未绑定到该页面", status_code=404
    )


# ── 字段 schema ──


def _field_cache_key(app_token: str, table_id: str) -> str:
    return f"safety:page-table:fields:{app_token}:{table_id}"


async def _load_field_schema(
    app_token: str, table_id: str, *, refresh: bool = False
) -> list[FieldSchema]:
    """取字段 schema（带 Redis 缓存），失败时抛出可读错误。"""
    cache_key = _field_cache_key(app_token, table_id)
    if not refresh:
        cached = await cache_get(cache_key)
        if cached:
            try:
                payload = json.loads(cached)
            except ValueError:
                payload = None
            if isinstance(payload, list):
                return build_field_schema(payload)
    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
    raw_fields = await client.list_fields(table_id=table_id)
    if not raw_fields:
        raise AppException(
            message=(
                "读取多维表格字段失败：请确认飞书应用已被添加为该多维表格的"
                "协作者，且 App Token / Table ID 正确"
            ),
            status_code=502,
        )
    await cache_set(cache_key, json.dumps(raw_fields), ex=FIELD_CACHE_TTL_SECONDS)
    return build_field_schema(raw_fields)


def _default_date_field(columns: list[FieldSchema]) -> str | None:
    """默认日期字段：优先名称含「日期」，否则第一个日期字段（无则不排序）。"""
    date_fields = [field for field in columns if field.kind == KIND_DATE]
    if not date_fields:
        return None
    preferred = next(
        (field for field in date_fields if "日期" in field.name), date_fields[0]
    )
    return preferred.name


async def _fetch_raw_records(
    app_token: str, table_id: str, *, fetch_sort_field: str | None = None
) -> list[dict[str, Any]]:
    """拉取记录（最多 MAX_RECORDS 条）。

    有日期字段时按其倒序拉取：月度更新的表会持续增长，默认顺序（创建
    先后）配合条数上限会把最新记录截断在窗口外，导致「当天」筛选落空。
    """
    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
    sort = (
        [{"field_name": fetch_sort_field, "desc": True}]
        if fetch_sort_field
        else None
    )
    rows, error = await client.search_records_with_result(
        table_id=table_id,
        page_size=100,
        max_pages=max(1, MAX_RECORDS // 100),
        sort=sort,
    )
    if error:
        raise AppException(
            message=f"读取多维表格记录失败：{error}", status_code=502
        )
    return rows


async def _visible_columns(
    model: SafetyPageFeishuConfig, app_token: str, table_id: str
) -> list[FieldSchema]:
    """页面可见列：全量 schema − 绑定配置的隐藏字段。

    飞书没有「列出视图下字段」的开放接口（/views/:id/fields 返回网关 404），
    视图对齐由设置页的隐藏字段配置承担；绑定的 view_id 仅作记录。
    多页签页面子表未单独配置隐藏字段时沿用主表配置。
    """
    schema = await _load_field_schema(app_token, table_id)
    definition = get_page_table(model.page_key)
    if definition is not None:
        bound = _resolve_bound_table(definition, model, table_id)
        hidden = set(bound.hidden_field_names)
    else:  # pragma: no cover —— 配置行必来自已登记页面
        hidden = {str(name) for name in (model.hidden_field_names or [])}
    return [field for field in schema if field.name not in hidden]


# ── 部门继承（父记录值下放，仅展示与统计，不回写飞书） ──


def _dept_field_of(schema: list[FieldSchema]) -> FieldSchema | None:
    """位置类文本字段（部门/车间 等），继承与统计都以它为目标。"""
    for field in schema:
        if field.kind == KIND_TEXT and any(
            key in field.name for key in _STATS_LOCATION_NAME_KEYS
        ):
            return field
    return None


def _link_parent_ids(raw_fields: dict[str, Any]) -> list[str]:
    """从原始字段值里提取 link 字段（type 18/21）指向的父记录 id。"""
    ids: list[str] = []
    for value in raw_fields.values():
        if not isinstance(value, dict):
            continue
        raw_ids = value.get("link_record_ids")
        if isinstance(raw_ids, list):
            ids.extend(str(item) for item in raw_ids if item)
    return ids


def _resolve_dept_inheritance(
    schema: list[FieldSchema], raw_rows: list[dict[str, Any]]
) -> dict[str, str]:
    """计算每条记录继承后的部门值：部门为空时取 link 父记录的部门。

    公司隐患总台账约 80% 记录的「部门/车间」填在父记录上；继承让列表列
    显示与车间统计完整。两轮迭代覆盖「父记录自身也靠继承」的情况。
    返回 {record_id: 部门}（仅含有值的记录）。
    """
    dept_field = _dept_field_of(schema)
    if dept_field is None:
        return {}
    dept_of: dict[str, str] = {}
    parent_of: dict[str, str] = {}
    for raw in raw_rows:
        record_id = str(raw.get("record_id") or "")
        if not record_id:
            continue
        raw_fields = raw.get("fields")
        if not isinstance(raw_fields, dict):
            continue
        dept = str(
            decode_value(dept_field, raw_fields.get(dept_field.name)) or ""
        ).strip()
        if dept:
            dept_of[record_id] = dept
        parents = _link_parent_ids(raw_fields)
        if parents:
            parent_of[record_id] = parents[0]
    for _ in range(2):
        changed = False
        for record_id, parent in parent_of.items():
            if record_id in dept_of:
                continue
            inherited = dept_of.get(parent)
            if inherited:
                dept_of[record_id] = inherited
                changed = True
        if not changed:
            break
    return dept_of


def _apply_inherited_dept(
    dept_field: FieldSchema | None,
    dept_map: dict[str, str],
    record_id: str,
    decoded: dict[str, Any],
) -> None:
    """把继承到的部门补进解码结果（仅在原值为空时）。"""
    if dept_field is None:
        return
    if str(decoded.get(dept_field.name) or "").strip():
        return
    inherited = dept_map.get(record_id)
    if inherited:
        decoded[dept_field.name] = inherited


def _mirror_fields_for_response(
    fields: dict[str, Any] | None, columns: list[FieldSchema]
) -> dict[str, Any]:
    """镜像副本存了全量字段（含隐藏列），响应只输出页面可见列。"""
    if not fields:
        return {}
    visible = {field.name for field in columns}
    return {name: value for name, value in fields.items() if name in visible}


# ── 本地镜像（全量副本 + 定时同步 + 编辑写透） ──

MIRROR_SYNC_MAX_RECORDS = 20000
MIRROR_SYNC_LOCK_TIMEOUT = 1800
_MIRROR_SYNC_LOCK_TEMPLATE = "safety:page-table:mirror-sync:{page_key}"
_mirror_sync_task: asyncio.Task[None] | None = None


def _ilike_escape(value: str) -> str:
    """转义 LIKE/ILIKE 通配符，选项名里的 % _ 按字面匹配。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _mirror_search_text(schema: list[FieldSchema], decoded: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in schema:
        text = _search_text(field, decoded.get(field.name)).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


async def sync_page_table_mirror(db: AsyncSession, page_key: str) -> int:
    """全量同步一个镜像页的全部绑定子表：拉取记录 upsert 并软删消失记录。

    多页签页面逐表同步（单表失败不影响其它表，整体状态记 partial/failed）；
    成功返回全部子表同步记录数；失败回写 ``last_sync_status`` 后抛业务异常。
    """
    definition, model, app_token, _ = await _load_config_or_raise(db, page_key)
    tables = _bound_tables(definition, model)
    lock_key = _MIRROR_SYNC_LOCK_TEMPLATE.format(page_key=page_key)
    if not await acquire_lock(lock_key, timeout=MIRROR_SYNC_LOCK_TIMEOUT):
        raise AppException(
            message="该页面的镜像同步正在执行，请稍后再试", status_code=409
        )
    try:
        client = SafetyBitableClient(app_token=app_token, table_id="")
        now = datetime.now(UTC)
        total_kept = 0
        errors: list[str] = []
        for bound in tables:
            try:
                schema = await _load_field_schema(app_token, bound.table_id)
                raw_rows, error = await client.search_records_with_result(
                    table_id=bound.table_id,
                    page_size=100,
                    max_pages=MIRROR_SYNC_MAX_RECORDS // 100,
                )
                if error:
                    errors.append(f"{bound.tab_name}: {error}")
                    continue
                existing_rows = (
                    (
                        await db.execute(
                            select(SafetyPageTableMirrorRecord).where(
                                SafetyPageTableMirrorRecord.page_key == page_key,
                                SafetyPageTableMirrorRecord.table_id
                                == bound.table_id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                existing_by_record = {
                    row.record_id: row for row in existing_rows
                }
                dept_field = _dept_field_of(schema)
                dept_map = _resolve_dept_inheritance(schema, raw_rows)
                seen: set[str] = set()
                kept = 0
                for raw in raw_rows[:MIRROR_SYNC_MAX_RECORDS]:
                    record_id = str(raw.get("record_id") or "")
                    if not record_id or record_id in seen:
                        # 飞书翻页可能跨页返回同一条记录，重复插入会撞唯一索引
                        continue
                    seen.add(record_id)
                    kept += 1
                    raw_fields = raw.get("fields")
                    decoded = decode_record_fields(
                        schema, raw_fields if isinstance(raw_fields, dict) else {}
                    )
                    _apply_inherited_dept(
                        dept_field, dept_map, record_id, decoded
                    )
                    current = existing_by_record.pop(record_id, None)
                    if current is None:
                        db.add(
                            SafetyPageTableMirrorRecord(
                                page_key=page_key,
                                table_id=bound.table_id,
                                record_id=record_id,
                                fields=decoded,
                                search_text=_mirror_search_text(schema, decoded),
                                synced_at=now,
                            )
                        )
                    else:
                        current.fields = decoded
                        current.search_text = _mirror_search_text(
                            schema, decoded
                        )
                        current.synced_at = now
                        current.is_deleted = False
                for stale in existing_by_record.values():
                    stale.is_deleted = True
                total_kept += kept
                logger.info(
                    "页面镜像同步: page=%s 表=%s 记录=%s",
                    page_key,
                    bound.tab_name,
                    kept,
                )
            except Exception as exc:  # noqa: BLE001 —— 单表失败不中断其它表
                await db.rollback()
                errors.append(f"{bound.tab_name}: {exc}")
        model.last_synced_at = now
        if errors:
            model.last_sync_status = "failed" if not total_kept else "partial"
            model.last_sync_error = "; ".join(errors)[:500]
        else:
            model.last_sync_status = "success"
            model.last_sync_error = None
        model.last_sync_record_count = total_kept
        if errors and not total_kept:
            # 全部子表失败：先回滚本会话，再经独立会话记录失败状态后抛出
            await db.rollback()
            raise AppException(
                message=f"镜像同步失败：{errors[0]}", status_code=502
            )
        await db.commit()
        logger.info(
            "页面镜像同步完成: page=%s 子表=%s 记录=%s 错误=%s",
            page_key,
            len(tables),
            total_kept,
            len(errors),
        )
        return total_kept
    except AppException:
        raise
    except Exception as exc:
        await db.rollback()
        await _record_mirror_sync_failure(page_key, str(exc))
        raise AppException(
            message=f"镜像同步失败：{exc}", status_code=502
        ) from exc
    finally:
        await release_lock(lock_key)


async def _record_mirror_sync_failure(page_key: str, message: str) -> None:
    """独立会话回写失败状态（主会话已回滚，不能再复用）。"""
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(SafetyPageFeishuConfig).where(
                    SafetyPageFeishuConfig.page_key == page_key,
                    SafetyPageFeishuConfig.is_deleted.is_(False),
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                return
            model.last_synced_at = datetime.now(UTC)
            model.last_sync_status = "failed"
            model.last_sync_error = message[:500]
            await session.commit()
    except Exception:
        logger.exception("回写镜像同步失败状态时出错: page=%s", page_key)


def _schedule_mirror_sync(page_key: str) -> None:
    """后台触发一次镜像同步（读取路径的未同步引导），不阻塞当前请求。"""
    global _mirror_sync_task
    if _mirror_sync_task is not None and not _mirror_sync_task.done():
        return
    _mirror_sync_task = asyncio.create_task(_run_mirror_sync_once(page_key))


async def _run_mirror_sync_once(page_key: str) -> None:
    try:
        async with async_session_factory() as session:
            await sync_page_table_mirror(session, page_key)
    except Exception:
        logger.exception("后台镜像同步失败: page=%s", page_key)


async def _write_through_mirror(
    page_key: str,
    record_id: str,
    raw_fields: dict[str, Any],
    table_id: str | None = None,
) -> bool:
    """编辑写透：用飞书侧最新字段值 upsert 镜像行（独立会话）。

    失败只记日志并返回 False，不影响已提交到飞书的修改。
    ``table_id`` 缺省用页面主绑定表（兼容单表页面）。
    """
    try:
        async with async_session_factory() as session:
            model = await _get_config_model(session, page_key)
            if model is None or not model.is_mirrored:
                return False
            effective_table = (table_id or model.table_id or "").strip()
            schema = await _load_field_schema(
                model.app_token or "", effective_table
            )
            decoded = decode_record_fields(schema, raw_fields)
            result = await session.execute(
                select(SafetyPageTableMirrorRecord).where(
                    SafetyPageTableMirrorRecord.page_key == page_key,
                    SafetyPageTableMirrorRecord.table_id == effective_table,
                    SafetyPageTableMirrorRecord.record_id == record_id,
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                session.add(
                    SafetyPageTableMirrorRecord(
                        page_key=page_key,
                        table_id=effective_table,
                        record_id=record_id,
                        fields=decoded,
                        search_text=_mirror_search_text(schema, decoded),
                    )
                )
            else:
                row.fields = decoded
                row.search_text = _mirror_search_text(schema, decoded)
                row.synced_at = datetime.now(UTC)
                row.is_deleted = False
            await session.commit()
            return True
    except Exception:
        logger.exception(
            "镜像写透失败（下次定时同步会兜底）: page=%s record=%s",
            page_key,
            record_id,
        )
        return False


async def upsert_page_table_mirror_record(
    page_key: str, record_id: str, table_id: str | None = None
) -> bool:
    """按 record_id 拉取飞书最新值并写透镜像（附件上传后使用）。"""
    try:
        async with async_session_factory() as session:
            model = await _get_config_model(session, page_key)
            if model is None or not model.is_mirrored:
                return False
            effective_table = (table_id or model.table_id or "").strip()
            client = SafetyBitableClient(
                app_token=model.app_token, table_id=effective_table
            )
            raw_fields = await client.get_record(record_id)
        if not isinstance(raw_fields, dict):
            return False
        return await _write_through_mirror(
            page_key, record_id, raw_fields, effective_table
        )
    except Exception:
        logger.exception(
            "镜像写透（单条拉取）失败: page=%s record=%s", page_key, record_id
        )
        return False


def _mirror_condition_expr(
    field: FieldSchema, expected: str, op: str = "eq"
) -> Any:
    """镜像查询的条件表达式（语义与实时路径 _condition_matches 一致）。

    日期字段支持 ``gte``/``lte``（ISO 文本比较，构成时间范围）；
    ``neq`` 表示「不等于且含未填写」（NULL 也命中，与「关闭状态 ≠
    已关闭」的到期下钻口径一致）；人员字段按 JSON 数组内的姓名引号
    包含匹配。
    """
    cell = SafetyPageTableMirrorRecord.fields[field.name].astext
    escaped = _ilike_escape(expected)
    if op == "neq":
        # NULL（字段缺失/未填写）与不相等的值都命中；多选列的 JSON 数组
        # 里含该选项也算相等（如关闭状态 ['已关闭']），需一并排除
        return or_(
            cell.is_(None),
            and_(cell != expected, ~cell.ilike(f'%"{escaped}"%')),
        )
    if field.kind == KIND_DATE:
        if op == "gte":
            return cell >= expected
        if op == "lte":
            return cell <= expected
        return cell.like(f"{escaped}%")
    if field.kind == KIND_CHECKBOX:
        return cell == ("true" if expected == "是" else "false")
    if field.kind in (KIND_MULTI_SELECT, KIND_PERSON):
        return cell.ilike(f'%"{escaped}"%')
    if field.kind == KIND_SELECT:
        return cell == expected
    return cell.ilike(f"%{escaped}%")


def _mirror_order_exprs(
    field: FieldSchema | None, direction: str
) -> list[Any]:
    """镜像查询的排序（数值列做正则防护后转数值，其余按文本）。"""
    if field is None:
        return [SafetyPageTableMirrorRecord.synced_at.desc()]
    cell_text = func.nullif(
        SafetyPageTableMirrorRecord.fields[field.name].astext, ""
    )
    reverse = direction.lower() == "desc"
    if field.kind == KIND_NUMBER:
        numeric = cell_text.cast(Numeric)
        guarded = case(
            (cell_text.op("~")(r"^-?\d+(\.\d+)?$"), numeric),
            else_=None,
        )
        expr = guarded.desc().nullslast() if reverse else guarded.asc().nullslast()
    else:
        expr = cell_text.desc().nullslast() if reverse else cell_text.asc().nullslast()
    return [expr, SafetyPageTableMirrorRecord.record_id.asc()]


# ── 记录查询 ──


def _search_text(field: FieldSchema, value: Any) -> str:
    if value is None:
        return ""
    if field.kind == KIND_CHECKBOX:
        return "是" if value else "否"
    if field.kind == KIND_NUMBER:
        return str(value)
    if field.kind == KIND_ATTACHMENT:
        return " ".join(str(item.get("name") or "") for item in value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("name") or item.get("text") or ""))
            else:
                parts.append(str(item))
        return " ".join(parts)
    if isinstance(value, dict):
        return " ".join(str(part) for part in value.values())
    return str(value)


def _sort_key(field: FieldSchema, value: Any) -> tuple[int, Any]:
    """排序键：空值恒排在后（方向反转时由调用方处理）。"""
    if value is None or value == "":
        return (1, "")
    if field.kind == KIND_NUMBER:
        return (0, float(value))
    if field.kind == KIND_CHECKBOX:
        return (0, 1 if value else 0)
    if field.kind == KIND_DATE:
        return (0, str(value))
    return (0, _search_text(field, value))


def _condition_matches(
    field: FieldSchema, value: Any, expected: str, op: str = "eq"
) -> bool:
    """多条件筛选的单条匹配规则（与下钻口径独立，面向查询表单）。

    日期：解码文本（YYYY-MM-DD）等于/前缀匹配，``gte``/``lte`` 按 ISO
    文本比较构成时间范围；``neq`` 对 ``eq`` 取反（空值也命中，服务
    「关闭状态 ≠ 已关闭」的到期下钻）；
    选项/多选：选项名精确相等；人员：任一姓名相等；
    文本：不区分大小写包含；勾选：是/否。
    """
    if op == "neq":
        return not _condition_matches(field, value, expected, "eq")
    text = _search_text(field, value).strip()
    if field.kind == KIND_DATE:
        if not text:
            return False
        if op == "gte":
            return text >= expected
        if op == "lte":
            return text <= expected
        return text == expected or text.startswith(expected)
    if field.kind == KIND_CHECKBOX:
        return ("是" if value else "否") == expected
    if isinstance(value, list):
        if field.kind == KIND_PERSON:
            return any(
                isinstance(item, dict) and str(item.get("name") or "") == expected
                for item in value
            )
        return any(str(item) == expected for item in value)
    if field.kind == KIND_TEXT:
        return expected.lower() in text.lower()
    return text == expected


async def _apply_dimension_filter(
    db: AsyncSession,
    decoded_rows: list[PageTableRecord],
    columns: list[FieldSchema],
    aliases: dict[str, str],
    dimension: str,
    dimension_value: str,
) -> list[PageTableRecord]:
    """仪表盘下钻过滤（车间归一/AI 兜底口径），实时与镜像路径共用。"""
    target = next((field for field in columns if field.name == dimension), None)
    if target is None:
        raise AppException(
            message=f"筛选字段「{dimension}」不在当前表格中", status_code=400
        )
    row_texts = [
        _search_text(target, record.fields.get(target.name)).strip()
        for record in decoded_rows
    ]
    if target.kind == KIND_TEXT:
        text_keys, pending = await _resolve_text_bucket_keys(
            db, target, row_texts, aliases
        )
        if pending:
            # 后台触发 AI 兜底归类；本次请求立即返回，下次刷新生效
            _schedule_ai_classify(pending, aliases)
        row_keys = {
            record.record_id: text_keys[text]
            for record, text in zip(decoded_rows, row_texts)
        }
    else:
        row_keys = {
            record.record_id: _stat_bucket_key(
                target, record.fields.get(target.name), aliases
            )
            for record in decoded_rows
        }
    if dimension_value == "其他" and target.kind != KIND_DATE:
        # 「其他」是合成桶：下钻语义 = 不在展示名单内的记录（与图表口径一致）
        counter: Counter[str] = Counter(row_keys.values())
        kept_keys = set(_stat_top_keys(counter, target, aliases))
        return [
            record
            for record in decoded_rows
            if row_keys[record.record_id] not in kept_keys
        ]
    return [
        record
        for record in decoded_rows
        if row_keys[record.record_id] == dimension_value
    ]


async def _list_records_from_mirror(
    db: AsyncSession,
    definition: PageTableDefinition,
    model: SafetyPageFeishuConfig,
    columns: list[FieldSchema],
    aliases: dict[str, str],
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    sort_field: str | None,
    sort_direction: str,
    filter_field: str | None,
    filter_value: str | None,
    conditions: list[PageTableRecordCondition] | None,
    table_id: str | None = None,
    over_limit_config: OverLimitFieldConfig | None = None,
    over_limit_only: bool = False,
) -> PageTableRecordsResponse:
    """镜像数据源：SQL 过滤/排序/分页（本地全量，无条数窗口）。

    仪表盘下钻（车间归一/AI 口径）无法下推 SQL：命中该场景时先取回全部
    匹配行，Python 端过滤排序后再分页，与实时路径语义一致。
    ``table_id`` 选择页签对应子表的镜像行；缺省主绑定表。
    超储过滤是派生值，同样只能 Python 端完成。
    """
    record_model = SafetyPageTableMirrorRecord
    effective_table = (
        table_id or model.table_id or ""
    ).strip()
    stmt = select(record_model).where(
        record_model.page_key == definition.page_key,
        record_model.table_id == effective_table,
        record_model.is_deleted.is_(False),
    )
    needle = (keyword or "").strip()
    if needle:
        stmt = stmt.where(
            record_model.search_text.ilike(f"%{_ilike_escape(needle)}%")
        )
    # 文本类条件（部门/车间）按图表桶归一口径匹配，SQL 的包含匹配会把
    # 「DR提炼→201二车间（DR）」这类别名原始写法漏掉，因此这类条件不下推
    # SQL，改为取回后统一走 _filter_decoded_records。
    active_conditions = [
        condition for condition in (conditions or []) if condition.value.strip()
    ]
    sql_conditions: list[PageTableRecordCondition] = []
    for condition in active_conditions:
        target = next(
            (field for field in columns if field.name == condition.field), None
        )
        if target is None:
            raise AppException(
                message=f"筛选字段「{condition.field}」不在当前表格中",
                status_code=400,
            )
        if target.kind != KIND_TEXT:
            sql_conditions.append(condition)

    for condition in sql_conditions:
        target = next(
            (field for field in columns if field.name == condition.field), None
        )
        assert target is not None
        stmt = stmt.where(
            _mirror_condition_expr(target, condition.value.strip(), condition.op)
        )

    dimension = (filter_field or "").strip()
    dimension_value = (filter_value or "").strip()
    drill_down = bool(dimension and dimension_value)
    # 命中文本条件、下钻或超储过滤时需要全量取回后 Python 过滤，不能再 SQL 分页
    python_filter = (
        drill_down
        or len(sql_conditions) < len(active_conditions)
        or (over_limit_only and over_limit_config is not None)
    )

    sort_target = next(
        (field for field in columns if field.name == sort_field), None
    )
    safe_size = max(1, min(page_size, MAX_PAGE_SIZE))
    safe_page = max(1, page)

    if python_filter:
        rows = (await db.execute(stmt)).scalars().all()
        decoded_rows = [
            PageTableRecord(
                record_id=row.record_id,
                fields=_mirror_fields_for_response(row.fields, columns),
            )
            for row in rows
        ]
        if over_limit_config is not None:
            source_values = {row.record_id: dict(row.fields or {}) for row in rows}
            _annotate_over_limit(decoded_rows, over_limit_config, source_values)
            if over_limit_only:
                decoded_rows = [
                    record for record in decoded_rows if record.over_limit
                ]
        if drill_down:
            decoded_rows = await _apply_dimension_filter(
                db, decoded_rows, columns, aliases, dimension, dimension_value
            )
        if active_conditions:
            by_fields = {id(record.fields): record for record in decoded_rows}
            kept = await _filter_decoded_records(
                db,
                [record.fields for record in decoded_rows],
                columns,
                keyword=None,  # 关键字已在 SQL 应用
                conditions=active_conditions,
                aliases=aliases,
            )
            decoded_rows = [by_fields[id(fields)] for fields in kept]
        if sort_target is not None:
            reverse = sort_direction.lower() == "desc"
            decoded_rows.sort(
                key=lambda record: _sort_key(
                    sort_target, record.fields.get(sort_target.name)
                ),
                reverse=reverse,
            )
        total = len(decoded_rows)
        start = (safe_page - 1) * safe_size
        page_rows = decoded_rows[start : start + safe_size]
    else:
        total = (
            await db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    stmt.order_by(*_mirror_order_exprs(sort_target, sort_direction))
                    .offset((safe_page - 1) * safe_size)
                    .limit(safe_size)
                )
            )
            .scalars()
            .all()
        )
        page_rows = [
            PageTableRecord(
                record_id=row.record_id,
                fields=_mirror_fields_for_response(row.fields, columns),
            )
            for row in rows
        ]
        if over_limit_config is not None:
            source_values = {row.record_id: dict(row.fields or {}) for row in rows}
            _annotate_over_limit(page_rows, over_limit_config, source_values)

    return PageTableRecordsResponse(
        page_key=definition.page_key,
        page_name=definition.page_name,
        columns=[PageTableColumn(**field.as_dict()) for field in columns],
        records=page_rows,
        total=total,
        page=safe_page,
        page_size=safe_size,
        truncated=False,
        over_limit_fields=(
            PageTableOverLimitFields(
                quantity_field=over_limit_config.quantity_field,
                limit_field=over_limit_config.limit_field,
                name_field=over_limit_config.name_field or "",
            )
            if over_limit_config
            else None
        ),
    )


async def list_page_table_records(
    db: AsyncSession,
    page_key: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    keyword: str | None = None,
    sort_field: str | None = None,
    sort_direction: str = "asc",
    filter_field: str | None = None,
    filter_value: str | None = None,
    conditions: list[PageTableRecordCondition] | None = None,
    table_id: str | None = None,
    over_limit_only: bool = False,
) -> PageTableRecordsResponse:
    """返回列定义与分页记录（多页签页面用 ``table_id`` 选择子表）。

    镜像开启且已同步过时查本地镜像（全量、无条数窗口）；未同步过先触发
    后台同步并回退实时拉取，保证首屏可用。``filter_field``/``filter_value``
    服务于仪表盘下钻，``conditions`` 是查询表单的多条件（字段间 AND）。
    页面绑定配置了超储计算列时，记录附带 ``over_limit/over_pct`` 派生标记，
    ``over_limit_only`` 只保留超储行。
    """
    definition, model, app_token, _primary = await _load_config_or_raise(
        db, page_key
    )
    bound = _resolve_bound_table(definition, model, table_id)
    effective_table = bound.table_id
    columns = await _visible_columns(model, app_token, effective_table)
    aliases = _workshop_aliases_of(model.workshop_aliases)
    over_limit_config = _over_limit_config(model)
    if over_limit_only and over_limit_config is None:
        raise AppException(
            message=(
                "该页面未配置超储计算列，无法按超储筛选。请先在 飞书设置 → "
                "页面数据表映射 中配置存量列与上限列"
            ),
            status_code=400,
        )
    # 条件字段必须在当前表格中（统计聚合路径宽松跳过，列表路径严格校验）
    for condition in conditions or []:
        if condition.value.strip() and not any(
            field.name == condition.field for field in columns
        ):
            raise AppException(
                message=f"筛选字段「{condition.field}」不在当前表格中",
                status_code=400,
            )

    if model.is_mirrored:
        if model.last_synced_at is None:
            # 首读引导：后台先同步一次，本次仍走实时路径
            _schedule_mirror_sync(page_key)
        else:
            return await _list_records_from_mirror(
                db,
                definition,
                model,
                columns,
                aliases,
                page=page,
                page_size=page_size,
                keyword=keyword,
                sort_field=sort_field,
                sort_direction=sort_direction,
                filter_field=filter_field,
                filter_value=filter_value,
                conditions=conditions,
                table_id=effective_table,
                over_limit_config=over_limit_config,
                over_limit_only=over_limit_only,
            )

    raw_rows = await _fetch_raw_records(
        app_token, effective_table, fetch_sort_field=_default_date_field(columns)
    )
    truncated = len(raw_rows) > MAX_RECORDS
    raw_rows = raw_rows[:MAX_RECORDS]

    full_schema = await _load_field_schema(app_token, effective_table)
    dept_field = _dept_field_of(full_schema)
    dept_map = _resolve_dept_inheritance(full_schema, raw_rows)

    decoded_rows: list[PageTableRecord] = []
    raw_field_map: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        record_id = str(row.get("record_id") or "")
        if not record_id:
            continue
        raw_fields = row.get("fields")
        normalized = raw_fields if isinstance(raw_fields, dict) else {}
        raw_field_map[record_id] = normalized
        decoded = decode_record_fields(columns, normalized)
        _apply_inherited_dept(dept_field, dept_map, record_id, decoded)
        decoded_rows.append(PageTableRecord(record_id=record_id, fields=decoded))

    if over_limit_config is not None:
        _annotate_over_limit(decoded_rows, over_limit_config, raw_field_map)
        if over_limit_only:
            decoded_rows = [
                record for record in decoded_rows if record.over_limit
            ]

    needle = (keyword or "").strip().lower()
    if needle:
        decoded_rows = [
            record
            for record in decoded_rows
            if any(
                needle in _search_text(field, record.fields.get(field.name)).lower()
                for field in columns
            )
        ]

    active_conditions = [
        condition for condition in (conditions or []) if condition.value.strip()
    ]
    if active_conditions:
        by_fields = {id(record.fields): record for record in decoded_rows}
        kept = await _filter_decoded_records(
            db,
            [record.fields for record in decoded_rows],
            columns,
            keyword=None,  # 关键字已在上方应用
            conditions=active_conditions,
            aliases=aliases,
        )
        decoded_rows = [by_fields[id(fields)] for fields in kept]

    dimension = (filter_field or "").strip()
    dimension_value = (filter_value or "").strip()
    if dimension and dimension_value:
        decoded_rows = await _apply_dimension_filter(
            db, decoded_rows, columns, aliases, dimension, dimension_value
        )

    sort_target = next((field for field in columns if field.name == sort_field), None)
    if sort_target is not None:
        reverse = sort_direction.lower() == "desc"
        decoded_rows.sort(
            key=lambda record: _sort_key(
                sort_target, record.fields.get(sort_target.name)
            ),
            reverse=reverse,
        )

    total = len(decoded_rows)
    safe_size = max(1, min(page_size, MAX_PAGE_SIZE))
    safe_page = max(1, page)
    start = (safe_page - 1) * safe_size
    return PageTableRecordsResponse(
        page_key=page_key,
        page_name=definition.page_name,
        columns=[PageTableColumn(**field.as_dict()) for field in columns],
        records=decoded_rows[start : start + safe_size],
        total=total,
        page=safe_page,
        page_size=safe_size,
        truncated=truncated,
        over_limit_fields=(
            PageTableOverLimitFields(
                quantity_field=over_limit_config.quantity_field,
                limit_field=over_limit_config.limit_field,
                name_field=over_limit_config.name_field or "",
            )
            if over_limit_config
            else None
        ),
    )


# ── 记录写入 ──


async def update_page_table_record(
    db: AsyncSession,
    page_key: str,
    record_id: str,
    values: dict[str, Any],
    *,
    user_id: uuid.UUID | None = None,
    table_id: str | None = None,
) -> PageTableRecord:
    """把页面提交的字段值回写到飞书多维表格（多页签页面按 table_id 定位）。"""
    definition, model, app_token, _primary = await _load_config_or_raise(
        db, page_key
    )
    bound = _resolve_bound_table(definition, model, table_id)
    effective_table = bound.table_id
    if not values:
        raise AppException(message="没有需要保存的字段", status_code=400)
    schema = await _load_field_schema(app_token, effective_table)
    try:
        encoded = encode_record_fields(schema, values)
    except FieldCodecError as exc:
        raise AppException(message=str(exc), status_code=400) from exc

    client = SafetyBitableClient(app_token=app_token, table_id=effective_table)
    ok, error = await client.update_record_with_result(record_id, encoded)
    if not ok:
        raise AppException(
            message=f"写入飞书多维表格失败：{error or '未知错误'}", status_code=502
        )

    await record_audit_log(
        db,
        action="update",
        user_id=user_id,
        resource_type="safety_page_table_record",
        resource_id=model.id,
        new_value={"fields": values},
        extra={
            "page_key": page_key,
            "record_id": record_id,
            "app_token": app_token,
            "table_id": effective_table,
        },
    )

    # 回读一次，让页面拿到飞书侧的真实结果（公式/关联等字段由飞书计算）
    raw_fields = await client.get_record(record_id)
    if isinstance(raw_fields, dict):
        # 写透：飞书已更新，本地镜像同步这一条（失败只记日志）
        await _write_through_mirror(
            page_key, record_id, raw_fields, effective_table
        )
    return PageTableRecord(
        record_id=record_id,
        fields=decode_record_fields(schema, raw_fields),
    )


async def create_page_table_record(
    db: AsyncSession,
    page_key: str,
    values: dict[str, Any],
    *,
    user_id: uuid.UUID | None = None,
    table_id: str | None = None,
) -> PageTableRecord:
    """在绑定的子表新建一条记录（多页签页面按 ``table_id`` 定位）。

    写入飞书成功后回读真实字段值并写透本地镜像，页面即可立即看到新记录，
    无需等待 15 分钟周期同步。
    """
    definition, model, app_token, _primary = await _load_config_or_raise(
        db, page_key
    )
    bound = _resolve_bound_table(definition, model, table_id)
    effective_table = bound.table_id
    if not values:
        raise AppException(message="没有需要保存的字段", status_code=400)
    schema = await _load_field_schema(app_token, effective_table)
    try:
        encoded = encode_record_fields(schema, values)
    except FieldCodecError as exc:
        raise AppException(message=str(exc), status_code=400) from exc
    # 新建时跳过空值字段，避免把一串 null 写进飞书；全空则拒绝
    encoded = {name: value for name, value in encoded.items() if value is not None}
    if not encoded:
        raise AppException(message="请至少填写一个字段", status_code=400)

    client = SafetyBitableClient(app_token=app_token, table_id=effective_table)
    record_id, error = await client.create_record_with_result(encoded)
    if not record_id:
        raise AppException(
            message=f"写入飞书多维表格失败：{error or '未知错误'}", status_code=502
        )

    await record_audit_log(
        db,
        action="create",
        user_id=user_id,
        resource_type="safety_page_table_record",
        resource_id=model.id,
        new_value={"fields": values},
        extra={
            "page_key": page_key,
            "record_id": record_id,
            "app_token": app_token,
            "table_id": effective_table,
        },
    )

    # 回读一次，让页面拿到飞书侧的真实结果（公式/自动编号等字段由飞书计算）
    raw_fields = await client.get_record(record_id)
    if isinstance(raw_fields, dict):
        # 写透：本地镜像同步这一条（失败只记日志，等待周期同步兜底）
        await _write_through_mirror(
            page_key, record_id, raw_fields, effective_table
        )
    return PageTableRecord(
        record_id=record_id,
        fields=decode_record_fields(schema, raw_fields),
    )


async def upload_page_table_attachment(
    db: AsyncSession,
    page_key: str,
    record_id: str,
    field_name: str,
    *,
    file: Any,
    user_id: uuid.UUID | None = None,
    table_id: str | None = None,
) -> PageTableAttachmentUploadResponse:
    """上传附件到飞书并在记录附件字段上追加（不覆盖已有附件）。"""
    definition, model, app_token, _primary = await _load_config_or_raise(
        db, page_key
    )
    bound = _resolve_bound_table(definition, model, table_id)
    effective_table = bound.table_id
    schema = await _load_field_schema(app_token, effective_table)
    try:
        attachment_field_or_error(schema, field_name)
    except FieldCodecError as exc:
        raise AppException(message=str(exc), status_code=400) from exc

    filename, content = await read_upload_secure(
        file,
        max_bytes=ATTACHMENT_MAX_BYTES,
        allowed_extensions=ATTACHMENT_ALLOWED_EXTENSIONS,
        what="附件",
    )

    client = SafetyBitableClient(app_token=app_token, table_id=effective_table)
    file_token = await client.upload_media(content, filename)
    if not file_token:
        raise AppException(message="上传附件到飞书失败", status_code=502)

    raw_fields = await client.get_record(record_id)
    tokens = existing_attachment_tokens(raw_fields.get(field_name))
    if file_token not in tokens:
        tokens.append(file_token)
    payload = [{"file_token": token} for token in tokens]
    ok, error = await client.update_record_with_result(
        record_id, {field_name: payload}
    )
    if not ok:
        raise AppException(
            message=(
                f"附件已上传但写入记录失败：{error or '未知错误'}"
                "（请勿重复上传，可在飞书表格中手动挂载该附件）"
            ),
            status_code=502,
        )

    await record_audit_log(
        db,
        action="upload_attachment",
        user_id=user_id,
        resource_type="safety_page_table_record",
        resource_id=model.id,
        new_value={"field": field_name, "file_name": filename},
        extra={"page_key": page_key, "record_id": record_id},
    )

    refreshed = await client.get_record(record_id)
    if isinstance(refreshed, dict):
        # 写透：附件字段已在飞书更新，本地镜像同步这一条（失败只记日志）
        await _write_through_mirror(page_key, record_id, refreshed)
    decoded = decode_record_fields(schema, refreshed)
    attachments = decoded.get(field_name) or []
    return PageTableAttachmentUploadResponse(
        record_id=record_id,
        field_name=field_name,
        attachments=[PageTableAttachmentItem(**item) for item in attachments],
    )


async def fetch_page_table_attachment(
    db: AsyncSession,
    page_key: str,
    record_id: str,
    field_name: str,
    file_token: str,
    table_id: str | None = None,
) -> tuple[bytes, str, str]:
    """代理下载附件。

    先校验该 file_token 确实属于这条记录的该附件字段，再回源飞书，避免
    通过构造 token 读取其它记录/表格的附件。
    """
    definition, model, app_token, _primary = await _load_config_or_raise(
        db, page_key
    )
    bound = _resolve_bound_table(definition, model, table_id)
    client = SafetyBitableClient(app_token=app_token, table_id=bound.table_id)
    raw_fields = await client.get_record(record_id)
    attachments = raw_fields.get(field_name)
    matched = None
    if isinstance(attachments, list):
        matched = next(
            (
                item
                for item in attachments
                if isinstance(item, dict) and item.get("file_token") == file_token
            ),
            None,
        )
    if matched is None:
        raise AppException(message="附件不存在或不属于该记录", status_code=404)

    # 首选 tmp_url（batch_get_tmp_download_url 换取内部下载地址）：
    # 部分应用/表格组合下附件 url 直接下载会 403，只有这条路可用
    content = await client.download_attachment_via_tmp_url(
        str(matched.get("tmp_url") or "")
    )
    if content is None:
        content = await client.download_attachment_from_url(
            str(matched.get("url") or "")
        )
    if content is None:
        content = await client.download_attachment(file_token)
    if content is None:
        raise AppException(message="下载飞书附件失败", status_code=502)
    return (
        content,
        str(matched.get("type") or "application/octet-stream"),
        str(matched.get("name") or "attachment"),
    )


# ── 仪表盘聚合 ──


def _default_stats_fields(columns: list[FieldSchema]) -> list[str]:
    """未显式指定分组字段时的默认维度：日期按月、位置类文本按车间号、单选按选项。"""
    date_field = next((f for f in columns if f.kind == KIND_DATE), None)
    location_field = next(
        (
            f
            for f in columns
            if f.kind == KIND_TEXT
            and any(key in f.name for key in _STATS_LOCATION_NAME_KEYS)
        ),
        None,
    )
    select_field = next(
        (f for f in columns if f.kind in (KIND_SELECT, KIND_MULTI_SELECT)), None
    )
    return [
        field.name
        for field in (date_field, location_field, select_field)
        if field is not None
    ]


def _stat_bucket_key(
    field: FieldSchema,
    value: Any,
    aliases: dict[str, str] | None = None,
) -> str:
    if field.kind == KIND_TEXT:
        # 文本字段走 AI 兜底分类感知的解析（见 _text_bucket_keys）
        text = _search_text(field, value).strip()
        return normalize_workshop_name(text, aliases) or text or _UNFILLED_KEY
    text = _search_text(field, value).strip()
    if not text:
        return _UNFILLED_KEY
    if field.kind == KIND_DATE:
        # 解码后的日期是 YYYY-MM-DD，按月归组
        return text[:7]
    return text


def _stat_top_keys(
    counter: Counter[str],
    field: FieldSchema,
    aliases: dict[str, str],
) -> list[str]:
    """统计展示的分组名单（与图表桶一致）。

    值分组：页面配置的规范车间名（别名映射的值）始终保留——DR/MC 这类产线
    拆分计数小，普通排名会掉进「其他」，正是老板要看的内容；其余按计数
    取前 N。日期分组：按时间升序保留最近 N 个月。
    """
    if field.kind == KIND_DATE:
        keys = sorted(key for key in counter if key != _UNFILLED_KEY)
        return keys[-STATS_MONTH_LIMIT:] if len(keys) > STATS_MONTH_LIMIT else keys
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    canonical_names = set(aliases.values())
    priority = [key for key, _ in ranked if key in canonical_names]
    normal = [key for key, _ in ranked if key not in canonical_names]
    return (priority + normal)[:STATS_GROUP_LIMIT]


async def _load_classifications(db: AsyncSession) -> dict[str, str]:
    """读取 AI 兜底分类缓存（{原始写法: 规范车间}）。"""
    result = await db.execute(
        select(WorkshopClassification).where(
            WorkshopClassification.is_deleted.is_(False)
        )
    )
    return {row.raw_value: row.canonical for row in result.scalars().all()}


async def _save_classifications(db: AsyncSession, mapping: dict[str, str]) -> None:
    """把 AI 归类结果写入缓存表（按原始写法 upsert）。"""
    result = await db.execute(
        select(WorkshopClassification).where(
            WorkshopClassification.is_deleted.is_(False)
        )
    )
    existing = {row.raw_value: row for row in result.scalars().all()}
    for raw_value, canonical in mapping.items():
        row = existing.get(raw_value)
        if row is None:
            db.add(WorkshopClassification(raw_value=raw_value, canonical=canonical))
        else:
            row.canonical = canonical
    await db.commit()


async def _ai_classify_workshops(
    values: list[str], canonical_names: list[str]
) -> dict[str, str]:
    """把未识别的位置描述批量交给 LLM，归入规范车间/部门清单。

    只对「别名与车间号规则都未命中」的写法调用；结果由调用方落缓存。
    LLM 不可用、输出无效时返回空映射，相关值保持原样（留在「其他」）。
    """
    if not values or not canonical_names:
        return {}
    try:
        from app.core.llm import llm_client
    except ImportError:  # pragma: no cover —— 依赖缺失时保守跳过
        return {}
    listing = "\n".join(f"{index}. {value}" for index, value in enumerate(values))
    messages = [
        {
            "role": "system",
            "content": (
                "你是工厂 EHS 数据管理员。厂区的规范车间/部门清单："
                f"{'、'.join(canonical_names)}。"
                "把每条位置描述归入清单中的一项，判断依据包括车间号、产线别名和"
                "功能区关键词（如仓库/库房→仓储部门，道路/后勤/办公楼/中控→行政部，"
                "循环水站/空压站/锅炉/动力→动力科，污水→污水车间）。"
                "确实无法判断的写「未分类」。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"位置描述清单（共 {len(values)} 条）：\n{listing}\n\n"
                '按序号返回 JSON：{"结果": [{"序号": 0, "车间": "清单中的名称"}]}'
            ),
        },
    ]
    try:
        data = await llm_client.chat_json(
            messages, expected_keys=["结果"], temperature=0.0
        )
    except Exception as exc:  # noqa: BLE001 —— LLM 不可用时保持原样
        logger.warning("AI 车间分类失败: %s", exc)
        return {}
    entries = data.get("results") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {}
    allowed = set(canonical_names)
    mapping: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        index = entry.get("序号")
        name = str(entry.get("车间") or "").strip()
        if isinstance(index, int) and 0 <= index < len(values):
            if name in allowed and name != "未分类":
                mapping[values[index]] = name
    return mapping


async def _resolve_text_bucket_keys(
    db: AsyncSession,
    field: FieldSchema,
    texts: list[str],
    aliases: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """文本字段「取值 → 分组键」：别名/车间号规则未命中的写法查 AI 分类缓存。

    返回 (取值→键 映射, 待 AI 兜底的未识别写法)。LLM 归类由后台任务完成，
    完成后下次刷新生效——绝不在统计请求内同步等待 LLM。
    """
    unique = list(dict.fromkeys(texts))
    keys: dict[str, str] = {}
    unrecognized: list[str] = []
    for text in unique:
        if not text:
            keys[text] = _UNFILLED_KEY
            continue
        key = normalize_workshop_name(text, aliases)
        if key != text:
            keys[text] = key
        else:
            unrecognized.append(text)
            keys[text] = text
    if not unrecognized:
        return keys, []
    cached = await _load_classifications(db)
    pending: list[str] = []
    for text in unrecognized:
        hit = (cached.get(text) or "").strip()
        if hit and hit != "未分类":
            keys[text] = hit
        elif hit:
            # AI 已判定无法归类：缓存防重复调用，分组保持原值
            keys[text] = text
        else:
            pending.append(text)
            keys[text] = text
    return keys, pending


async def _classify_pending_workshops(
    pending: list[str], aliases: dict[str, str]
) -> None:
    """后台执行 AI 兜底归类：批量调用 LLM 并把结果写入分类缓存。

    由统计接口通过后台任务触发（带分布式锁防并发重复调用），调用方
    立即返回，归类结果在下次刷新时生效。
    """
    if not pending:
        return
    if not await acquire_lock(_AI_CLASSIFY_LOCK_KEY, timeout=900):
        logger.info("AI 兜底车间分类已在执行，跳过本次触发")
        return
    try:
        canonical_names = sorted(set(aliases.values()))
        classified = await _ai_classify_workshops(pending, canonical_names)
        if classified:
            async with async_session_factory() as session:
                await _save_classifications(session, classified)
        logger.info(
            "AI 兜底车间分类完成: %d/%d 条", len(classified or {}), len(pending)
        )
    finally:
        await release_lock(_AI_CLASSIFY_LOCK_KEY)


def _schedule_ai_classify(pending: list[str], aliases: dict[str, str]) -> None:
    global _ai_classify_task
    if _ai_classify_task is not None and not _ai_classify_task.done():
        return  # 已有后台归类在跑
    _ai_classify_task = asyncio.create_task(
        _classify_pending_workshops(list(pending), dict(aliases))
    )


def _record_matches_keyword(
    record: dict[str, Any], columns: list[FieldSchema], needle: str
) -> bool:
    """解码记录的关键字匹配（与镜像 search_text 列同口径：任一字段包含）。"""
    lowered = needle.lower()
    return any(
        lowered in _search_text(field, record.get(field.name)).lower()
        for field in columns
    )


async def _filter_decoded_records(
    db: AsyncSession,
    records: list[dict[str, Any]],
    columns: list[FieldSchema],
    *,
    keyword: str | None,
    conditions: list[PageTableRecordCondition] | None,
    aliases: dict[str, str],
) -> list[dict[str, Any]]:
    """统计取数的记录级筛选（关键字 + 多条件，条件间 AND）。

    文本字段（部门/车间）按图表桶归一口径匹配（别名 + AI 兜底缓存），
    其余字段与列表查询的 _condition_matches 同语义；字段不在当前子表时
    跳过该条件（跨子表聚合时各表结构不同）。
    """
    needle = (keyword or "").strip()
    active = [c for c in (conditions or []) if c.value.strip()]
    text_key_maps: dict[str, dict[str, str]] = {}
    pending: list[str] = []
    for condition in active:
        target = next(
            (field for field in columns if field.name == condition.field), None
        )
        if (
            target is None
            or target.kind != KIND_TEXT
            or condition.field in text_key_maps
        ):
            continue
        row_texts = [
            _search_text(target, record.get(target.name)).strip()
            for record in records
        ]
        key_map, pending_part = await _resolve_text_bucket_keys(
            db, target, row_texts, aliases
        )
        text_key_maps[condition.field] = key_map
        pending.extend(pending_part)
    if pending:
        _schedule_ai_classify(pending, aliases)

    filtered: list[dict[str, Any]] = []
    for record in records:
        if needle and not _record_matches_keyword(record, columns, needle):
            continue
        matched_all = True
        for condition in active:
            target = next(
                (field for field in columns if field.name == condition.field), None
            )
            if target is None:
                continue
            value = record.get(target.name)
            expected = condition.value.strip()
            if target.kind == KIND_TEXT:
                text = _search_text(target, value).strip()
                bucket = text_key_maps.get(condition.field, {}).get(text, text)
                if bucket != expected and expected.lower() not in text.lower():
                    matched_all = False
                    break
            elif not _condition_matches(target, value, expected, condition.op):
                matched_all = False
                break
        if matched_all:
            filtered.append(record)
    return filtered


async def _collect_table_records(
    db: AsyncSession,
    model: SafetyPageFeishuConfig,
    app_token: str,
    bound: BoundTable,
    *,
    keyword: str | None = None,
    conditions: list[PageTableRecordCondition] | None = None,
) -> tuple[list[dict[str, Any]], list[FieldSchema]]:
    """取一张子表的全部解码记录（镜像优先，未同步走实时）+ 该表可见列。

    供 records 实时路径与跨表统计聚合复用；部门继承在两条路径都已应用。
    ``keyword``/``conditions`` 服务于仪表盘与列表同口径筛选（见
    _filter_decoded_records），不传时保持原取数行为。每条记录额外带
    ``_record_id`` 键（到期提醒推送记录定位用；统计/筛选只按字段名
    访问，不受该键影响）。
    """
    columns = await _visible_columns(model, app_token, bound.table_id)
    has_filters = bool((keyword or "").strip()) or any(
        condition.value.strip() for condition in (conditions or [])
    )
    if model.is_mirrored and model.last_synced_at is not None:
        mirror_rows = (
            await db.execute(
                select(
                    SafetyPageTableMirrorRecord.record_id,
                    SafetyPageTableMirrorRecord.fields,
                ).where(
                    SafetyPageTableMirrorRecord.page_key == model.page_key,
                    SafetyPageTableMirrorRecord.table_id == bound.table_id,
                    SafetyPageTableMirrorRecord.is_deleted.is_(False),
                )
            )
        ).all()
        records = [
            dict(fields or {}, _record_id=record_id)
            for record_id, fields in mirror_rows
        ]
        if has_filters:
            records = await _filter_decoded_records(
                db,
                records,
                columns,
                keyword=keyword,
                conditions=conditions,
                aliases=_workshop_aliases_of(model.workshop_aliases),
            )
        return records, columns

    raw_rows = await _fetch_raw_records(
        app_token,
        bound.table_id,
        fetch_sort_field=_default_date_field(columns),
    )
    raw_rows = raw_rows[:MAX_RECORDS]
    full_schema = await _load_field_schema(app_token, bound.table_id)
    dept_field = _dept_field_of(full_schema)
    dept_map = _resolve_dept_inheritance(full_schema, raw_rows)
    decoded: list[dict[str, Any]] = []
    for row in raw_rows:
        record_id = str(row.get("record_id") or "")
        fields = row.get("fields")
        if not record_id or not isinstance(fields, dict):
            continue
        row_decoded = decode_record_fields(columns, fields)
        _apply_inherited_dept(dept_field, dept_map, record_id, row_decoded)
        row_decoded["_record_id"] = record_id
        decoded.append(row_decoded)
    if has_filters:
        decoded = await _filter_decoded_records(
            db,
            decoded,
            columns,
            keyword=keyword,
            conditions=conditions,
            aliases=_workshop_aliases_of(model.workshop_aliases),
        )
    return decoded, columns


async def get_page_table_stats(
    db: AsyncSession,
    page_key: str,
    group_by: list[str] | None = None,
    table_id: str | None = None,
    *,
    keyword: str | None = None,
    conditions: list[PageTableRecordCondition] | None = None,
    due_field: str | None = None,
    close_field: str | None = None,
) -> PageTableStatsResponse:
    """按维度聚合记录（月份 / 车间号 / 选项等），供页面顶部仪表盘使用。

    单表模式（``table_id`` 给定或页面未配子表）：聚合该表。
    汇总模式（多页签页面且未指定 ``table_id``）：聚合全部绑定子表——
    每个分组字段只统计「存在该字段的子表」，日期分组只取该字段为日期
    类型的子表（同一字段在不同子表可能是文本，如 2024 年的检查内容）。
    ``keyword``/``conditions`` 与列表查询同口径，仪表盘随筛选联动。
    """
    definition, model, app_token, primary_table = await _load_config_or_raise(
        db, page_key
    )
    bound_tables = _bound_tables(definition, model)
    aggregate_mode = table_id is None and len(bound_tables) > 1
    if aggregate_mode:
        tables_for_stats = bound_tables
        target = bound_tables[0]
    else:
        target = _resolve_bound_table(definition, model, table_id)
        tables_for_stats = [target]

    # 逐表取数（汇总模式下并发取全部子表）
    per_table: list[tuple[BoundTable, list[dict[str, Any]], list[FieldSchema]]] = []
    if aggregate_mode:
        results = await asyncio.gather(
            *[
                _collect_table_records(
                    db, model, app_token, bound, keyword=keyword, conditions=conditions
                )
                for bound in tables_for_stats
            ],
            return_exceptions=True,
        )
        for bound, result in zip(tables_for_stats, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "统计子表取数失败（跳过）: page=%s 表=%s err=%s",
                    page_key,
                    bound.tab_name,
                    result,
                )
                continue
            records, columns = result
            per_table.append((bound, records, columns))
    else:
        if model.is_mirrored and model.last_synced_at is None:
            _schedule_mirror_sync(page_key)
        records, columns = await _collect_table_records(
            db, model, app_token, target, keyword=keyword, conditions=conditions
        )
        per_table.append((target, records, columns))

    primary_columns = next(
        (columns for _, _, columns in per_table if columns), []
    )

    requested = [str(name).strip() for name in (group_by or []) if str(name).strip()]
    if requested:
        if aggregate_mode:
            # 汇总模式：字段只需存在于任一绑定子表
            known = {field.name for _, _, columns in per_table for field in columns}
        else:
            known = {field.name for field in primary_columns}
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise AppException(
                message=f"分组字段不在当前表格中：{'、'.join(unknown)}", status_code=400
            )
        group_names = requested
    else:
        group_names = [
            field.name
            for field in primary_columns
            if field.name in _default_stats_fields(primary_columns)
        ]

    total = sum(len(records) for _, records, _ in per_table)
    aliases = _workshop_aliases_of(model.workshop_aliases)
    groups: list[PageTableStatGroup] = []
    for group_name in group_names:
        # 每张子表里该字段的定义（类型可能不同：如检查内容 文本 vs 日期）
        field_defs = [
            (bound, next((f for f in columns if f.name == group_name), None))
            for bound, _, columns in per_table
        ]
        hits = [(bound, f) for bound, f in field_defs if f is not None]
        if not hits:
            continue
        reference = hits[0][1]
        counter: Counter[str] = Counter()
        pending_all: list[str] = []
        is_date_group = reference.kind == KIND_DATE
        for bound, field in hits:
            records = next(
                records for b, records, _ in per_table if b.table_id == bound.table_id
            )
            # 日期分组只统计该字段确实是日期类型的子表；文本型检查内容
            # （2024 年等）不产生月份桶，避免把描述文本当年月
            if is_date_group and field.kind != KIND_DATE:
                continue
            if field.kind == KIND_TEXT:
                row_texts = [
                    _search_text(field, record.get(field.name)).strip()
                    for record in records
                ]
                key_map, pending = await _resolve_text_bucket_keys(
                    db, field, row_texts, aliases
                )
                pending_all.extend(pending)
                counter.update(key_map[text] for text in row_texts)
            else:
                counter.update(
                    _stat_bucket_key(field, record.get(field.name), aliases)
                    for record in records
                )
        if pending_all:
            # 后台触发 AI 兜底归类；本次返回未分类结果，下次刷新生效
            _schedule_ai_classify(pending_all, aliases)
        top_keys = _stat_top_keys(counter, reference, aliases)
        if reference.kind == KIND_DATE:
            # 月份：按时间升序展示；超过上限时只保留最近几个月
            buckets = [
                PageTableStatBucket(key=key, count=counter[key]) for key in top_keys
            ]
            if _UNFILLED_KEY in counter:
                buckets.append(
                    PageTableStatBucket(key=_UNFILLED_KEY, count=counter[_UNFILLED_KEY])
                )
            mode = "month"
        else:
            buckets = [
                PageTableStatBucket(key=key, count=counter[key]) for key in top_keys
            ]
            overflow = sum(
                count for key, count in counter.items() if key not in top_keys
            )
            if overflow:
                buckets.append(PageTableStatBucket(key="其他", count=overflow))
            mode = "value"
        groups.append(
            PageTableStatGroup(
                field=reference.name, kind=reference.kind, mode=mode, buckets=buckets
            )
        )

    # 到期分布（仪表盘到期卡片）：未关闭记录按目标完成日期归桶；
    # 只统计该字段为日期类型的子表（与到期提醒推送同口径）。
    due_summary: PageTableDueSummary | None = None
    if due_field and close_field:
        from app.modules.safety.service.hazard_due_reminder import summarize_due

        due_records = [
            record
            for bound, records, columns in per_table
            if any(
                field.name == due_field and field.kind == KIND_DATE
                for field in columns
            )
            for record in records
        ]
        due_summary = PageTableDueSummary(
            **summarize_due(due_records, due_field, close_field)
        )

    return PageTableStatsResponse(
        page_key=page_key,
        page_name=definition.page_name,
        total=total,
        groups=groups,
        due_summary=due_summary,
    )


async def list_page_table_field_values(
    db: AsyncSession,
    page_key: str,
    field: str,
    table_id: str | None = None,
) -> PageTableFieldValuesResponse:
    """字段去重可选值（含出现次数），供筛选下拉框的选项使用。

    人员字段按个人姓名拆分计数；部门/车间等文本字段与图表桶同口径
    （别名归一 + AI 兜底缓存）；选项/日期等其他字段按展示文本归组。
    镜像数据源；未同步过时返回空列表。
    """
    definition, model, app_token, _primary = await _load_config_or_raise(
        db, page_key
    )
    bound = _resolve_bound_table(definition, model, table_id)
    field_name = field.strip()
    if not field_name:
        raise AppException(message="请指定要枚举的字段名", status_code=400)
    columns = await _visible_columns(model, app_token, bound.table_id)
    target = next((f for f in columns if f.name == field_name), None)
    if target is None:
        raise AppException(
            message=f"字段「{field_name}」不在当前表格中", status_code=400
        )

    counter: Counter[str] = Counter()
    values: list[dict[str, Any]] = []
    if model.is_mirrored and model.last_synced_at is not None:
        values = [
            dict(fields or {})
            for fields in (
                await db.execute(
                    select(SafetyPageTableMirrorRecord.fields).where(
                        SafetyPageTableMirrorRecord.page_key == model.page_key,
                        SafetyPageTableMirrorRecord.table_id == bound.table_id,
                        SafetyPageTableMirrorRecord.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        ]

    aliases = _workshop_aliases_of(model.workshop_aliases)
    pending: list[str] = []
    if target.kind == KIND_PERSON:
        for record in values:
            items = record.get(field_name)
            for item in items if isinstance(items, list) else []:
                name = (
                    str(item.get("name") or "").strip()
                    if isinstance(item, dict)
                    else ""
                )
                if name:
                    counter[name] += 1
    elif target.kind == KIND_TEXT:
        row_texts = [
            _search_text(target, record.get(field_name)).strip()
            for record in values
        ]
        key_map, pending_part = await _resolve_text_bucket_keys(
            db, target, row_texts, aliases
        )
        pending.extend(pending_part)
        if pending_part:
            _schedule_ai_classify(pending_part, aliases)
        for text in row_texts:
            key = key_map.get(text, text)
            if key:
                counter[key] += 1
    else:
        for record in values:
            key = _stat_bucket_key(target, record.get(field_name), aliases)
            if key and key != _UNFILLED_KEY:
                counter[key] += 1

    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return PageTableFieldValuesResponse(
        page_key=page_key,
        field=field_name,
        table_id=bound.table_id,
        values=[
            PageTableFieldValueCount(value=key, count=count)
            for key, count in ranked[:MAX_FIELD_VALUES]
        ],
    )


async def list_page_table_tabs(
    db: AsyncSession, page_key: str
) -> list[PageTableTab]:
    """页签清单：主绑定在前 + sub_tables 依次在后，含各子表镜像记录数。"""
    definition, model, _, _ = await _load_config_or_raise(db, page_key)
    tables = _bound_tables(definition, model)
    counts: dict[str, int] = {}
    if model.is_mirrored and model.last_synced_at is not None:
        rows = (
            (
                await db.execute(
                    select(
                        SafetyPageTableMirrorRecord.table_id,
                        func.count(),
                    ).where(
                        SafetyPageTableMirrorRecord.page_key == page_key,
                        SafetyPageTableMirrorRecord.is_deleted.is_(False),
                    ).group_by(SafetyPageTableMirrorRecord.table_id)
                )
            )
            .all()
        )
        counts = {table_id: count for table_id, count in rows}
    return [
        PageTableTab(
            table_id=bound.table_id,
            tab_name=bound.tab_name,
            is_primary=bound.is_primary,
            record_count=counts.get(bound.table_id, 0),
        )
        for bound in tables
    ]


# ── 绑定测试与链接解析 ──


async def test_page_feishu_config(
    db: AsyncSession,
    page_key: str,
) -> PageFeishuConfigTestResult:
    """校验绑定：读字段 + 读记录数，并把结果写回配置行。"""
    definition = _require_definition(page_key)
    try:
        model = await _get_config_model(db, page_key)
    except (OperationalError, ProgrammingError) as exc:
        if _is_config_table_missing(exc):
            raise AppException(
                message="页面表格绑定数据表未创建，请先执行安全模块数据库迁移"
            ) from exc
        raise
    app_token, table_id = _require_binding(definition, model)
    assert model is not None
    checked_at = datetime.now(UTC)

    async def _record(
        success: bool, message: str, fields: list[FieldSchema], count: int
    ) -> PageFeishuConfigTestResult:
        model.last_test_status = "success" if success else "failed"
        model.last_test_error = None if success else message[:500]
        model.last_tested_at = checked_at
        model.last_test_field_count = len(fields) if success else None
        model.last_test_record_count = count if success else None
        await db.commit()
        return PageFeishuConfigTestResult(
            success=success,
            message=message,
            checked_at=checked_at,
            field_count=len(fields) if success else 0,
            record_count=count if success else 0,
            fields=[
                PageFeishuFieldSummary(
                    name=field.name, kind=field.kind, editable=field.editable
                )
                for field in fields
            ],
        )

    try:
        schema = await _load_field_schema(app_token, table_id, refresh=True)
    except AppException as exc:
        return await _record(False, exc.message, [], 0)

    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
    rows, error = await client.search_records_with_result(page_size=1, max_pages=1)
    if error:
        return await _record(False, f"读取记录失败：{error}", schema, 0)
    return await _record(
        True,
        f"绑定正常：读取到 {len(schema)} 个字段",
        schema,
        len(rows),
    )


async def resolve_page_feishu_url(
    db: AsyncSession,
    url: str,
) -> ResolvedPageFeishuUrl:
    """解析粘贴的多维表格链接：取出 app_token / table_id / view_id 并列出子表。"""
    del db  # 解析只用飞书应用凭证，不依赖本地数据
    raw = (url or "").strip()
    if not raw:
        raise AppException(message="请填写多维表格链接", status_code=400)
    is_wiki = bool(_WIKI_LINK_RE.search(raw))
    table_id: str | None = None
    view_id: str | None = None
    app_token: str | None = None
    try:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(raw)
        query = parse_qs(parsed.query)
        table_id = next(iter(query.get("table") or ()), None)
        view_id = next(iter(query.get("view") or ()), None)
        base_match = _BASE_LINK_RE.search(parsed.path)
        if base_match:
            app_token = base_match.group(1)
    except ValueError as exc:
        raise AppException(message="无法解析该链接", status_code=400) from exc

    if is_wiki:
        node_token = _WIKI_LINK_RE.search(raw)
        config = await load_safety_feishu_runtime_config()
        if node_token is None or config is None:
            raise AppException(
                message="知识库链接需要先配置飞书应用凭证才能解析",
                status_code=400,
            )
        from app.platform.integrations.feishu.utils import (
            resolve_wiki_bitable_app_token,
        )

        app_token = await resolve_wiki_bitable_app_token(
            app_id=config.app_id,
            app_secret=config.app_secret,
            node_token=node_token.group(1),
        )
    if not app_token:
        raise AppException(
            message="链接中未找到 app_token，请使用多维表格 /base/ 或 /wiki/ 链接",
            status_code=400,
        )

    client = SafetyBitableClient(app_token=app_token, table_id=table_id or "")
    tables = await client.list_tables(app_token)
    return ResolvedPageFeishuUrl(
        app_token=app_token,
        table_id=table_id,
        view_id=view_id,
        is_wiki=is_wiki,
        tables=[
            ResolvedFeishuTable(
                table_id=str(item.get("table_id") or ""),
                table_name=str(item.get("name") or ""),
            )
            for item in tables
            if item.get("table_id")
        ],
    )
