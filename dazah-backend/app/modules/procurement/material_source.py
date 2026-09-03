"""Feishu-backed material code lookup for procurement forms."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import cache_get, cache_set
from app.modules.procurement.models import MaterialCatalogRecord, MaterialSourceConfig
from app.modules.procurement.repository import (
    MaterialCatalogRepository,
    MaterialSourceConfigRepository,
)
from app.modules.procurement.schemas import MaterialSourceConfigUpsert
from app.platform.identity.public_api import (
    FeishuAppCredentials,
)
from app.platform.integrations.feishu.bitable import (
    BitableClient,
    BitableRecordPage,
)
from app.platform.integrations.feishu.fields import extract_text
from app.platform.integrations.feishu.utils import (
    BitableReference,
    parse_bitable_url,
)

logger = logging.getLogger(__name__)

MATERIAL_SOURCE_CONFIG_KEY = "material-master"
MATERIAL_OPTIONS_CACHE_TTL = 60
MAX_MATERIAL_OPTIONS = 20
MATERIAL_RECORD_PAGE_SIZE = 500
MAX_MATERIAL_SCAN_PAGES = 20
BITABLE_TEXT_FIELD_TYPE = 1
MAX_MATERIAL_OPTION_PAGE_SIZE = 500
# 联想请求必须有界，但飞书 records/search 在数据量大的表上可能超过 3 秒，
# 预算过紧会把正常请求误判为超时；异步请求不占用 worker，适度放宽单请求
# 和总预算换取联想可用性，前端超时（15 秒）仍兜底整体等待。
MATERIAL_OPTION_REQUEST_TIMEOUT_SECONDS = 8.0
MATERIAL_OPTION_TOTAL_TIMEOUT_SECONDS = 12.0
MATERIAL_OPTION_COLLECT_FACTOR = 5
MATERIAL_CODE_FIELD = "物料编码"
MATERIAL_DESCRIPTION_FIELD = "物料说明"
SPECIFICATION_FIELD = "规格型号"
LEGACY_SPECIFICATION_FIELD = "规则型号"
MATERIAL_UNIT_FIELD = "主要单位"
MATERIAL_TEMPLATE_FIELD = "物料模板"
MATERIAL_CATEGORY_FIELD = "物料大类"
MATERIAL_SUBCATEGORY_FIELD = "物料小类"
MATERIAL_COST_CATEGORY_FIELD = "物料成本大类"
# 可选字段：表里没有时不阻断同步，识别不到则留空。
# (配置字段名, 飞书候选名, 显示名称)
OPTIONAL_MATERIAL_FIELD_SPECS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("material_unit_field", (MATERIAL_UNIT_FIELD,), "主要单位"),
    ("material_template_field", (MATERIAL_TEMPLATE_FIELD,), "物料模板"),
    ("material_category_field", (MATERIAL_CATEGORY_FIELD,), "物料大类"),
    ("material_subcategory_field", (MATERIAL_SUBCATEGORY_FIELD,), "物料小类"),
    ("material_cost_category_field", (MATERIAL_COST_CATEGORY_FIELD,), "物料成本大类"),
)


class MaterialSourceError(Exception):
    """Expected material source failure safe to expose to an API caller."""

    status_code = 502

    def __init__(self, message: str) -> None:
        self.public_message = message
        super().__init__(message)


class MaterialSourceValidationError(MaterialSourceError):
    status_code = 400


class MaterialSourceFieldsError(MaterialSourceError):
    status_code = 422


class MaterialSourceNotConfiguredError(MaterialSourceError):
    status_code = 404


class MaterialSourceCredentialsError(MaterialSourceError):
    status_code = 503


class MaterialSourcePermissionError(MaterialSourceError):
    status_code = 502


class MaterialSourceTimeoutError(MaterialSourceError):
    status_code = 504


class MaterialSourceConflictError(MaterialSourceError):
    status_code = 409


class MaterialSourceUpstreamError(MaterialSourceError):
    """飞书 API 返回的临时性业务错误（Fail、频率超限），同步路径会重试。"""

    status_code = 502


@dataclass(frozen=True)
class MaterialSourceProbe:
    source_url: str
    app_token: str
    table_id: str
    view_id: str | None
    material_code_field: str
    material_code_field_type: int | None
    material_description_field: str
    rule_model_field: str
    material_unit_field: str | None
    material_template_field: str | None
    material_category_field: str | None
    material_subcategory_field: str | None
    material_cost_category_field: str | None
    available_fields: list[str]
    status: str
    error_message: str | None
    tested_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "app_token": self.app_token,
            "table_id": self.table_id,
            "view_id": self.view_id,
            "material_code_field": self.material_code_field,
            "material_description_field": self.material_description_field,
            "rule_model_field": self.rule_model_field,
            "material_unit_field": self.material_unit_field,
            "material_template_field": self.material_template_field,
            "material_category_field": self.material_category_field,
            "material_subcategory_field": self.material_subcategory_field,
            "material_cost_category_field": self.material_cost_category_field,
            "available_fields": self.available_fields,
            "status": self.status,
            "error_message": self.error_message,
            "tested_at": self.tested_at,
        }


@dataclass(frozen=True)
class MaterialSourceSync:
    config: MaterialSourceConfig
    synced_count: int
    deactivated_count: int


MATERIAL_SYNC_PAGE_SIZE = 500
MAX_MATERIAL_SYNC_PAGES = 200
MATERIAL_SYNC_PAGE_RETRIES = 3
MATERIAL_SYNC_RETRY_BACKOFF_SECONDS = 1.0
# 大批量同步的单页请求超时：飞书 search 在数据量大的表上可能超过默认 15 秒，
# 超时会被误判为网络故障并重试，放宽后慢但正常的页面一次就能拉完。
MATERIAL_SYNC_PAGE_TIMEOUT_SECONDS = 60.0


def _resolve_field(
    available_fields: list[str],
    requested: str | None,
    candidates: tuple[str, ...],
    label: str,
) -> str:
    available = {
        field.strip(): field.strip() for field in available_fields if field.strip()
    }
    if requested and requested.strip():
        normalized = requested.strip()
        if normalized not in available:
            raise MaterialSourceFieldsError(
                f"多维表格缺少配置的{label}字段：{normalized}"
            )
        return available[normalized]

    for candidate in candidates:
        if candidate in available:
            return available[candidate]

    raise MaterialSourceFieldsError(f"多维表格缺少{label}字段，请配置“{candidates[0]}”")


def _resolve_optional_field(
    available_fields: list[str],
    requested: str | None,
    candidates: tuple[str, ...],
    label: str,
) -> str | None:
    """解析可选字段：显式配置但缺失时报错，自动识别缺失时返回 None。"""
    available = {
        field.strip(): field.strip() for field in available_fields if field.strip()
    }
    if requested and requested.strip():
        normalized = requested.strip()
        if normalized not in available:
            raise MaterialSourceFieldsError(
                f"多维表格缺少配置的{label}字段：{normalized}"
            )
        return available[normalized]
    for candidate in candidates:
        if candidate in available:
            return available[candidate]
    return None


@dataclass(frozen=True)
class MaterialFieldMapping:
    material_code_field: str
    material_code_field_type: int | None
    material_description_field: str
    rule_model_field: str
    available_fields: list[str]
    material_unit_field: str | None
    material_template_field: str | None
    material_category_field: str | None
    material_subcategory_field: str | None
    material_cost_category_field: str | None


def _resolve_field_mapping(
    fields: list[dict[str, Any]],
    payload: MaterialSourceConfigUpsert,
) -> MaterialFieldMapping:
    available_fields = [
        str(item.get("field_name", "")).strip()
        for item in fields
        if isinstance(item, dict) and str(item.get("field_name", "")).strip()
    ]
    material_code_field = _resolve_field(
        available_fields,
        payload.material_code_field,
        (MATERIAL_CODE_FIELD,),
        "物料编码",
    )
    material_description_field = _resolve_field(
        available_fields,
        payload.material_description_field,
        (MATERIAL_DESCRIPTION_FIELD,),
        "物料说明",
    )
    rule_model_field = _resolve_field(
        available_fields,
        payload.rule_model_field,
        (SPECIFICATION_FIELD, LEGACY_SPECIFICATION_FIELD),
        "规格型号",
    )
    material_code_field_type = next(
        (
            int(item["type"])
            for item in fields
            if isinstance(item, dict)
            and str(item.get("field_name", "")).strip() == material_code_field
            and isinstance(item.get("type"), (int, str))
            and str(item["type"]).isdigit()
        ),
        None,
    )
    optional_fields = {
        attr: _resolve_optional_field(
            available_fields,
            getattr(payload, attr),
            candidates,
            label,
        )
        for attr, candidates, label in OPTIONAL_MATERIAL_FIELD_SPECS
    }
    return MaterialFieldMapping(
        material_code_field=material_code_field,
        material_code_field_type=material_code_field_type,
        material_description_field=material_description_field,
        rule_model_field=rule_model_field,
        available_fields=available_fields,
        material_unit_field=optional_fields["material_unit_field"],
        material_template_field=optional_fields["material_template_field"],
        material_category_field=optional_fields["material_category_field"],
        material_subcategory_field=optional_fields["material_subcategory_field"],
        material_cost_category_field=optional_fields["material_cost_category_field"],
    )


def _validate_reference(source_url: str) -> BitableReference:
    reference = parse_bitable_url(source_url)
    if not reference.app_token or not reference.table_id:
        raise MaterialSourceValidationError(
            "飞书多维表格链接无法解析，请确认包含 /base/{app_token} 和 table 参数"
        )
    return reference


def _material_source_disabled_error() -> MaterialSourceCredentialsError:
    return MaterialSourceCredentialsError(
        "采购飞书同步暂未启用，待配置独立业务应用后恢复"
    )


def ensure_material_source_sync_enabled() -> None:
    """采购独立应用接入前，禁止启动远程同步。"""
    raise _material_source_disabled_error()


async def _get_credentials(db: AsyncSession) -> FeishuAppCredentials:
    raise _material_source_disabled_error()


async def _run_feishu[T](
    operation: str,
    callback: Callable[[], Awaitable[T]],
) -> T:
    try:
        return await callback()
    except httpx.TimeoutException as exc:
        raise MaterialSourceTimeoutError("飞书多维表格请求超时") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            raise MaterialSourcePermissionError(
                "平台飞书应用无权访问该多维表格"
            ) from exc
        raise MaterialSourcePermissionError("飞书多维表格访问失败") from exc
    except httpx.RequestError as exc:
        raise MaterialSourcePermissionError("无法连接飞书多维表格") from exc
    except RuntimeError as exc:
        message = str(exc)
        if "not configured" in message.lower():
            raise MaterialSourceCredentialsError(
                "平台尚未配置可用的飞书企业自建应用"
            ) from exc
        # 飞书 API 业务错误：Fail（1254002）和频率超限（99991600）是
        # 临时性失败，同步路径会对这类错误重试；其余按确定性错误处理。
        if "code=1254002" in message or "code=99991600" in message:
            raise MaterialSourceUpstreamError(
                "飞书多维表格暂时繁忙，请稍后重试"
            ) from exc
        raise MaterialSourcePermissionError("飞书多维表格访问失败") from exc
    except MaterialSourceError:
        # 回调中明确抛出的业务错误直接透传，避免被包装成通用访问失败
        raise
    except Exception as exc:
        logger.error(
            "Feishu material source operation failed: %s (%s)",
            operation,
            type(exc).__name__,
        )
        raise MaterialSourcePermissionError("飞书多维表格访问失败") from exc


async def probe_material_source(
    db: AsyncSession,
    payload: MaterialSourceConfigUpsert,
) -> MaterialSourceProbe:
    reference = _validate_reference(payload.source_url)
    assert reference.app_token is not None
    assert reference.table_id is not None
    credentials = await _get_credentials(db)
    client = BitableClient(
        app_token=reference.app_token,
        app_id=credentials.app_id,
        app_secret=credentials.app_secret,
    )
    fields = await _run_feishu(
        "list_fields",
        lambda: client.list_fields(reference.table_id or ""),
    )
    mapping = _resolve_field_mapping(fields, payload)
    return MaterialSourceProbe(
        source_url=payload.source_url.strip(),
        app_token=reference.app_token,
        table_id=reference.table_id,
        view_id=reference.view_id,
        material_code_field=mapping.material_code_field,
        material_code_field_type=mapping.material_code_field_type,
        material_description_field=mapping.material_description_field,
        rule_model_field=mapping.rule_model_field,
        material_unit_field=mapping.material_unit_field,
        material_template_field=mapping.material_template_field,
        material_category_field=mapping.material_category_field,
        material_subcategory_field=mapping.material_subcategory_field,
        material_cost_category_field=mapping.material_cost_category_field,
        available_fields=mapping.available_fields,
        status="success",
        error_message=None,
        tested_at=datetime.now(UTC),
    )


def _config_from_probe(
    probe: MaterialSourceProbe,
    *,
    user_id: UUID,
) -> MaterialSourceConfig:
    return MaterialSourceConfig(
        config_key=MATERIAL_SOURCE_CONFIG_KEY,
        source_url=probe.source_url,
        app_token=probe.app_token,
        table_id=probe.table_id,
        view_id=probe.view_id,
        material_code_field=probe.material_code_field,
        material_code_field_type=probe.material_code_field_type,
        material_description_field=probe.material_description_field,
        rule_model_field=probe.rule_model_field,
        material_unit_field=probe.material_unit_field,
        material_template_field=probe.material_template_field,
        material_category_field=probe.material_category_field,
        material_subcategory_field=probe.material_subcategory_field,
        material_cost_category_field=probe.material_cost_category_field,
        last_test_status=probe.status,
        last_test_error=probe.error_message,
        last_tested_at=probe.tested_at,
        created_by=user_id,
        updated_by=user_id,
    )


async def get_material_source_config(
    db: AsyncSession,
) -> MaterialSourceConfig | None:
    return await MaterialSourceConfigRepository(db).get()


async def save_material_source_config(
    db: AsyncSession,
    payload: MaterialSourceConfigUpsert,
    *,
    user_id: UUID,
) -> MaterialSourceConfig:
    probe = await probe_material_source(db, payload)
    config = _config_from_probe(probe, user_id=user_id)
    repository = MaterialSourceConfigRepository(db)
    saved = await repository.save(config)
    saved.sync_status = "not_synced"
    saved.sync_error = None
    saved.last_synced_at = None
    saved.last_sync_record_count = 0
    saved.sync_total_records = None
    saved.sync_fetched_count = 0
    await repository.invalidate_catalog(saved.id)
    await db.flush()
    return saved


def _payload_from_config(config: MaterialSourceConfig) -> MaterialSourceConfigUpsert:
    return MaterialSourceConfigUpsert(
        source_url=config.source_url,
        material_code_field=config.material_code_field,
        material_description_field=config.material_description_field,
        rule_model_field=config.rule_model_field,
        material_unit_field=config.material_unit_field,
        material_template_field=config.material_template_field,
        material_category_field=config.material_category_field,
        material_subcategory_field=config.material_subcategory_field,
        material_cost_category_field=config.material_cost_category_field,
    )


async def _fetch_sync_page_with_retry(
    fetch_page: Callable[[], Awaitable[BitableRecordPage]],
    *,
    before_attempt: Callable[[int], Awaitable[None]] | None = None,
) -> BitableRecordPage:
    """拉取一页飞书记录，超时或飞书临时性业务错误自动重试。

    飞书翻页只支持串行 page_token，无法并发预取；此处只对超时和
    Fail/频率超限等临时性错误做重试，权限错误和分页异常属于确定性
    错误，重试无意义。
    """
    last_error: MaterialSourceTimeoutError | MaterialSourceUpstreamError | None = None
    for attempt in range(MATERIAL_SYNC_PAGE_RETRIES):
        if before_attempt is not None:
            await before_attempt(attempt + 1)
        try:
            return await _run_feishu("sync_records_page", fetch_page)
        except (MaterialSourceTimeoutError, MaterialSourceUpstreamError) as exc:
            last_error = exc
            if attempt < MATERIAL_SYNC_PAGE_RETRIES - 1:
                logger.warning(
                    "Feishu material sync page fetch failed (%s), "
                    "retrying attempt %s/%s",
                    type(exc).__name__,
                    attempt + 1,
                    MATERIAL_SYNC_PAGE_RETRIES,
                )
                await asyncio.sleep(MATERIAL_SYNC_RETRY_BACKOFF_SECONDS * (attempt + 1))
    assert last_error is not None
    raise last_error


async def _iter_material_record_pages(
    client: BitableClient,
    config: MaterialSourceConfig,
    *,
    before_page_attempt: Callable[[int], Awaitable[None]] | None = None,
) -> AsyncIterator[tuple[BitableRecordPage, int | None]]:
    """Yield one Feishu page at a time; never retain the complete source table."""
    page_token: str | None = None
    field_names = list(
        dict.fromkeys(
            (
                config.material_code_field,
                config.material_description_field,
                config.rule_model_field,
                *(
                    field_name
                    for field_name in (
                        config.material_unit_field,
                        config.material_template_field,
                        config.material_category_field,
                        config.material_subcategory_field,
                        config.material_cost_category_field,
                    )
                    if field_name
                ),
            )
        )
    )
    expected_total: int | None = None
    for _ in range(MAX_MATERIAL_SYNC_PAGES):
        current_page_token = page_token

        async def fetch_page() -> BitableRecordPage:
            return await client.search_records_page(
                config.table_id,
                view_id=config.view_id,
                field_names=field_names,
                page_size=MATERIAL_SYNC_PAGE_SIZE,
                page_token=current_page_token,
                timeout=MATERIAL_SYNC_PAGE_TIMEOUT_SECONDS,
            )

        page = await _fetch_sync_page_with_retry(
            fetch_page,
            before_attempt=before_page_attempt,
        )
        if expected_total is None and page.get("total") is not None:
            expected_total = int(page["total"] or 0)
        yield page, expected_total
        if not page.get("has_more"):
            return
        next_page_token = str(page.get("page_token") or "")
        if not next_page_token or next_page_token == page_token:
            raise MaterialSourcePermissionError("飞书物料表格分页数据异常")
        page_token = next_page_token
    raise MaterialSourcePermissionError(
        "飞书物料表格记录数量超过单次同步上限，请缩小数据表范围"
    )


async def _list_all_material_records(
    client: BitableClient,
    config: MaterialSourceConfig,
    *,
    on_page: Callable[[int, int | None], Awaitable[None]] | None = None,
) -> list[dict[str, Any]]:
    """Compatibility helper for callers/tests; sync path uses page streaming below."""
    records: list[dict[str, Any]] = []
    async for page, expected_total in _iter_material_record_pages(client, config):
        page_items = [
            item for item in page.get("items") or [] if isinstance(item, dict)
        ]
        records.extend(page_items)
        if on_page is not None:
            await on_page(len(records), expected_total)
    return records


async def mark_sync_failed(
    db: AsyncSession,
    config_id: UUID,
    message: str,
) -> None:
    await db.rollback()
    config = await MaterialSourceConfigRepository(db).get()
    if config is None or config.id != config_id:
        return
    config.sync_status = "error"
    config.sync_phase = "failed"
    config.sync_error = message
    config.sync_heartbeat_at = datetime.now(UTC)
    await db.commit()


async def reset_interrupted_syncs(db: AsyncSession) -> None:
    """把服务器重启/崩溃遗留的 syncing 状态重置为 error。

    同步在进程内后台任务中执行，进程被杀后没有任何收尾机制，
    数据库会永久停留在 syncing；应用启动时调用本函数恢复可点击状态。
    """
    config = await MaterialSourceConfigRepository(db).get()
    if config is None or config.sync_status != "syncing":
        return
    config.sync_status = "error"
    config.sync_phase = "failed"
    config.sync_error = "上次同步因服务器重启中断，请重新同步"
    config.sync_persisted_count = 0
    config.sync_fetched_count = 0
    config.sync_heartbeat_at = datetime.now(UTC)
    await db.commit()


async def sync_material_source(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> MaterialSourceSync:
    config = await get_material_source_config(db)
    if config is None:
        raise MaterialSourceNotConfiguredError("物料数据源尚未配置")

    config.sync_status = "syncing"
    config.sync_phase = "fetching"
    config.sync_error = None
    config.sync_total_records = None
    config.sync_fetched_count = 0
    config.sync_persisted_count = 0
    config.sync_heartbeat_at = datetime.now(UTC)
    await db.commit()

    try:
        credentials = await _get_credentials(db)
        client = BitableClient(
            app_token=config.app_token,
            app_id=credentials.app_id,
            app_secret=credentials.app_secret,
        )
        fields = await _run_feishu(
            "sync_list_fields",
            lambda: client.list_fields(config.table_id),
        )
        mapping = _resolve_field_mapping(fields, _payload_from_config(config))
        if (
            mapping.material_code_field != config.material_code_field
            or mapping.material_description_field != config.material_description_field
            or mapping.rule_model_field != config.rule_model_field
        ):
            raise MaterialSourceFieldsError(
                "飞书多维表格字段已变化，请重新保存采购物料数据源配置"
            )
        # 可选字段自动补全：存量配置没有新字段映射时，用本次识别结果补齐，
        # 无需管理员重新保存配置即可获得新增的可选字段。
        config.material_unit_field = mapping.material_unit_field
        config.material_template_field = mapping.material_template_field
        config.material_category_field = mapping.material_category_field
        config.material_subcategory_field = mapping.material_subcategory_field
        config.material_cost_category_field = mapping.material_cost_category_field

        async def report_progress(
            fetched_count: int,
            expected_total: int | None,
        ) -> None:
            config.sync_fetched_count = fetched_count
            if expected_total is not None:
                config.sync_total_records = expected_total
            await db.commit()

        repository = MaterialCatalogRepository(db)
        existing_record_ids = await repository.list_feishu_record_ids(config.id)
        active_record_ids: set[str] = set()
        max_modified_time: int | None = None
        now = datetime.now(UTC)

        async def report_page_attempt(_attempt: int) -> None:
            config.sync_phase = "fetching"
            config.sync_heartbeat_at = datetime.now(UTC)
            await db.commit()

        async for page, expected_total in _iter_material_record_pages(
            client,
            config,
            before_page_attempt=report_page_attempt,
        ):
            page_items = [
                item for item in page.get("items") or [] if isinstance(item, dict)
            ]
            rows: list[dict[str, object]] = []
            for raw_record in page_items:
                record_id = str(raw_record.get("record_id") or "").strip()
                if not record_id:
                    continue
                fields_value = raw_record.get("fields")
                source_fields = fields_value if isinstance(fields_value, dict) else {}
                modified_time = _record_timestamp(raw_record, "last_modified_time")
                if modified_time is not None:
                    max_modified_time = max(
                        max_modified_time or modified_time, modified_time
                    )
                rows.append(
                    {
                        "source_config_id": config.id,
                        "feishu_record_id": record_id,
                        "material_code": extract_text(
                            source_fields.get(config.material_code_field)
                        ).strip(),
                        "material_description": extract_text(
                            source_fields.get(config.material_description_field)
                        ).strip(),
                        "rule_model": extract_text(
                            source_fields.get(config.rule_model_field)
                        ).strip(),
                        "material_unit": extract_text(
                            source_fields.get(config.material_unit_field)
                        ).strip(),
                        "material_template": extract_text(
                            source_fields.get(config.material_template_field)
                        ).strip(),
                        "material_category": extract_text(
                            source_fields.get(config.material_category_field)
                        ).strip(),
                        "material_subcategory": extract_text(
                            source_fields.get(config.material_subcategory_field)
                        ).strip(),
                        "material_cost_category": extract_text(
                            source_fields.get(config.material_cost_category_field)
                        ).strip(),
                        "feishu_created_time": _record_timestamp(
                            raw_record, "created_time"
                        ),
                        "feishu_last_modified_time": modified_time,
                        "last_synced_at": now,
                        "is_deleted": False,
                        "created_by": user_id,
                        "updated_by": user_id,
                    }
                )
                active_record_ids.add(record_id)
            config.sync_phase = "persisting"
            upserted_count = await repository.bulk_upsert(rows)
            config.sync_persisted_count = (config.sync_persisted_count or 0) + (
                upserted_count or len(rows)
            )
            config.sync_fetched_count = (config.sync_fetched_count or 0) + len(rows)
            config.sync_total_records = expected_total
            config.sync_heartbeat_at = datetime.now(UTC)
            await db.commit()
        config.sync_phase = "deactivating"
        config.sync_heartbeat_at = datetime.now(UTC)
        await db.commit()
    except MaterialSourceError as exc:
        await mark_sync_failed(db, config.id, exc.public_message)
        raise

    missing_record_ids = sorted(existing_record_ids - active_record_ids)
    deactivated_count = await repository.deactivate_missing(
        config.id, missing_record_ids
    )
    config.material_code_field_type = mapping.material_code_field_type
    config.sync_phase = "completed"
    config.sync_heartbeat_at = datetime.now(UTC)
    config.last_successful_modified_time = max_modified_time
    config.sync_status = "success"
    config.sync_error = None
    config.last_synced_at = now
    config.last_sync_record_count = len(active_record_ids)
    config.updated_by = user_id
    await db.flush()
    await db.commit()
    return MaterialSourceSync(
        config=config,
        synced_count=len(active_record_ids),
        deactivated_count=deactivated_count,
    )


def _record_timestamp(record: dict[str, Any], key: str) -> int | None:
    value = record.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


async def list_material_catalog(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    material_code: str | None = None,
    material_description: str | None = None,
    rule_model: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[MaterialCatalogRecord], int, MaterialSourceConfig]:
    config = await get_material_source_config(db)
    if config is None:
        raise MaterialSourceNotConfiguredError("物料数据源尚未配置")
    records, total = await MaterialCatalogRepository(db).list_records(
        source_config_id=config.id,
        keyword=keyword.strip() if keyword else None,
        material_code=material_code.strip() if material_code else None,
        material_description=(
            material_description.strip() if material_description else None
        ),
        rule_model=rule_model.strip() if rule_model else None,
        page=page,
        page_size=page_size,
    )
    return records, total, config


async def test_material_source_config(
    db: AsyncSession,
    payload: MaterialSourceConfigUpsert | None = None,
) -> MaterialSourceProbe:
    repository = MaterialSourceConfigRepository(db)
    existing = await repository.get()
    test_payload = payload or (
        _payload_from_config(existing) if existing is not None else None
    )
    if test_payload is None:
        raise MaterialSourceNotConfiguredError("物料数据源尚未配置")

    try:
        probe = await probe_material_source(db, test_payload)
    except MaterialSourceError as exc:
        if existing is not None and (
            payload is None or test_payload.source_url.strip() == existing.source_url
        ):
            existing.last_test_status = "error"
            existing.last_test_error = exc.public_message
            existing.last_tested_at = datetime.now(UTC)
            await db.flush()
        raise

    if existing is not None and (
        payload is None or test_payload.source_url.strip() == existing.source_url
    ):
        existing.last_test_status = probe.status
        existing.last_test_error = probe.error_message
        existing.last_tested_at = probe.tested_at
        existing.material_code_field_type = probe.material_code_field_type
        await db.flush()
    return probe


def _material_options_cache_key(
    config: MaterialSourceConfig,
    keyword: str,
    limit: int,
) -> str:
    source_fingerprint = sha256(
        ":".join(
            (
                config.app_token,
                config.table_id,
                config.view_id or "",
                config.material_code_field,
                config.material_description_field,
                config.rule_model_field,
                config.material_unit_field or "",
                config.material_template_field or "",
                config.material_category_field or "",
                config.material_subcategory_field or "",
                config.material_cost_category_field or "",
            )
        ).encode()
    ).hexdigest()[:24]
    keyword_fingerprint = sha256(keyword.casefold().encode()).hexdigest()[:32]
    return (
        "procurement:material-options:"
        f"{config.id}:{source_fingerprint}:{keyword_fingerprint}:{limit}"
    )


async def _read_cached_options(key: str) -> list[dict[str, str]] | None:
    try:
        cached = await cache_get(key)
    except Exception as exc:
        logger.warning(
            "Redis material options cache unavailable: %s",
            type(exc).__name__,
        )
        return None
    if not cached:
        return None
    try:
        parsed = json.loads(cached)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or not all(
        isinstance(item, dict) for item in parsed
    ):
        return None
    return cast(list[dict[str, str]], parsed)


async def _write_cached_options(
    key: str,
    options: list[dict[str, str]],
) -> None:
    try:
        await cache_set(
            key,
            json.dumps(options, ensure_ascii=False),
            ex=MATERIAL_OPTIONS_CACHE_TTL,
        )
    except Exception as exc:
        logger.warning(
            "Redis material options cache unavailable: %s",
            type(exc).__name__,
        )


def _material_option(
    record: dict[str, Any],
    config: MaterialSourceConfig,
) -> dict[str, str]:
    fields = record.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    return {
        "record_id": str(record.get("record_id") or ""),
        "material_code": extract_text(fields.get(config.material_code_field)).strip(),
        "material_description": extract_text(
            fields.get(config.material_description_field)
        ).strip(),
        "rule_model": extract_text(fields.get(config.rule_model_field)).strip(),
        "material_unit": extract_text(fields.get(config.material_unit_field)).strip(),
        "material_template": extract_text(
            fields.get(config.material_template_field)
        ).strip(),
        "material_category": extract_text(
            fields.get(config.material_category_field)
        ).strip(),
        "material_subcategory": extract_text(
            fields.get(config.material_subcategory_field)
        ).strip(),
        "material_cost_category": extract_text(
            fields.get(config.material_cost_category_field)
        ).strip(),
    }


def _material_option_rank(option: dict[str, str], keyword_folded: str) -> int:
    code = option["material_code"].casefold()
    if code == keyword_folded:
        return 0
    if code.startswith(keyword_folded):
        return 1
    return 2


def _sort_and_truncate_material_options(
    options: list[dict[str, str]],
    keyword: str,
    limit: int,
) -> list[dict[str, str]]:
    """Prefer exact code matches over prefixes and arbitrary contains hits.

    ``sorted`` is stable, so options with the same rank keep the order the
    Feishu API returned them in.
    """
    keyword_folded = keyword.casefold()
    ordered = sorted(
        options,
        key=lambda option: _material_option_rank(option, keyword_folded),
    )
    return ordered[:limit]


async def _resolve_material_code_field_type(
    db: AsyncSession,
    client: BitableClient,
    config: MaterialSourceConfig,
) -> int | None:
    if config.material_code_field_type is not None:
        return int(config.material_code_field_type)
    fields = await _run_feishu(
        "list_fields",
        lambda: client.list_fields(config.table_id),
    )
    field_type = next(
        (
            int(item["type"])
            for item in fields
            if isinstance(item, dict)
            and str(item.get("field_name", "")).strip() == config.material_code_field
            and isinstance(item.get("type"), (int, str))
            and str(item["type"]).isdigit()
        ),
        None,
    )
    if field_type is None:
        raise MaterialSourceFieldsError("无法识别飞书物料编码字段类型")
    config.material_code_field_type = field_type
    await db.flush()
    return field_type


async def _list_client_filtered_options(
    client: BitableClient,
    config: MaterialSourceConfig,
    *,
    keyword: str,
    limit: int,
    deadline: float,
) -> list[dict[str, str]]:
    exact_options: list[dict[str, str]] = []
    fuzzy_options: list[dict[str, str]] = []
    page_token: str | None = None
    field_names = list(
        dict.fromkeys(
            (
                config.material_code_field,
                config.material_description_field,
                config.rule_model_field,
                *(
                    field_name
                    for field_name in (
                        config.material_unit_field,
                        config.material_template_field,
                        config.material_category_field,
                        config.material_subcategory_field,
                        config.material_cost_category_field,
                    )
                    if field_name
                ),
            )
        )
    )
    keyword_folded = keyword.casefold()
    collect_limit = limit * MATERIAL_OPTION_COLLECT_FACTOR
    for _ in range(MAX_MATERIAL_SCAN_PAGES):
        if time.monotonic() >= deadline:
            raise MaterialSourceTimeoutError("飞书物料数据源请求超时")
        current_page_token = page_token

        async def fetch_page() -> BitableRecordPage:
            return await client.search_records_page(
                config.table_id,
                view_id=config.view_id,
                field_names=field_names,
                page_size=MATERIAL_RECORD_PAGE_SIZE,
                page_token=current_page_token,
                timeout=MATERIAL_OPTION_REQUEST_TIMEOUT_SECONDS,
            )

        page = await _run_feishu(
            "search_records_page",
            fetch_page,
        )
        records = page.get("items") or []
        for record in records:
            if not isinstance(record, dict):
                continue
            option = _material_option(record, config)
            code = option["material_code"].casefold()
            if keyword_folded not in code:
                continue
            if code == keyword_folded:
                exact_options.append(option)
                if len(exact_options) >= limit:
                    return exact_options[:limit]
            elif len(fuzzy_options) < collect_limit:
                # Exact matches may sit on later pages, so fuzzy collection
                # filling up must not stop the scan short of the exact one.
                fuzzy_options.append(option)
        if not page.get("has_more"):
            break
        next_page_token = str(page.get("page_token") or "")
        if not next_page_token or next_page_token == page_token:
            raise MaterialSourcePermissionError("飞书多维表格分页数据异常")
        page_token = next_page_token
    else:
        logger.warning(
            "Feishu material source scan reached page limit: %s",
            MAX_MATERIAL_SCAN_PAGES,
        )
    return _sort_and_truncate_material_options(
        exact_options + fuzzy_options,
        keyword,
        limit,
    )


def _material_option_from_catalog(
    record: MaterialCatalogRecord,
) -> dict[str, str]:
    return {
        "record_id": record.feishu_record_id,
        "material_code": record.material_code,
        "material_description": record.material_description,
        "rule_model": record.rule_model,
        "material_unit": record.material_unit,
        "material_template": record.material_template,
        "material_category": record.material_category,
        "material_subcategory": record.material_subcategory,
        "material_cost_category": record.material_cost_category,
    }


async def _list_local_material_options(
    db: AsyncSession,
    config: MaterialSourceConfig,
    *,
    keyword: str,
    limit: int,
) -> list[dict[str, str]] | None:
    # 本地镜像取最近一次成功同步的快照；只要同步过就优先使用，同步失败
    # 不会破坏已同步数据，避免联想被打回慢速的飞书实时查询。首次配置或
    # 更换链接后（last_synced_at 为空）才走飞书。
    if config.last_synced_at is None:
        return None
    records = await MaterialCatalogRepository(db).list_option_records(
        source_config_id=config.id,
        keyword=keyword,
        limit=limit,
    )
    return _sort_and_truncate_material_options(
        [_material_option_from_catalog(record) for record in records],
        keyword,
        limit,
    )


async def list_material_options(
    db: AsyncSession,
    *,
    keyword: str,
    limit: int = MAX_MATERIAL_OPTIONS,
) -> list[dict[str, str]]:
    normalized_keyword = keyword.strip()
    if not normalized_keyword:
        raise MaterialSourceValidationError("物料编码关键词不能为空")
    if limit < 1 or limit > MAX_MATERIAL_OPTIONS:
        raise MaterialSourceValidationError("联想结果数量必须在 1 到 20 之间")

    config = await get_material_source_config(db)
    if config is None:
        raise MaterialSourceNotConfiguredError("物料数据源尚未配置")
    local_options = await _list_local_material_options(
        db,
        config,
        keyword=normalized_keyword,
        limit=limit,
    )
    if local_options is not None:
        return local_options
    cache_key = _material_options_cache_key(config, normalized_keyword, limit)
    cached = await _read_cached_options(cache_key)
    if cached is not None:
        return cached
    credentials = await _get_credentials(db)

    client = BitableClient(
        app_token=config.app_token,
        app_id=credentials.app_id,
        app_secret=credentials.app_secret,
    )
    field_type = await _resolve_material_code_field_type(db, client, config)
    if field_type == BITABLE_TEXT_FIELD_TYPE:
        # A contains filter is served from an arbitrary page window and can
        # cut off the exact code match, so the exact record is looked up with
        # an equality filter and merged ahead of the fuzzy candidates. The
        # client applies the same ranking.
        page_size = min(
            max(limit * MATERIAL_OPTION_COLLECT_FACTOR, 50),
            MAX_MATERIAL_OPTION_PAGE_SIZE,
        )
        exact_filter: dict[str, object] = {
            "conjunction": "and",
            "conditions": [
                {
                    "field_name": config.material_code_field,
                    "operator": "is",
                    "value": [normalized_keyword],
                }
            ],
        }
        contains_filter: dict[str, object] = {
            "conjunction": "and",
            "conditions": [
                {
                    "field_name": config.material_code_field,
                    "operator": "contains",
                    "value": [normalized_keyword],
                }
            ],
        }

        async def fetch_exact() -> list[dict[str, Any]]:
            try:
                return await _run_feishu(
                    "search_records",
                    lambda: client.search_records(
                        config.table_id,
                        filter_info=exact_filter,
                        view_id=config.view_id,
                        page_size=limit,
                        timeout=MATERIAL_OPTION_REQUEST_TIMEOUT_SECONDS,
                    ),
                )
            except MaterialSourceTimeoutError:
                raise
            except MaterialSourceError as exc:
                # An unsupported equality filter must not take the whole
                # lookup down; fall back to the fuzzy-only result set.
                logger.warning(
                    "Exact material option lookup skipped: %s",
                    exc.public_message,
                )
                return []

        async def fetch_fuzzy() -> list[dict[str, Any]]:
            return await _run_feishu(
                "search_records",
                lambda: client.search_records(
                    config.table_id,
                    filter_info=contains_filter,
                    view_id=config.view_id,
                    page_size=page_size,
                    timeout=MATERIAL_OPTION_REQUEST_TIMEOUT_SECONDS,
                ),
            )

        try:
            exact_records, fuzzy_records = await asyncio.wait_for(
                asyncio.gather(fetch_exact(), fetch_fuzzy()),
                timeout=MATERIAL_OPTION_TOTAL_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise MaterialSourceTimeoutError("飞书物料数据源请求超时") from exc
        options: list[dict[str, str]] = []
        seen_record_ids: set[str] = set()
        for record in [*exact_records, *fuzzy_records]:
            option = _material_option(record, config)
            if option["record_id"] in seen_record_ids:
                continue
            seen_record_ids.add(option["record_id"])
            options.append(option)
        options = _sort_and_truncate_material_options(
            options,
            normalized_keyword,
            limit,
        )
    else:
        options = await _list_client_filtered_options(
            client,
            config,
            keyword=normalized_keyword,
            limit=limit,
            deadline=time.monotonic() + MATERIAL_OPTION_TOTAL_TIMEOUT_SECONDS,
        )
    await _write_cached_options(cache_key, options)
    return options
