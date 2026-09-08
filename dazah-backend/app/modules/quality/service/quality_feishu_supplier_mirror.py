"""供应商资质飞书子表 -> 本地镜像回拉。

供应商资质列表页与仪表盘从"每次实时直读飞书"改为读本地镜像表
``quality.supplier_qualification_records``：
- 首次（或手动全量刷新）按 GET /records 翻页拉全表；
- 增量轮用 search 单页按 ``last_modified_time`` 降序 + 客户端水位过滤，
  只写达到水位的行（对齐仓储模块实测：records/search 无 filter 翻页失效，
  filter 对自动字段返回 InvalidFilter，无法真正翻页式增量）；
- 远端已删除的记录在镜像中软删（仅全量轮做删除对账，增量轮不删，避免
  翻页失效误删未拉到的历史行）。

凭证与实体配置由本模块解密校验后显式传给平台 BitableClient，符合
``app/platform/integrations/feishu/AGENTS.md`` 平台边界。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.models.external_quality import SupplierQualificationMirror
from app.modules.quality.models.feishu_settings import QualityFeishuEntitySetting
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

ENTITY_SUPPLIER_QUALIFICATION = "supplier_qualification"


def map_record_to_mirror_fields(
    record: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    """把飞书一条记录映射成镜像表列值（中文字段 -> snake_case 列）。"""
    fields = record.get("fields") or {}
    get_value = feishu_sync_service._get_mapped_field_value
    normalize_text = feishu_sync_service._normalize_text
    parse_datetime = feishu_sync_service._parse_feishu_datetime

    # 负责人 - user 字段
    responsible_raw = get_value(entity, fields, "负责人")
    responsible: str | None = None
    if isinstance(responsible_raw, list):
        names: list[str] = []
        for item in responsible_raw:
            if isinstance(item, dict):
                name = item.get("name", "") or item.get("text", "")
                if name:
                    names.append(str(name))
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        responsible = "、".join(names) if names else None
    elif responsible_raw:
        responsible = normalize_text(responsible_raw)

    completed_raw = get_value(entity, fields, "是否完成")
    is_completed = (
        completed_raw is True
        or str(completed_raw).strip().lower() in ("true", "是", "已确认", "1")
    )

    deadline_dt = parse_datetime(get_value(entity, fields, "截止日期"))

    return {
        "supplier_name": normalize_text(get_value(entity, fields, "供应商名称")),
        "material_name": normalize_text(get_value(entity, fields, "物料名称")),
        "material_type": normalize_text(get_value(entity, fields, "物料类型")),
        "qualification_name": normalize_text(get_value(entity, fields, "资质名称")),
        "qualification_file": normalize_text(get_value(entity, fields, "资质文件")),
        "is_completed": is_completed,
        "deadline": deadline_dt.isoformat() if deadline_dt else None,
        "responsible_person": responsible,
        "remark": normalize_text(get_value(entity, fields, "备注")),
        "expiry_status": normalize_text(get_value(entity, fields, "到期状态")),
        "source_created_at": parse_datetime(record.get("created_time")),
        "source_updated_at": feishu_sync_service._get_record_modified_at(record),
    }


async def pull_supplier_qualification_mirror(
    db: AsyncSession,
    *,
    full: bool = False,
) -> dict[str, int]:
    """回拉入口：执行镜像同步并把结果写回实体配置"最近状态"。

    失败（配置未启用/飞书不可达）同样标记 failed，让设置页可诊断，
    异常原样抛出。
    """
    try:
        result = await _pull_supplier_qualification_mirror_impl(db, full=full)
    except AppException as exc:
        await _mark_entity_pull_status(
            db, ok=False, error=str(getattr(exc, "detail", "") or "") or None
        )
        raise
    await _mark_entity_pull_status(
        db,
        ok=result["failed"] == 0,
        error=f"{result['failed']} 条记录写入失败" if result["failed"] else None,
    )
    return result


async def _pull_supplier_qualification_mirror_impl(
    db: AsyncSession,
    *,
    full: bool = False,
) -> dict[str, int]:
    """回拉供应商资质子表到本地镜像。返回 {synced, failed, removed, total}。

    full=True 强制全量翻页（首次、手动"从飞书拉取"、删除对账轮）；
    否则按增量水位拉最近修改页。无配置或飞书不可达抛 AppException，
    不静默吞异常（对齐后端接口规范）。
    """
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_SUPPLIER_QUALIFICATION, direction="pull"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    table_id = feishu_sync_service._require_table_id(entity)

    existing = (
        await db.execute(
            select(
                SupplierQualificationMirror.feishu_record_id,
                SupplierQualificationMirror.source_updated_at,
            ).where(SupplierQualificationMirror.is_deleted.is_(False))
        )
    ).all()
    existing_map: dict[str, datetime | None] = {
        row.feishu_record_id: row.source_updated_at for row in existing
    }

    if full or not existing_map:
        records = await _fetch_or_fail(_fetch_full_records(client, table_id))
    else:
        watermark = _compute_watermark(existing_map)
        records = await _fetch_or_fail(
            _fetch_incremental_records(client, table_id, watermark)
        )

    synced = 0
    failed = 0
    seen_record_ids: set[str] = set()
    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id:
            continue
        seen_record_ids.add(record_id)
        try:
            # savepoint 隔离单行失败，避免一个坏行污染整个回拉事务
            async with db.begin_nested():
                changed = await _upsert_mirror_record(
                    db,
                    record_id=record_id,
                    mapped=map_record_to_mirror_fields(record, entity),
                    existing_updated_at=existing_map.get(record_id),
                )
            if changed:
                synced += 1
        except Exception:
            logger.exception(
                "Failed to upsert supplier qualification record %s", record_id
            )
            failed += 1

    # 仅全量轮做删除对账：远端消失的未删镜像行软删
    deleted = 0
    if full or not existing_map:
        stale = set(existing_map) - seen_record_ids
        if stale:
            stale_rows = (
                await db.execute(
                    select(SupplierQualificationMirror).where(
                        SupplierQualificationMirror.feishu_record_id.in_(stale),
                        SupplierQualificationMirror.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            for row in stale_rows:
                row.is_deleted = True
                deleted += 1
            await db.flush()

    await db.commit()
    logger.info(
        "supplier_qualification mirror pull: synced=%d failed=%d deleted=%d",
        synced,
        failed,
        deleted,
    )
    return {
        "synced": synced,
        "failed": failed,
        "removed": deleted,
        "total": len(records),
    }


async def _fetch_or_fail(
    fetchable: Awaitable[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """飞书拉取失败转 503 业务异常（不裸 500、不静默返回空）。"""
    try:
        return await fetchable
    except AppException:
        raise
    except Exception as exc:
        raise AppException(
            message="从飞书拉取供应商资质失败：无法连接飞书或访问该子表，"
            "请检查网络及模块飞书应用对该 Base 的协作者权限",
            status_code=503,
        ) from exc


async def _fetch_full_records(
    client: BitableClient, table_id: str
) -> list[dict[str, Any]]:
    """全量翻页：必须走 GET /records 列表接口。

    records/search 无 filter 时翻页失效（page_token 恒为 pageToken:500
    循环，仓储模块实测），GET 列表接口翻页可靠且支持 automatic_fields
    返回 last_modified_time 等自动字段。
    """
    records: list[dict[str, Any]] = []
    page_token = ""
    for _page_index in range(200):
        params: dict[str, Any] = {
            "page_size": 500,
            "field_name_type": "name",
            "automatic_fields": True,
        }
        if page_token:
            params["page_token"] = page_token
        data = await client.client.request(
            "GET",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records",
            params=params,
            timeout=60.0,
        )
        records.extend(
            item for item in (data.get("items") or []) if isinstance(item, dict)
        )
        if not data.get("has_more"):
            return records
        remote_total = data.get("total") or 0
        if remote_total and len(records) >= remote_total:
            return records[: int(remote_total)]
        page_token = str(data.get("page_token") or "")
        if not page_token:
            return records
    return records


async def _fetch_incremental_records(
    client: BitableClient,
    table_id: str,
    watermark: datetime | None,
) -> list[dict[str, Any]]:
    """增量：search 单页按 last_modified_time 降序 + 水位过滤。

    filter 对自动字段返回 InvalidFilter、且 search 翻页失效，故只取第一页
    并按 record_id 去重；第 500 条之后的历史修改由每日全量兜底。
    """
    data = await client.client.request(
        "POST",
        f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records/search",
        params={"page_size": 500, "field_name_type": "name", "automatic_fields": True},
        json={"sort": [{"field_name": "last_modified_time", "desc": True}]},
        timeout=60.0,
    )
    merged: dict[str, dict[str, Any]] = {}
    for record in data.get("items") or []:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("record_id") or "")
        if record_id and _record_is_newer(record, watermark):
            merged[record_id] = record
    return list(merged.values())


def _compute_watermark(existing_map: dict[str, datetime | None]) -> datetime | None:
    timestamps = [ts for ts in existing_map.values() if ts is not None]
    return max(timestamps) if timestamps else None


def _record_is_newer(record: dict[str, Any], watermark: datetime | None) -> bool:
    if watermark is None:
        return True
    modified_ms = record.get("last_modified_time")
    if not isinstance(modified_ms, (int, float)):
        return True
    modified = datetime.fromtimestamp(float(modified_ms) / 1000, tz=UTC)
    return modified >= watermark


async def _upsert_mirror_record(
    db: AsyncSession,
    *,
    record_id: str,
    mapped: dict[str, Any],
    existing_updated_at: datetime | None,
) -> bool:
    """按飞书 record_id 镜像 upsert。返回是否发生写库。"""
    # 增量轮：远端修改时间未超过本地水位则跳过
    new_updated = mapped.get("source_updated_at")
    if (
        existing_updated_at is not None
        and new_updated is not None
        and new_updated <= existing_updated_at
    ):
        return False

    model = (
        await db.execute(
            select(SupplierQualificationMirror).where(
                SupplierQualificationMirror.feishu_record_id == record_id,
                SupplierQualificationMirror.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()

    if model is None:
        model = SupplierQualificationMirror(feishu_record_id=record_id)
        db.add(model)

    for column, value in mapped.items():
        setattr(model, column, value)
    await db.flush()
    return True


__all__ = ["map_record_to_mirror_fields", "pull_supplier_qualification_mirror"]


async def _mark_entity_pull_status(
    db: AsyncSession,
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    """把回拉结果写回实体配置行（设置页"最近状态"列的数据源）。"""
    model = (
        await db.execute(
            select(QualityFeishuEntitySetting).where(
                QualityFeishuEntitySetting.entity_code
                == ENTITY_SUPPLIER_QUALIFICATION,
                QualityFeishuEntitySetting.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if model is None:
        return
    model.last_sync_status = "success" if ok else "failed"
    model.last_sync_error = error
    model.last_synced_at = datetime.now(UTC)
    await db.commit()
