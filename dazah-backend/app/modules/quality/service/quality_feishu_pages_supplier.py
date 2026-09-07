"""Supplier Qualification Feishu pages service.

读路径改为本模块镜像表 ``quality.supplier_qualification_records``（由
``quality_feishu_supplier_mirror`` 定时/手动回拉），列表与仪表盘不再每次实时
拉飞书；写路径仍以飞书为准：创建/更新/删除后同步回写镜像，保证即时可见。

``_map_supplier_qualification`` 与 ``_build_supplier_qualification_fields`` 是
飞书记录 <-> 响应 dict <-> 飞书写入 fields 的映射，保留供测试与写路径复用。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.quality.models.external_quality import SupplierQualificationMirror
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.quality_feishu_pages import (
    _build_page_result,
    _create_entity_record,
    _delete_entity_record,
    _resolve_runtime_entity,
)
from app.modules.quality.service.quality_feishu_supplier_mirror import (
    map_record_to_mirror_fields,
    pull_supplier_qualification_mirror,
)
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

ENTITY_SUPPLIER_QUALIFICATION = "supplier_qualification"


def _map_supplier_qualification(
    record: dict[str, Any],
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    """飞书记录 -> 页面响应行（与镜像映射共用中文字段口径）。"""
    mapped = map_record_to_mirror_fields(record, entity)
    return {
        "record_id": str(record.get("record_id") or ""),
        **mapped,
        "created_at": mapped.get("source_created_at"),
        "updated_at": mapped.get("source_updated_at"),
    }


def _mirror_row(mirror: SupplierQualificationMirror) -> dict[str, Any]:
    """镜像表行 -> 页面响应行。"""
    return {
        "record_id": mirror.feishu_record_id,
        "supplier_name": mirror.supplier_name,
        "material_name": mirror.material_name,
        "material_type": mirror.material_type,
        "qualification_name": mirror.qualification_name,
        "qualification_file": mirror.qualification_file,
        "is_completed": mirror.is_completed,
        "deadline": mirror.deadline,
        "responsible_person": mirror.responsible_person,
        "remark": mirror.remark,
        "expiry_status": mirror.expiry_status,
        "created_at": mirror.source_created_at,
        "updated_at": mirror.source_updated_at,
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _expiry_bucket_conditions(
    bucket: str | None,
) -> list[ColumnElement[bool]]:
    """按截止日期把镜像表行分到 expired/due_30/due_60/due_90 四个区间。

    deadline 列存的是 UTC ISO 字符串（datetime.isoformat()，格式统一带
    +00:00 偏移与秒），字典序与时间序一致，故可直接做字符串比较，与
    get_supplier_statistics 的 Python 分桶保持同一口径：
    - expired：截止日期已过（days_left < 0）
    - due_30：今天起 0~30 天内到期
    - due_60：31~60 天内到期
    - due_90：61~90 天内到期
    无 deadline 的行不属于任何分桶（与统计的 normal_count 一致）。
    """
    if not bucket:
        return []
    now = datetime.now(UTC)
    mirror = SupplierQualificationMirror
    deadline = mirror.deadline
    bounds: dict[str, tuple[str | None, str]] = {
        "expired": (None, now.isoformat()),
        "due_30": (now.isoformat(), (now + timedelta(days=31)).isoformat()),
        "due_60": (
            (now + timedelta(days=31)).isoformat(),
            (now + timedelta(days=61)).isoformat(),
        ),
        "due_90": (
            (now + timedelta(days=61)).isoformat(),
            (now + timedelta(days=91)).isoformat(),
        ),
    }
    lower, upper = bounds[bucket]
    conditions: list[ColumnElement[bool]] = [deadline.is_not(None)]
    if lower is not None:
        conditions.append(deadline >= lower)
    conditions.append(deadline < upper)
    return conditions


async def list_supplier_qualification_records(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    supplier_name: str | None = None,
    material_type: str | None = None,
    qualification_name: str | None = None,
    is_completed: bool | None = None,
    expiry_bucket: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """查询本地镜像表（列表页与仪表盘共用）。

    expiry_bucket 可选 expired/due_30/due_60/due_90，按截止日期分桶筛选，
    与 get_supplier_statistics 计数口径一致；None 表示不按到期分桶过滤。
    """
    mirror = SupplierQualificationMirror
    conditions: list[ColumnElement[bool]] = [mirror.is_deleted.is_(False)]
    if supplier_name:
        conditions.append(mirror.supplier_name == supplier_name)
    if material_type:
        conditions.append(mirror.material_type == material_type)
    if qualification_name:
        conditions.append(mirror.qualification_name == qualification_name)
    if is_completed is not None:
        conditions.append(mirror.is_completed == is_completed)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        conditions.append(
            or_(
                mirror.supplier_name.ilike(pattern),
                mirror.material_name.ilike(pattern),
                mirror.material_type.ilike(pattern),
                mirror.qualification_name.ilike(pattern),
                mirror.qualification_file.ilike(pattern),
                mirror.responsible_person.ilike(pattern),
                mirror.remark.ilike(pattern),
            )
        )
    conditions.extend(_expiry_bucket_conditions(expiry_bucket))

    total = (
        await db.execute(
            select(func.count())
            .select_from(mirror)
            .where(*conditions)
        )
    ).scalar() or 0

    offset = (page - 1) * page_size
    rows = (
        (
            await db.execute(
                select(mirror)
                .where(*conditions)
                .order_by(
                    mirror.deadline.desc().nulls_last(),
                    mirror.source_updated_at.desc().nulls_last(),
                )
                .offset(offset)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    items = [_mirror_row(row) for row in rows]
    return _build_page_result(items, total, page, page_size)


async def get_supplier_qualification_record(
    db: AsyncSession,
    record_id: str,
) -> dict[str, Any]:
    """读取单条镜像记录。"""
    row = await _get_mirror_by_record_id(db, record_id)
    if row is None:
        raise NotFoundException(resource="供应商资质记录")
    return _mirror_row(row)


async def _get_mirror_by_record_id(
    db: AsyncSession, record_id: str
) -> SupplierQualificationMirror | None:
    return (
        await db.execute(
            select(SupplierQualificationMirror).where(
                SupplierQualificationMirror.feishu_record_id == record_id,
                SupplierQualificationMirror.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()


async def _write_mirror_from_remote(
    db: AsyncSession,
    client: BitableClient,
    table_id: str,
    record_id: str,
    entity: feishu_sync_service.QualityFeishuEntityRuntimeConfig,
) -> dict[str, Any]:
    """从飞书读取指定记录并回写镜像表，返回响应行。

    写路径（创建/更新后）即时回写，避免等到定时轮才可见；失败仅记录，
    不阻断主写入（飞书为事实源，定时回拉兜底）。
    """
    record = await client.get_record(table_id, record_id)
    if not record:
        raise NotFoundException(resource="供应商资质记录")
    mapped = map_record_to_mirror_fields(record, entity)
    row = await _get_mirror_by_record_id(db, record_id)
    if row is None:
        row = SupplierQualificationMirror(feishu_record_id=record_id)
        db.add(row)
    for column, value in mapped.items():
        setattr(row, column, value)
    await db.flush()
    await db.commit()
    return _mirror_row(row)


def _build_supplier_qualification_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    text_fields: list[tuple[str, str]] = [
        ("供应商名称", "supplier_name"),
        ("物料名称", "material_name"),
        ("物料类型", "material_type"),
        ("资质名称", "qualification_name"),
        ("资质文件", "qualification_file"),
        ("备注", "remark"),
    ]
    for feishu_key, payload_key in text_fields:
        val = str(payload.get(payload_key) or "").strip()
        if val:
            fields[feishu_key] = val

    is_completed = payload.get("is_completed")
    if is_completed is not None:
        fields["是否完成"] = bool(is_completed)

    deadline = payload.get("deadline")
    if deadline not in (None, ""):
        fields["截止日期"] = feishu_sync_service._to_ms_timestamp(
            feishu_sync_service._parse_feishu_datetime(deadline)
        )

    responsible = payload.get("responsible_person")
    if responsible:
        if isinstance(responsible, dict) and responsible.get("id"):
            fields["负责人"] = [responsible]
        elif isinstance(responsible, str) and responsible.strip():
            if responsible.strip().startswith("ou_"):
                fields["负责人"] = [{"id": responsible.strip()}]

    return fields


async def create_supplier_qualification_record(
    db: AsyncSession,
    payload: dict[str, Any],
) -> dict[str, Any]:
    supplier_name = str(payload.get("supplier_name") or "").strip()
    if not supplier_name:
        raise AppException(message="供应商名称不能为空")
    qualification_name = str(payload.get("qualification_name") or "").strip()
    if not qualification_name:
        raise AppException(message="资质名称不能为空")
    fields = _build_supplier_qualification_fields(payload)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_SUPPLIER_QUALIFICATION, direction="push"
    )
    created = await _create_entity_record(db, ENTITY_SUPPLIER_QUALIFICATION, fields)
    record_id = created["record_id"]
    try:
        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        return await _write_mirror_from_remote(
            db, client, created["table_id"], record_id, entity
        )
    except (NotFoundException, AppException):
        # 飞书写入成功但镜像回写失败：返回飞书 record_id 兜底行，不重复写飞书
        logger.exception("supplier_qualification create mirror write-back failed")
        return {
            "record_id": record_id,
            "supplier_name": payload.get("supplier_name"),
            "material_name": payload.get("material_name"),
            "material_type": payload.get("material_type"),
            "qualification_name": payload.get("qualification_name"),
            "qualification_file": payload.get("qualification_file"),
            "is_completed": bool(payload.get("is_completed")),
            "deadline": payload.get("deadline"),
            "responsible_person": payload.get("responsible_person"),
            "remark": payload.get("remark"),
            "expiry_status": None,
            "created_at": None,
            "updated_at": None,
        }


async def update_supplier_qualification_record(
    db: AsyncSession,
    record_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    current = await get_supplier_qualification_record(db, record_id)
    merged = {**current, **payload}
    fields = _build_supplier_qualification_fields(merged)
    runtime, entity = await _resolve_runtime_entity(
        db, ENTITY_SUPPLIER_QUALIFICATION, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    table_id = feishu_sync_service._require_table_id(entity)
    await client.update_record(table_id, record_id, fields)
    try:
        return await _write_mirror_from_remote(
            db, client, table_id, record_id, entity
        )
    except (NotFoundException, AppException):
        logger.exception("supplier_qualification update mirror write-back failed")
        return await get_supplier_qualification_record(db, record_id)


async def delete_supplier_qualification_record(
    db: AsyncSession,
    record_id: str,
) -> None:
    await _delete_entity_record(db, ENTITY_SUPPLIER_QUALIFICATION, record_id)
    # 飞书已物理删除，镜像同步软删
    row = await _get_mirror_by_record_id(db, record_id)
    if row is not None:
        row.is_deleted = True
        await db.commit()


async def pull_supplier_qualification_records(
    db: AsyncSession,
    *,
    full: bool = True,
) -> dict[str, int]:
    """手动回拉（“从飞书拉取”按钮）：委托镜像回拉服务，真实写库。

    full 默认 True —— 手动按钮语义为全量同步；定时增量轮由 scheduled 调用
    full=False。
    """
    result = await pull_supplier_qualification_mirror(db, full=full)
    return {
        "synced": result["synced"],
        "failed": result["failed"],
        "removed": result["removed"],
        "total": result["total"],
    }


async def get_supplier_statistics(db: AsyncSession) -> dict[str, Any]:
    """基于镜像表计算供应商资质 GMP 指标。"""
    try:
        result = await list_supplier_qualification_records(db, page=1, page_size=99999)
    except AppException:
        return _empty_supplier_stats()
    items: list[dict[str, Any]] = result.get("items", [])

    total = len(items)
    completed = sum(1 for item in items if item.get("is_completed"))
    pending = total - completed

    now = datetime.now(UTC)

    supplier_stats: dict[str, dict[str, int]] = {}
    material_type_stats: dict[str, dict[str, int]] = {}
    qualification_stats: dict[str, dict[str, int]] = {}

    expired_count = 0
    due_30_count = 0
    due_60_count = 0
    due_90_count = 0
    normal_count = 0

    for item in items:
        sn = (item.get("supplier_name") or "未知").strip()
        mt = (item.get("material_type") or "未知").strip()
        qn = (item.get("qualification_name") or "未知").strip()
        is_done = item.get("is_completed")

        if sn not in supplier_stats:
            supplier_stats[sn] = {
                "total": 0,
                "completed": 0,
                "pending": 0,
                "expired": 0,
                "due30": 0,
                "due60": 0,
                "due90": 0,
            }
        supplier_stats[sn]["total"] += 1
        supplier_stats[sn]["completed" if is_done else "pending"] += 1

        if mt not in material_type_stats:
            material_type_stats[mt] = {
                "total": 0,
                "completed": 0,
                "pending": 0,
                "expired": 0,
            }
        material_type_stats[mt]["total"] += 1
        material_type_stats[mt]["completed" if is_done else "pending"] += 1

        if qn not in qualification_stats:
            qualification_stats[qn] = {"total": 0, "completed": 0, "pending": 0}
        qualification_stats[qn]["total"] += 1
        qualification_stats[qn]["completed" if is_done else "pending"] += 1

        deadline = item.get("deadline")
        if deadline:
            if isinstance(deadline, str):
                deadline = feishu_sync_service._parse_feishu_datetime(deadline)
            if deadline:
                days_left = (deadline - now).days
                if days_left < 0:
                    expired_count += 1
                    supplier_stats[sn]["expired"] += 1
                    material_type_stats[mt]["expired"] += 1
                elif days_left <= 30:
                    due_30_count += 1
                    supplier_stats[sn]["due30"] += 1
                elif days_left <= 60:
                    due_60_count += 1
                    supplier_stats[sn]["due60"] += 1
                elif days_left <= 90:
                    due_90_count += 1
                    supplier_stats[sn]["due90"] += 1
                else:
                    normal_count += 1
            else:
                normal_count += 1
        else:
            normal_count += 1

    supplier_risk = sorted(
        [
            {
                "name": k,
                "total": v["total"],
                "completed": v["completed"],
                "pending": v["pending"],
                "expired": v["expired"],
                "due30": v["due30"],
                "risk_score": v["expired"] * 3 + v["due30"] * 2 + v["pending"],
            }
            for k, v in supplier_stats.items()
        ],
        key=lambda x: -float(str(x["risk_score"])),
    )[:10]

    material_type_compliance = [
        {
            "type": k,
            "total": v["total"],
            "completed": v["completed"],
            "pending": v["pending"],
            "expired": v["expired"],
            "compliance_rate": round(v["completed"] / v["total"] * 100, 1)
            if v["total"] > 0
            else 0,
        }
        for k, v in sorted(material_type_stats.items(), key=lambda x: -x[1]["total"])
    ]

    qualification_compliance = [
        {
            "name": k,
            "total": v["total"],
            "completed": v["completed"],
            "pending": v["pending"],
            "completion_rate": round(v["completed"] / v["total"] * 100, 1)
            if v["total"] > 0
            else 0,
        }
        for k, v in sorted(qualification_stats.items(), key=lambda x: -x[1]["total"])
    ]

    expiry_timeline: dict[str, int] = {}
    for item in items:
        deadline = item.get("deadline")
        if deadline:
            if isinstance(deadline, str):
                deadline = feishu_sync_service._parse_feishu_datetime(deadline)
            if deadline:
                month_key = deadline.strftime("%Y-%m")
                expiry_timeline[month_key] = expiry_timeline.get(month_key, 0) + 1

    timeline_sorted = sorted(expiry_timeline.items())
    recent_timeline = [
        {"month": k, "count": v}
        for k, v in timeline_sorted
        if k <= (now + timedelta(days=400)).strftime("%Y-%m")
    ][-24:]

    return {
        "total": total,
        "completed": completed,
        "pending": pending,
        "completion_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "expired_count": expired_count,
        "due_30_count": due_30_count,
        "due_60_count": due_60_count,
        "due_90_count": due_90_count,
        "normal_count": normal_count,
        "supplier_count": len(supplier_stats),
        "material_type_compliance": material_type_compliance,
        "qualification_compliance": qualification_compliance,
        "supplier_risk_ranking": supplier_risk,
        "expiry_timeline": recent_timeline,
    }


def _empty_supplier_stats() -> dict[str, Any]:
    return {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "completion_rate": 0,
        "expired_count": 0,
        "due_30_count": 0,
        "due_60_count": 0,
        "due_90_count": 0,
        "normal_count": 0,
        "supplier_count": 0,
        "material_type_compliance": [],
        "qualification_compliance": [],
        "supplier_risk_ranking": [],
        "expiry_timeline": [],
    }
