"""Generic Feishu Bitable record CRUD for quality inspection sub-modules.

检验模块的 items / instruments / finished / solid / liquid 数据全部存于飞书多维表格。
本服务提供按 entity_code 的通用「字段元数据 / 新增 / 编辑 / 删除 / 单条读取 / 回拉」
能力。字段名必须是飞书表真实字段名，字段值按飞书 ui_type 强制转换；未知字段名直接
报错，只读字段（附件/人员/Lookup/公式等）不参与写入。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.inspection_finished_material import (
    FINISHED_PRODUCT_GROUP_ENTITY_MAP,
)
from app.modules.quality.service.inspection_helpers import _base_map, _pull_count
from app.modules.quality.service.quality_feishu_material_groups import (
    MATERIAL_ENTITY_CODES,
)
from app.modules.quality.service.quality_feishu_pages import (
    _delete_entity_record,
    _resolve_runtime_entity,
)
from app.platform.audit.service import record_audit_log
from app.platform.integrations.feishu.auth import FeishuAuth
from app.platform.integrations.feishu.bitable import BitableClient, _to_ms_timestamp

logger = logging.getLogger(__name__)

# 检验模块可写实体白名单：items / instruments / finished / solid / liquid
_INSPECTION_ENTITY_CODES: set[str] = {
    "qc_items_inventory",
    "qc_items_inbound",
    "qc_items_outbound",
    "qc_instr_equipment",
    "qc_instr_maintenance",
    "qc_instr_calibration",
    "qc_instr_repair",
    "qc_instr_change",
    "qc_instr_contracts",
    "qc_instr_plans",
    "qc_instr_assets",
}
for _codes in FINISHED_PRODUCT_GROUP_ENTITY_MAP.values():
    _INSPECTION_ENTITY_CODES.update(_codes)
_INSPECTION_ENTITY_CODES.update(MATERIAL_ENTITY_CODES)

# 只读字段类型：通用表单不写入
# （附件需上传文件、人员需 bitable user id、Lookup/公式由飞书派生）
_READ_ONLY_UI_TYPES = {
    "User",
    "Lookup",
    "DuplexLink",
    "Attachment",
    "Formula",
    "CreatedUser",
    "ModifiedUser",
    "CreatedTime",
    "ModifiedTime",
    "GroupChat",
}

_NUMERIC_UI_TYPES = {"Number", "Currency", "Percent", "Progress", "Rating"}


def validate_inspection_entity(entity_code: str) -> None:
    """仅允许对检验模块实体执行通用写操作（防御任意实体写入）。"""
    if entity_code not in _INSPECTION_ENTITY_CODES:
        raise AppException(message=f"不支持的检验实体: {entity_code}", status_code=400)


def _coerce_write_value(field_meta: dict[str, Any], value: Any) -> Any:
    """按飞书 ui_type 转换前端传入值；返回 SKIP_REMOTE_FIELD 表示跳过该字段。"""
    ui_type = str(field_meta.get("ui_type") or "").strip()
    if ui_type in _READ_ONLY_UI_TYPES:
        return feishu_sync_service.SKIP_REMOTE_FIELD
    if value is None or value == "":
        return feishu_sync_service.SKIP_REMOTE_FIELD
    if ui_type == "Url":
        return feishu_sync_service._to_feishu_url_field_value(str(value))
    if ui_type == "DateTime":
        if isinstance(value, (int, float)):
            return int(value)
        parsed = feishu_sync_service._parse_feishu_datetime(value)
        if parsed is None:
            return feishu_sync_service.SKIP_REMOTE_FIELD
        return int(_to_ms_timestamp(parsed))
    if ui_type == "Checkbox":
        normalized = feishu_sync_service._normalize_bool_from_yes_no(value)
        return (
            normalized
            if normalized is not None
            else feishu_sync_service.SKIP_REMOTE_FIELD
        )
    if ui_type in _NUMERIC_UI_TYPES:
        if isinstance(value, (int, float)):
            return value
        try:
            return int(str(value).strip())
        except ValueError:
            try:
                return float(str(value).strip())
            except ValueError:
                return feishu_sync_service.SKIP_REMOTE_FIELD
    if ui_type in {"SingleSelect", "MultiSelect"}:
        if isinstance(value, list):
            return [str(v) for v in value if str(v)]
        return str(value)
    return value


def _coerce_write_fields(
    remote_field_map: dict[str, dict[str, Any]],
    fields: dict[str, Any],
) -> dict[str, Any]:
    """仅保留远程表真实存在的字段并转换类型；未知字段名直接报错（防拼写错误静默丢数据）。"""
    unknown = [name for name in fields if name not in remote_field_map]
    if unknown:
        raise AppException(
            message=f"存在飞书表中不存在的字段: {', '.join(sorted(unknown))}",
            status_code=400,
        )
    coerced: dict[str, Any] = {}
    for name, value in fields.items():
        coerced_value = _coerce_write_value(remote_field_map[name], value)
        if coerced_value is not feishu_sync_service.SKIP_REMOTE_FIELD:
            coerced[name] = coerced_value
    return coerced


def _entity_table_id(entity: Any) -> str:
    """实体配置必须带非空 table_id（防御配置缺失导致对空表名发起请求）。"""
    table_id = str(entity.table_id or "").strip()
    if not table_id:
        raise AppException(message="检验实体未配置飞书表 table_id", status_code=400)
    return table_id


async def _resolve_write_client(
    db: AsyncSession,
    entity_code: str,
) -> tuple[Any, Any]:
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="push")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    return client, entity


async def _list_remote_field_map(
    client: BitableClient,
    table_id: str,
) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("field_name") or "").strip(): item
        for item in await client.list_fields(table_id)
        if item.get("field_name")
    }


async def get_inspection_entity_fields(
    db: AsyncSession, entity_code: str
) -> dict[str, Any]:
    """返回实体字段元数据（供前端动态生成新增/编辑表单）。"""
    validate_inspection_entity(entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    fields: list[dict[str, Any]] = []
    for item in await client.list_fields(_entity_table_id(entity)):
        field_name = str(item.get("field_name") or "").strip()
        if not field_name:
            continue
        ui_type = str(item.get("ui_type") or "").strip()
        fields.append(
            {
                "field_name": field_name,
                "ui_type": ui_type,
                "editable": ui_type not in _READ_ONLY_UI_TYPES,
            }
        )
    return {"fields": fields, "can_push": bool(entity.enable_push_to_feishu)}


async def create_inspection_feishu_record(
    db: AsyncSession,
    entity_code: str,
    fields: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    validate_inspection_entity(entity_code)
    client, entity = await _resolve_write_client(db, entity_code)
    remote_field_map = await _list_remote_field_map(client, entity.table_id)
    coerced = _coerce_write_fields(remote_field_map, fields)
    record = await client.create_record(_entity_table_id(entity), coerced)
    record_id = str(record.get("record_id") or "")
    await record_audit_log(
        db,
        action="feishu_record_created",
        user_id=actor_user_id,
        resource_type=f"quality.feishu.{entity_code}",
        extra={
            "feishu_record_id": record_id,
            "feishu_table_id": entity.table_id,
            "fields": sorted(coerced.keys()),
        },
    )
    await db.commit()
    return {"record_id": record_id}


async def update_inspection_feishu_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
    fields: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    validate_inspection_entity(entity_code)
    client, entity = await _resolve_write_client(db, entity_code)
    remote_field_map = await _list_remote_field_map(client, entity.table_id)
    coerced = _coerce_write_fields(remote_field_map, fields)
    record = await client.update_record(_entity_table_id(entity), record_id, coerced)
    next_record_id = str(record.get("record_id") or record_id)
    await record_audit_log(
        db,
        action="feishu_record_updated",
        user_id=actor_user_id,
        resource_type=f"quality.feishu.{entity_code}",
        extra={
            "feishu_record_id": next_record_id,
            "feishu_table_id": entity.table_id,
            "fields": sorted(coerced.keys()),
        },
    )
    await db.commit()
    return {"record_id": next_record_id}


async def delete_inspection_feishu_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    validate_inspection_entity(entity_code)
    await _delete_entity_record(db, entity_code, record_id, actor_user_id)
    return {"record_id": record_id}


async def get_inspection_feishu_record(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> dict[str, Any]:
    validate_inspection_entity(entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    record = await client.get_record(_entity_table_id(entity), record_id)
    if not record or not record.get("record_id"):
        raise NotFoundException(resource="飞书记录", resource_id=str(record_id))
    remote_field_names = sorted(
        str(item.get("field_name") or "").strip()
        for item in await client.list_fields(_entity_table_id(entity))
        if item.get("field_name")
    )
    return _base_map(record, entity, remote_field_names)


async def pull_inspection_feishu_records(
    db: AsyncSession,
    entity_code: str,
) -> dict[str, int]:
    validate_inspection_entity(entity_code)
    return await _pull_count(db, entity_code)


def _find_attachment_in_record(
    record: dict[str, Any],
    file_token: str,
) -> dict[str, Any] | None:
    """在飞书记录的字段值中按 file_token 定位附件项（避免对任意 URL 发起抓取）。"""
    target = str(file_token)
    for value in (record.get("fields") or {}).values():
        if isinstance(value, list):
            for item in value:
                if (
                    isinstance(item, dict)
                    and str(item.get("file_token") or "") == target
                ):
                    return item
    return None


async def _download_attachment_bytes(
    url: str,
    token: str,
) -> tuple[bytes | None, str, str]:
    """按 safety 模块已验证的策略下载飞书附件（含错误体校验）。

    返回 (content, content_type, reason)：
    - 成功: (bytes, content_type, "")
    - 失败: (None, "", "forbidden" | "invalid" | "http")

    策略：
    1. 带 Authorization header 请求（兼容 open.feishu.cn 域名）
    2. 不带 Authorization 请求（兼容内部预签名 URL，鉴权已内嵌 query）
    仅接受真实文件内容：拒绝空内容或 application/json / text/html 错误响应，
    避免把飞书 JSON 错误页当附件返回给前端。
    """
    forbidden = False

    async def _try(headers: dict[str, str] | None) -> tuple[bytes, str] | None:
        nonlocal forbidden
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            resp = await http.get(url, headers=headers or {})
        if resp.status_code == 403:
            forbidden = True
            return None
        if resp.status_code != 200:
            return None
        content = resp.content
        content_type = resp.headers.get("content-type") or ""
        if not content:
            return None
        if content_type.startswith("application/json") or content_type.startswith(
            "text/html"
        ):
            return None
        return content, content_type

    result = await _try({"Authorization": f"Bearer {token}"})
    if result is not None:
        return result[0], result[1], ""
    result = await _try(None)
    if result is not None:
        return result[0], result[1], ""
    return None, "", "forbidden" if forbidden else "invalid"


async def get_inspection_feishu_attachment_content(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
    file_token: str,
) -> tuple[bytes, str, str]:
    """代理下载检验记录附件（飞书附件 url 需带 access token 才能访问）。

    返回 (content, content_type, filename)。附件必须属于该记录，避免任意 URL 抓取。
    """
    validate_inspection_entity(entity_code)
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    record = await client.get_record(_entity_table_id(entity), record_id)
    if not record or not record.get("record_id"):
        raise NotFoundException(resource="飞书记录", resource_id=str(record_id))
    attachment = _find_attachment_in_record(record, file_token)
    if attachment is None:
        raise NotFoundException(resource="飞书附件", resource_id=str(file_token))
    url = attachment.get("url") or attachment.get("tmp_url")
    if not url:
        raise AppException(message="附件无可用下载地址", status_code=400)
    token = await FeishuAuth.get_tenant_access_token(
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    downloaded = await _download_attachment_bytes(url, token)
    content, content_type, reason = downloaded
    if content is None:
        if reason == "forbidden":
            raise AppException(
                message=(
                    "飞书应用缺少附件下载权限：请在飞书开放平台为应用开通 drive "
                    "下载权限，并将应用加入对应多维表格协作者并授予可管理权限后重试"
                ),
                status_code=502,
            )
        raise AppException(
            message="飞书附件下载失败（内容无效或网络错误）", status_code=502
        )
    filename = str(attachment.get("name") or "attachment")
    return content, content_type, filename
