"""Feishu-backed material code lookup for procurement forms."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import cache_get, cache_set
from app.modules.procurement.models import MaterialSourceConfig
from app.modules.procurement.repository import MaterialSourceConfigRepository
from app.modules.procurement.schemas import MaterialSourceConfigUpsert
from app.platform.identity.public_api import (
    FeishuAppCredentials,
    get_platform_feishu_app_credentials,
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
MATERIAL_CODE_FIELD = "物料编码"
MATERIAL_DESCRIPTION_FIELD = "物料说明"
SPECIFICATION_FIELD = "规格型号"
LEGACY_SPECIFICATION_FIELD = "规则型号"


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
            "available_fields": self.available_fields,
            "status": self.status,
            "error_message": self.error_message,
            "tested_at": self.tested_at,
        }


def _resolve_field(
    available_fields: list[str],
    requested: str | None,
    candidates: tuple[str, ...],
    label: str,
) -> str:
    available = {
        field.strip(): field.strip()
        for field in available_fields
        if field.strip()
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

    raise MaterialSourceFieldsError(
        f"多维表格缺少{label}字段，请配置“{candidates[0]}”"
    )


def _resolve_field_mapping(
    fields: list[dict[str, Any]],
    payload: MaterialSourceConfigUpsert,
) -> tuple[str, int | None, str, str, list[str]]:
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
    return (
        material_code_field,
        material_code_field_type,
        material_description_field,
        rule_model_field,
        available_fields,
    )


def _validate_reference(source_url: str) -> BitableReference:
    reference = parse_bitable_url(source_url)
    if not reference.app_token or not reference.table_id:
        raise MaterialSourceValidationError(
            "飞书多维表格链接无法解析，请确认包含 /base/{app_token} 和 table 参数"
        )
    return reference


async def _get_credentials(db: AsyncSession) -> FeishuAppCredentials:
    try:
        credentials = await get_platform_feishu_app_credentials(db)
    except RuntimeError as exc:
        raise MaterialSourceCredentialsError("平台飞书应用凭证不可用") from exc
    if credentials is None:
        raise MaterialSourceCredentialsError("平台尚未配置可用的飞书企业自建应用")
    return credentials


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
        if "not configured" in str(exc).lower():
            raise MaterialSourceCredentialsError(
                "平台尚未配置可用的飞书企业自建应用"
            ) from exc
        raise MaterialSourcePermissionError("飞书多维表格访问失败") from exc
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
    (
        material_code_field,
        material_code_field_type,
        material_description_field,
        rule_model_field,
        available_fields,
    ) = _resolve_field_mapping(fields, payload)
    return MaterialSourceProbe(
        source_url=payload.source_url.strip(),
        app_token=reference.app_token,
        table_id=reference.table_id,
        view_id=reference.view_id,
        material_code_field=material_code_field,
        material_code_field_type=material_code_field_type,
        material_description_field=material_description_field,
        rule_model_field=rule_model_field,
        available_fields=available_fields,
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
    return await MaterialSourceConfigRepository(db).save(config)


def _payload_from_config(config: MaterialSourceConfig) -> MaterialSourceConfigUpsert:
    return MaterialSourceConfigUpsert(
        source_url=config.source_url,
        material_code_field=config.material_code_field,
        material_description_field=config.material_description_field,
        rule_model_field=config.rule_model_field,
    )


async def test_material_source_config(
    db: AsyncSession,
    payload: MaterialSourceConfigUpsert | None = None,
) -> MaterialSourceProbe:
    repository = MaterialSourceConfigRepository(db)
    existing = await repository.get()
    test_payload = payload or (
        _payload_from_config(existing)
        if existing is not None
        else None
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
    }


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
            and str(item.get("field_name", "")).strip()
            == config.material_code_field
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
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    page_token: str | None = None
    field_names = list(
        dict.fromkeys(
            (
                config.material_code_field,
                config.material_description_field,
                config.rule_model_field,
            )
        )
    )
    keyword_folded = keyword.casefold()
    for _ in range(MAX_MATERIAL_SCAN_PAGES):
        current_page_token = page_token

        async def fetch_page() -> BitableRecordPage:
            return await client.search_records_page(
                config.table_id,
                view_id=config.view_id,
                field_names=field_names,
                page_size=MATERIAL_RECORD_PAGE_SIZE,
                page_token=current_page_token,
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
            if keyword_folded not in option["material_code"].casefold():
                continue
            options.append(option)
            if len(options) >= limit:
                return options
        if not page.get("has_more"):
            return options
        next_page_token = str(page.get("page_token") or "")
        if not next_page_token or next_page_token == page_token:
            raise MaterialSourcePermissionError("飞书多维表格分页数据异常")
        page_token = next_page_token

    logger.warning(
        "Feishu material source scan reached page limit: %s",
        MAX_MATERIAL_SCAN_PAGES,
    )
    return options


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
        filter_info: dict[str, object] = {
            "conjunction": "and",
            "conditions": [
                {
                    "field_name": config.material_code_field,
                    "operator": "contains",
                    "value": [normalized_keyword],
                }
            ],
        }
        records = await _run_feishu(
            "search_records",
            lambda: client.search_records(
                config.table_id,
                filter_info=filter_info,
                view_id=config.view_id,
                page_size=limit,
            ),
        )
        options = [_material_option(record, config) for record in records]
    else:
        options = await _list_client_filtered_options(
            client,
            config,
            keyword=normalized_keyword,
            limit=limit,
        )
    await _write_cached_options(cache_key, options)
    return options
