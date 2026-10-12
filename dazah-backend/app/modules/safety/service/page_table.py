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
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
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
    KIND_SELECT,
    KIND_TEXT,
    FieldCodecError,
    FieldSchema,
    attachment_field_or_error,
    build_field_schema,
    decode_record_fields,
    encode_record_fields,
    existing_attachment_tokens,
)
from app.modules.safety.feishu.runtime_config import load_safety_feishu_runtime_config
from app.modules.safety.models import (
    SafetyPageFeishuConfig,
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
    PageTableAttachmentItem,
    PageTableAttachmentUploadResponse,
    PageTableColumn,
    PageTableRecord,
    PageTableRecordsResponse,
    PageTableStatBucket,
    PageTableStatGroup,
    PageTableStatsResponse,
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
_UNFILLED_KEY = "（未填写）"
# AI 兜底归类的后台任务状态（进程内防重入；跨实例由 Redis 锁兜底）
_ai_classify_task: asyncio.Task | None = None
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
        is_enabled=model.is_enabled,
        is_configured=bool(_clean(model.app_token) and _clean(model.table_id)),
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
    logger.info(
        "DEBUG 保存页面绑定入口: page=%s fields_set=%s 别名条数=%s",
        page_key,
        sorted(data.model_fields_set),
        len(data.workshop_aliases or {}),
    )
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
        if "is_enabled" in data.model_fields_set and data.is_enabled is not None:
            model.is_enabled = data.is_enabled
        # 绑定变化后旧的测试结论与字段缓存都不再适用
        model.last_test_status = None
        model.last_test_error = None
        model.last_tested_at = None
        model.last_test_field_count = None
        model.last_test_record_count = None
        await db.commit()
        await db.refresh(model)
        if model.app_token and model.table_id:
            await cache_delete(_field_cache_key(model.app_token, model.table_id))
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
    raw_fields = await client.list_fields()
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


async def _fetch_raw_records(app_token: str, table_id: str) -> list[dict[str, Any]]:
    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
    rows, error = await client.search_records_with_result(
        page_size=100,
        max_pages=max(1, MAX_RECORDS // 100),
    )
    if error:
        raise AppException(
            message=f"读取多维表格记录失败：{error}", status_code=502
        )
    return rows


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
) -> PageTableRecordsResponse:
    """返回列定义与分页记录（列来自飞书 schema，过滤/排序/分页在服务端完成）。

    ``filter_field``/``filter_value`` 服务于仪表盘下钻：匹配规则与统计聚合
    一致（月份前缀、车间号归一、选项名），保证点图表看到的明细和数字对得上。
    """
    definition, model, app_token, table_id = await _load_config_or_raise(db, page_key)
    schema = await _load_field_schema(app_token, table_id)
    hidden = {str(name) for name in (model.hidden_field_names or [])}
    columns = [field for field in schema if field.name not in hidden]
    aliases = _workshop_aliases_of(model.workshop_aliases)

    raw_rows = await _fetch_raw_records(app_token, table_id)
    truncated = len(raw_rows) > MAX_RECORDS
    raw_rows = raw_rows[:MAX_RECORDS]

    decoded_rows: list[PageTableRecord] = []
    for row in raw_rows:
        record_id = str(row.get("record_id") or "")
        if not record_id:
            continue
        raw_fields = row.get("fields")
        decoded_rows.append(
            PageTableRecord(
                record_id=record_id,
                fields=decode_record_fields(
                    columns, raw_fields if isinstance(raw_fields, dict) else {}
                ),
            )
        )

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

    dimension = (filter_field or "").strip()
    dimension_value = (filter_value or "").strip()
    if dimension and dimension_value:
        target = next(
            (field for field in columns if field.name == dimension), None
        )
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
            decoded_rows = [
                record
                for record in decoded_rows
                if row_keys[record.record_id] not in kept_keys
            ]
        else:
            decoded_rows = [
                record
                for record in decoded_rows
                if row_keys[record.record_id] == dimension_value
            ]

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
    )


# ── 记录写入 ──


async def update_page_table_record(
    db: AsyncSession,
    page_key: str,
    record_id: str,
    values: dict[str, Any],
    *,
    user_id: uuid.UUID | None = None,
) -> PageTableRecord:
    """把页面提交的字段值回写到飞书多维表格。"""
    _, model, app_token, table_id = await _load_config_or_raise(db, page_key)
    if not values:
        raise AppException(message="没有需要保存的字段", status_code=400)
    schema = await _load_field_schema(app_token, table_id)
    try:
        encoded = encode_record_fields(schema, values)
    except FieldCodecError as exc:
        raise AppException(message=str(exc), status_code=400) from exc

    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
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
            "table_id": table_id,
        },
    )

    # 回读一次，让页面拿到飞书侧的真实结果（公式/关联等字段由飞书计算）
    raw_fields = await client.get_record(record_id)
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
) -> PageTableAttachmentUploadResponse:
    """上传附件到飞书并在记录附件字段上追加（不覆盖已有附件）。"""
    _, model, app_token, table_id = await _load_config_or_raise(db, page_key)
    schema = await _load_field_schema(app_token, table_id)
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

    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
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
) -> tuple[bytes, str, str]:
    """代理下载附件。

    先校验该 file_token 确实属于这条记录的该附件字段，再回源飞书，避免
    通过构造 token 读取其它记录/表格的附件。
    """
    _, _, app_token, table_id = await _load_config_or_raise(db, page_key)
    client = SafetyBitableClient(app_token=app_token, table_id=table_id)
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

    content = await client.download_attachment_from_url(str(matched.get("url") or ""))
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


async def get_page_table_stats(
    db: AsyncSession,
    page_key: str,
    group_by: list[str] | None = None,
) -> PageTableStatsResponse:
    """按维度聚合整表记录（月份 / 车间号 / 选项等），供页面顶部仪表盘使用。"""
    definition, model, app_token, table_id = await _load_config_or_raise(db, page_key)
    schema = await _load_field_schema(app_token, table_id)
    hidden = {str(name) for name in (model.hidden_field_names or [])}
    columns = [field for field in schema if field.name not in hidden]

    requested = [str(name).strip() for name in (group_by or []) if str(name).strip()]
    if requested:
        known = {field.name for field in columns}
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise AppException(
                message=f"分组字段不在当前表格中：{'、'.join(unknown)}", status_code=400
            )
        group_fields = [
            next(f for f in columns if f.name == name) for name in requested
        ]
    else:
        group_fields = [f for f in columns if f.name in _default_stats_fields(columns)]

    raw_rows = await _fetch_raw_records(app_token, table_id)
    decoded = [
        decode_record_fields(
            columns, row.get("fields") if isinstance(row.get("fields"), dict) else {}
        )
        for row in raw_rows[:MAX_RECORDS]
    ]

    groups: list[PageTableStatGroup] = []
    aliases = _workshop_aliases_of(model.workshop_aliases)
    for field in group_fields:
        if field.kind == KIND_TEXT:
            row_texts = [
                _search_text(field, record.get(field.name)).strip()
                for record in decoded
            ]
            key_map, pending = await _resolve_text_bucket_keys(
                db, field, row_texts, aliases
            )
            if pending:
                # 后台触发 AI 兜底归类；本次返回未分类结果，下次刷新生效
                _schedule_ai_classify(pending, aliases)
            counter: Counter[str] = Counter(key_map[text] for text in row_texts)
        else:
            counter: Counter[str] = Counter(
                _stat_bucket_key(field, record.get(field.name), aliases)
                for record in decoded
            )
        top_keys = _stat_top_keys(counter, field, aliases)
        if field.kind == KIND_DATE:
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
                field=field.name, kind=field.kind, mode=mode, buckets=buckets
            )
        )

    return PageTableStatsResponse(
        page_key=page_key,
        page_name=definition.page_name,
        total=len(decoded),
        groups=groups,
    )


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
        table_id = (query.get("table") or [None])[0]
        view_id = (query.get("view") or [None])[0]
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
