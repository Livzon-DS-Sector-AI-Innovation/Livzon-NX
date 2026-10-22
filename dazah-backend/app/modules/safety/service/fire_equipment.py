"""灭火器 / 消防栓点检：器材台账投影 + 点检记录。

「灭火器及消防栓点检」页绑定各车间的飞书多维表格子表（经页面镜像同步落
库），本服务做三件事：

- 台账投影：``page_table_mirror_records`` → ``fire_equipment`` 结构化台账
  （编号/部门/位置按字段名启发式抽取，器材类型优先看记录字段、再看子表
  名），由镜像同步入口在同步完成后自动调用（幂等，可安全重跑）；
- 点检记录：按检查卡（灭火器 4 项 / 消防栓 8 项，每月一次）逐项记录
  合格/不合格，快照存 ``fire_inspection_records`` 并回写器材最近点检状态；
- 飞书写回：提交后把点检记录写回同 Base 的「点检记录」子表（一键初始化
  建表），失败置 ``feishu_record_id = NULL`` 由同步循环自动补写。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.feishu.bitable_client import SafetyBitableClient
from app.modules.safety.models import (
    FireEquipment,
    FireInspectionRecord,
    SafetyPageFeishuConfig,
    SafetyPageTableMirrorRecord,
)

logger = logging.getLogger(__name__)

FIRE_EQUIPMENT_PAGE_KEY = "safety:emergency-accident:fire-equipment-inspection"

EQUIPMENT_TYPE_EXTINGUISHER = "extinguisher"
EQUIPMENT_TYPE_HYDRANT = "hydrant"
EQUIPMENT_TYPE_LABELS = {
    EQUIPMENT_TYPE_EXTINGUISHER: "灭火器",
    EQUIPMENT_TYPE_HYDRANT: "消防栓",
}

# 检查项文案与《消防栓、灭火器点检卡》(QR/EHS-SH-029/030) 一致；key 是
# 记录契约（改文案不改 key），label 展示用。
EXTINGUISHER_CHECK_ITEMS: tuple[tuple[str, str], ...] = (
    ("body", "灭火器钢体外表清洁，无变形、损伤、锈蚀。"),
    ("placement", "灭火器放置便于人员获取，且通道畅通无障碍物。"),
    (
        "pressure",
        "灭火器压力表的外表面不得有变形、损伤，"
        "压力指针指在绿色区域（正常工作压力）。",
    ),
    ("parts", "灭火器的喷嘴、铅封、保险销、压把等部件完好。"),
)
HYDRANT_CHECK_ITEMS: tuple[tuple[str, str], ...] = (
    ("signage", "消防栓箱有明显的消防栓字样及说明或标识。"),
    ("passage", "消防栓箱附近1米范围内，通道无杂物阻挡，箱门便于开启。"),
    ("accessories", "消防栓箱内水枪、水带、消防栓阀门配件齐全，箱门玻璃无破损。"),
    (
        "valve",
        "消防栓阀开口方向正对消防栓门，阀门开、关无障碍，关闭时无泄漏现象。",
    ),
    ("nozzle", "消防水枪无变形、损伤，开口无破裂。"),
    ("hose", "消防水带无损伤，水带卡口紧固无松动现象，密封橡胶圈完好。"),
    ("hose_placement", "水带采用盘圈挂置或折叠方式放置，便于取用。"),
    (
        "pressure",
        "消防水压满足使用时压力，阀门正常开关，其密封良好无漏水现象。",
    ),
)

CHECK_ITEMS_BY_TYPE = {
    EQUIPMENT_TYPE_EXTINGUISHER: EXTINGUISHER_CHECK_ITEMS,
    EQUIPMENT_TYPE_HYDRANT: HYDRANT_CHECK_ITEMS,
}

# 字段名启发式：先按候选名精确匹配（顺序即优先级），再按包含关键词兜底。
# 飞书子表列名各车间可能不完全一致，投影失败的字段留空，不阻塞台账生成。
_EQUIPMENT_NO_NAMES = (
    "灭火器编号",
    "消防栓编号",
    "器材编号",
    "设备编号",
    "点检卡编号",
    "编号",
)
_EQUIPMENT_NO_KEYWORDS = ("编号",)
_DEPARTMENT_NAMES = (
    "所属部门",
    "归属部门",
    "使用部门",
    "责任部门",
    "部门/车间",
    "所属单位",
    "部门",
    "单位",
)
_DEPARTMENT_KEYWORDS = ("部门", "单位", "车间")
_LOCATION_NAMES = (
    "存放位置",
    "放置地点",
    "所在地点",
    "安装位置",
    "摆放位置",
    "具体位置",
    "位置",
    "地点",
)
_LOCATION_KEYWORDS = ("位置", "地点", "场所")
_EXPIRY_NAMES = (
    "有效日期",
    "有效期至",
    "有效期",
    "到期日期",
    "失效日期",
    "报废日期",
)
_EXPIRY_KEYWORDS = ("有效期", "到期", "失效", "报废")
_TYPE_NAMES = ("器材类型", "设备类型", "消防器材类型", "类型", "类别")
_HYDRANT_KEYWORDS = ("消防栓", "消火栓")
_EXTINGUISHER_KEYWORDS = ("灭火器",)


# ── 镜像字段解析 ──


def _display_text(value: Any) -> str:
    """解码后的字段值 → 展示文本（人员取姓名、多选拼接、链接取标题）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if isinstance(value, dict):
        text = value.get("text") or value.get("link")
        return str(text).strip() if text else ""
    if isinstance(value, list):
        parts = [_display_text(item) for item in value]
        return "、".join(part for part in parts if part)
    return str(value).strip()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _expiry_date_of(fields: dict[str, Any]) -> date | None:
    """有效日期字段值 → date；兼容 2026-02-13 / 2026.02.13 / 2026/2/3。"""
    text = _pick_field_value(fields, _EXPIRY_NAMES, _EXPIRY_KEYWORDS)
    if not text:
        return None
    normalized = (
        text[:10]
        .replace(".", "-")
        .replace("/", "-")
        .replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
    )
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        pass
    try:
        # fromisoformat 不接受非补零写法（2026-2-3），strptime 可以
        return datetime.strptime(normalized, "%Y-%m-%d").date()
    except ValueError:
        return None


def _pick_field_value(
    fields: dict[str, Any],
    exact_names: tuple[str, ...],
    keywords: tuple[str, ...],
) -> str:
    for name in exact_names:
        if name in fields:
            text = _display_text(fields.get(name))
            if text:
                return text
    for name, value in fields.items():
        if _contains_any(name, keywords):
            text = _display_text(value)
            if text:
                return text
    return ""


def _detect_equipment_type(fields: dict[str, Any], tab_name: str) -> str:
    """器材类型：类型字段 > 子表名关键词 > 列名关键词 > 默认灭火器。

    各车间子表通常没有独立的类型列，但列名（灭火器编号 / 消防栓编号）
    与子表名都带器材关键词，足以判型；都无法判定时默认灭火器（数量占绝
    大多数），错判可在飞书加一列「器材类型」纠正。
    """
    type_text = _pick_field_value(fields, _TYPE_NAMES, _TYPE_NAMES)
    if _contains_any(type_text, _HYDRANT_KEYWORDS):
        return EQUIPMENT_TYPE_HYDRANT
    if _contains_any(type_text, _EXTINGUISHER_KEYWORDS):
        return EQUIPMENT_TYPE_EXTINGUISHER
    if _contains_any(tab_name, _HYDRANT_KEYWORDS):
        return EQUIPMENT_TYPE_HYDRANT
    if _contains_any(tab_name, _EXTINGUISHER_KEYWORDS):
        return EQUIPMENT_TYPE_EXTINGUISHER
    field_names = " ".join(fields.keys())
    if _contains_any(field_names, _HYDRANT_KEYWORDS):
        return EQUIPMENT_TYPE_HYDRANT
    if _contains_any(field_names, _EXTINGUISHER_KEYWORDS):
        return EQUIPMENT_TYPE_EXTINGUISHER
    return EQUIPMENT_TYPE_EXTINGUISHER


async def sync_fire_equipment_ledger(db: AsyncSession) -> dict[str, int]:
    """镜像记录 → 消防器材台账投影（幂等，可安全重跑）。"""
    from app.modules.safety.service.page_table import _clean_sub_tables

    config = (
        await db.execute(
            select(SafetyPageFeishuConfig).where(
                SafetyPageFeishuConfig.page_key == FIRE_EQUIPMENT_PAGE_KEY,
                SafetyPageFeishuConfig.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()

    # 页签名取 sub_tables 配置；主绑定若同时出现在 sub_tables 里（仅为携带
    # 显示名），用它的真实表名，否则兜底「主表」。
    tab_names: dict[str, str] = {}
    if config is not None:
        for entry in _clean_sub_tables(config.sub_tables):
            tab_names[entry["table_id"]] = entry["tab_name"]
        primary_table = (config.table_id or "").strip()
        if primary_table:
            tab_names.setdefault(primary_table, "主表")

    now = datetime.now(UTC)
    mirror_rows = (
        (
            await db.execute(
                select(SafetyPageTableMirrorRecord).where(
                    SafetyPageTableMirrorRecord.page_key
                    == FIRE_EQUIPMENT_PAGE_KEY,
                    SafetyPageTableMirrorRecord.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    equipment_rows = (
        (
            await db.execute(
                select(FireEquipment).where(
                    FireEquipment.page_key == FIRE_EQUIPMENT_PAGE_KEY,
                    FireEquipment.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    existing = {(row.table_id, row.record_id): row for row in equipment_rows}
    seen: set[tuple[str, str]] = set()
    created = updated = unchanged = 0
    for mirror in mirror_rows:
        key = (mirror.table_id, mirror.record_id)
        if not mirror.table_id or key in seen:
            continue
        seen.add(key)
        fields = mirror.fields if isinstance(mirror.fields, dict) else {}
        tab_name = tab_names.get(mirror.table_id, mirror.table_id)
        values: dict[str, Any] = {
            "page_key": FIRE_EQUIPMENT_PAGE_KEY,
            "tab_name": tab_name,
            "equipment_type": _detect_equipment_type(fields, tab_name),
            "equipment_no": _pick_field_value(
                fields, _EQUIPMENT_NO_NAMES, _EQUIPMENT_NO_KEYWORDS
            ),
            "department": _pick_field_value(
                fields, _DEPARTMENT_NAMES, _DEPARTMENT_KEYWORDS
            ),
            "location": _pick_field_value(
                fields, _LOCATION_NAMES, _LOCATION_KEYWORDS
            ),
            "fields": fields,
            "search_text": " ".join(
                part
                for part in (
                    _pick_field_value(
                        fields, _EQUIPMENT_NO_NAMES, _EQUIPMENT_NO_KEYWORDS
                    ),
                    _pick_field_value(
                        fields, _DEPARTMENT_NAMES, _DEPARTMENT_KEYWORDS
                    ),
                    _pick_field_value(
                        fields, _LOCATION_NAMES, _LOCATION_KEYWORDS
                    ),
                    tab_name,
                )
                if part
            ),
            "expiry_date": _expiry_date_of(fields),
            "last_synced_at": now,
        }
        current = existing.pop(key, None)
        if current is None:
            db.add(
                FireEquipment(
                    table_id=mirror.table_id,
                    record_id=mirror.record_id,
                    **values,
                )
            )
            created += 1
            continue
        changed = False
        for attr, value in values.items():
            # last_synced_at 每轮都变，不作为业务变更依据
            if attr == "last_synced_at":
                continue
            if getattr(current, attr) != value:
                setattr(current, attr, value)
                changed = True
        current.last_synced_at = now
        if changed:
            updated += 1
        else:
            unchanged += 1
    removed = 0
    for stale in existing.values():
        stale.is_deleted = True
        removed += 1
    await db.commit()
    result = {
        "mirror": len(mirror_rows),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "removed": removed,
    }
    logger.info("消防器材台账投影完成: %s", result)
    return result


async def maybe_project_after_sync(db: AsyncSession, page_key: str) -> None:
    """镜像同步入口的投影分发：仅消防点检页需要，失败不阻塞同步本身。"""
    if page_key != FIRE_EQUIPMENT_PAGE_KEY:
        return
    try:
        await sync_fire_equipment_ledger(db)
    except Exception:
        await db.rollback()
        logger.exception("消防器材台账投影失败（等待下一轮同步兜底）")


# ── 器材与点检查询 ──


def month_start_utc() -> datetime:
    tz = ZoneInfo("Asia/Shanghai")
    now_local = datetime.now(tz)
    start_local = now_local.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return start_local.astimezone(UTC)


def _hidden_by_table(config: SafetyPageFeishuConfig | None) -> dict[str, set[str]]:
    """table_id → 隐藏字段集合（子表未单独配置时沿用主绑定，与镜像页口径一致）。"""
    from app.modules.safety.service.page_table import _clean_sub_tables

    if config is None:
        return {}
    primary_hidden = {
        str(name).strip()
        for name in (config.hidden_field_names or [])
        if str(name).strip()
    }
    result: dict[str, set[str]] = {}
    primary_table = (config.table_id or "").strip()
    if primary_table:
        result[primary_table] = set(primary_hidden)
    for entry in _clean_sub_tables(config.sub_tables):
        hidden = {
            str(name).strip()
            for name in (entry.get("hidden_field_names") or [])
            if str(name).strip()
        }
        result[entry["table_id"]] = hidden or set(primary_hidden)
    return result


# 台账页默认不展示的动态列：与管理列（器材编号/归属部门/存放位置/有效
# 日期）重复或为行号噪音。直接复用投影的候选名单元组，各车间子表用不同
# 列名（车间/单位/地点/失效日期等变体）也能覆盖；完整字段仍在详情抽屉
# 展示，需要时可在飞书设置页调整隐藏字段。
_DEFAULT_SUPPRESSED_COLUMNS = frozenset(
    {
        "序号",
        "体系编号",
        "车间",
        "部门",
        "单位",
        *_EQUIPMENT_NO_NAMES,
        *_DEPARTMENT_NAMES,
        *_LOCATION_NAMES,
        *_EXPIRY_NAMES,
    }
)


async def _collect_columns(
    app_token: str,
    table_ids: list[str],
    hidden_by_table: dict[str, set[str]],
) -> list[dict[str, str]]:
    """按行来源子表收集动态列（跨子表去重，顺序跟飞书 schema）。

    列定义与镜像页同源（飞书实时 schema + Redis 缓存），多维表格增删列后
    页面自动对齐；与管理列重复的列默认抑制，单表 schema 读取失败只跳过
    该表，不阻塞列表。
    """
    from app.modules.safety.service.page_table import _load_field_schema

    seen: dict[str, str] = {}
    for table_id in table_ids:
        hidden = hidden_by_table.get(table_id, set())
        try:
            schema = await _load_field_schema(app_token, table_id)
        except Exception as exc:  # noqa: BLE001 —— 单表失败不阻塞列表
            logger.warning(
                "读取飞书字段 schema 失败（跳过该表动态列）: table=%s err=%s",
                table_id,
                exc,
            )
            continue
        for field in schema:
            if (
                field.name in hidden
                or field.name in seen
                or field.name in _DEFAULT_SUPPRESSED_COLUMNS
            ):
                continue
            seen[field.name] = str(field.kind)
    return [{"name": name, "kind": kind} for name, kind in seen.items()]


async def get_fire_equipment_columns(
    db: AsyncSession, rows: list[FireEquipment]
) -> list[dict[str, str]]:
    """当前结果页涉及子表的动态列清单（供台账页对齐多维表格展示）。"""
    config = await _load_fire_config(db)
    app_token = (config.app_token or "").strip() if config else ""
    if not app_token or not rows:
        return []
    table_ids: list[str] = []
    for row in rows:
        if row.table_id and row.table_id not in table_ids:
            table_ids.append(row.table_id)
    return await _collect_columns(
        app_token, table_ids, _hidden_by_table(config)
    )


async def list_fire_equipment(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    equipment_type: str | None = None,
    keyword: str | None = None,
    table_id: str | None = None,
    month_status: str | None = None,
    expiry_status: str | None = None,
) -> tuple[list[FireEquipment], int]:
    """器材台账分页列表；month_status 按本月是否已点检筛选。"""
    conditions: list[ColumnElement[bool]] = [
        FireEquipment.is_deleted.is_(False)
    ]
    if equipment_type:
        conditions.append(FireEquipment.equipment_type == equipment_type)
    if table_id:
        conditions.append(FireEquipment.table_id == table_id)
    if month_status == "inspected":
        conditions.append(FireEquipment.last_inspected_at >= month_start_utc())
    elif month_status == "uninspected":
        conditions.append(
            or_(
                FireEquipment.last_inspected_at.is_(None),
                FireEquipment.last_inspected_at < month_start_utc(),
            )
        )
    if expiry_status == "expired":
        conditions.append(FireEquipment.expiry_date.isnot(None))
        conditions.append(FireEquipment.expiry_date < date.today())
    elif expiry_status == "expiring":
        today = date.today()
        conditions.append(FireEquipment.expiry_date >= today)
        conditions.append(FireEquipment.expiry_date <= today + timedelta(days=30))
    keyword_text = (keyword or "").strip()
    if keyword_text:
        escaped = keyword_text.replace("\\", "\\\\").replace("%", "\\%").replace(
            "_", "\\_"
        )
        pattern = f"%{escaped}%"
        conditions.append(
            or_(
                FireEquipment.equipment_no.ilike(pattern),
                FireEquipment.department.ilike(pattern),
                FireEquipment.location.ilike(pattern),
                FireEquipment.tab_name.ilike(pattern),
                FireEquipment.search_text.ilike(pattern),
            )
        )
    total = (
        await db.execute(
            select(func.count())
            .select_from(FireEquipment)
            .where(*conditions)
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(FireEquipment)
                .where(*conditions)
                .order_by(
                    FireEquipment.tab_name,
                    FireEquipment.equipment_no,
                    FireEquipment.record_id,
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def get_fire_equipment(db: AsyncSession, equipment_id: UUID) -> FireEquipment:
    equipment = (
        await db.execute(
            select(FireEquipment).where(
                FireEquipment.id == equipment_id,
                FireEquipment.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    if equipment is None:
        raise AppException(message="消防器材不存在或已下架", status_code=404)
    return equipment


async def get_fire_equipment_stats(db: AsyncSession) -> dict[str, Any]:
    """台账概览：类型分布 + 本月点检覆盖 + 镜像绑定/同步状态。"""
    month_start = month_start_utc()
    total, extinguisher, hydrant = (
        await db.execute(
            select(
                func.count(),
                func.count()
                .filter(
                    FireEquipment.equipment_type == EQUIPMENT_TYPE_EXTINGUISHER
                )
                .label("extinguisher"),
                func.count()
                .filter(FireEquipment.equipment_type == EQUIPMENT_TYPE_HYDRANT)
                .label("hydrant"),
            )
            .select_from(FireEquipment)
            .where(FireEquipment.is_deleted.is_(False))
        )
    ).one()
    inspected, failed = (
        await db.execute(
            select(
                func.count()
                .filter(FireEquipment.last_inspected_at >= month_start)
                .label("inspected"),
                func.count()
                .filter(
                    FireEquipment.last_inspected_at >= month_start,
                    FireEquipment.last_inspection_result == "fail",
                )
                .label("failed"),
            )
            .select_from(FireEquipment)
            .where(FireEquipment.is_deleted.is_(False))
        )
    ).one()
    today = date.today()
    in_30 = today + timedelta(days=30)
    expired, expiring = (
        await db.execute(
            select(
                func.count()
                .filter(FireEquipment.expiry_date < today)
                .label("expired"),
                func.count()
                .filter(
                    FireEquipment.expiry_date >= today,
                    FireEquipment.expiry_date <= in_30,
                )
                .label("expiring"),
            )
            .select_from(FireEquipment)
            .where(FireEquipment.is_deleted.is_(False))
        )
    ).one()
    config = (
        await db.execute(
            select(SafetyPageFeishuConfig).where(
                SafetyPageFeishuConfig.page_key == FIRE_EQUIPMENT_PAGE_KEY,
                SafetyPageFeishuConfig.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()
    total = int(total or 0)
    inspected = int(inspected or 0)
    return {
        "total": total,
        "extinguisher_count": int(extinguisher or 0),
        "hydrant_count": int(hydrant or 0),
        "inspected_this_month": inspected,
        "uninspected_this_month": max(total - inspected, 0),
        "failed_this_month": int(failed or 0),
        "expired_count": int(expired or 0),
        "expiring_in_30_count": int(expiring or 0),
        "is_configured": bool(
            config
            and config.is_enabled
            and (config.app_token or "").strip()
            and (config.table_id or "").strip()
        ),
        "writeback_enabled": bool(
            config and (config.writeback_table_id or "").strip()
        ),
        "last_synced_at": config.last_synced_at if config else None,
        "last_sync_status": config.last_sync_status if config else None,
        "last_sync_error": config.last_sync_error if config else None,
    }


async def list_equipment_inspections(
    db: AsyncSession,
    equipment_id: UUID,
    *,
    limit: int = 30,
) -> list[FireInspectionRecord]:
    """单台器材的最近点检记录（新→旧）。"""
    rows = (
        (
            await db.execute(
                select(FireInspectionRecord)
                .where(
                    FireInspectionRecord.equipment_id == equipment_id,
                    FireInspectionRecord.is_deleted.is_(False),
                )
                .order_by(FireInspectionRecord.inspected_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def list_fire_inspections(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    equipment_type: str | None = None,
    result: str | None = None,
    keyword: str | None = None,
    inspected_from: datetime | None = None,
    inspected_to: datetime | None = None,
) -> tuple[list[FireInspectionRecord], int]:
    """点检记录台账分页列表（按点检时间倒序）。"""
    conditions: list[ColumnElement[bool]] = [
        FireInspectionRecord.is_deleted.is_(False)
    ]
    if equipment_type:
        conditions.append(
            FireInspectionRecord.equipment_type == equipment_type
        )
    if result:
        conditions.append(FireInspectionRecord.result == result)
    if inspected_from is not None:
        conditions.append(FireInspectionRecord.inspected_at >= inspected_from)
    if inspected_to is not None:
        conditions.append(FireInspectionRecord.inspected_at < inspected_to)
    keyword_text = (keyword or "").strip()
    if keyword_text:
        escaped = keyword_text.replace("\\", "\\\\").replace("%", "\\%").replace(
            "_", "\\_"
        )
        pattern = f"%{escaped}%"
        conditions.append(
            or_(
                FireInspectionRecord.equipment_no.ilike(pattern),
                FireInspectionRecord.department.ilike(pattern),
                FireInspectionRecord.location.ilike(pattern),
                FireInspectionRecord.inspector_name.ilike(pattern),
            )
        )
    total = (
        await db.execute(
            select(func.count())
            .select_from(FireInspectionRecord)
            .where(*conditions)
        )
    ).scalar_one()
    rows = (
        (
            await db.execute(
                select(FireInspectionRecord)
                .where(*conditions)
                .order_by(FireInspectionRecord.inspected_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


# ── 点检提交 ──


async def create_fire_inspection(
    db: AsyncSession,
    equipment_id: UUID,
    *,
    items: list[dict[str, Any]],
    abnormal_action: str | None,
    inspected_at: datetime | None,
    inspector_id: UUID | None,
    inspector_name: str,
    source: str,
) -> FireInspectionRecord:
    """提交一次点检：检查项必须覆盖整卡，结论自动汇总，回写器材状态。

    检查项 label 以服务端检查卡为准（客户端只传 key/result/remark），
    ``items`` 全量快照落库，检查卡调整后历史记录仍按当时口径展示。
    """
    equipment = await get_fire_equipment(db, equipment_id)
    checklist = CHECK_ITEMS_BY_TYPE.get(equipment.equipment_type)
    if not checklist:
        raise AppException(
            message=f"未知的器材类型: {equipment.equipment_type}",
            status_code=400,
        )
    label_by_key = {key: label for key, label in checklist}
    seen: set[str] = set()
    item_snapshots: list[dict[str, Any]] = []
    for item in items:
        key = str(item.get("key") or "").strip()
        if key not in label_by_key:
            raise AppException(
                message=f"检查项 {key or '(空)'} 不在当前检查卡中", status_code=400
            )
        if key in seen:
            raise AppException(message=f"检查项 {key} 重复提交", status_code=400)
        result = str(item.get("result") or "").strip()
        if result not in ("ok", "fail"):
            raise AppException(
                message=f"检查项 {key} 的结果只能是 ok 或 fail", status_code=400
            )
        seen.add(key)
        remark = str(item.get("remark") or "").strip()
        item_snapshots.append(
            {
                "key": key,
                "label": label_by_key[key],
                "result": result,
                "remark": remark or None,
            }
        )
    missing = [key for key in label_by_key if key not in seen]
    if missing:
        raise AppException(
            message="存在未点检的检查项，请逐项确认后再提交", status_code=400
        )
    failed_items = [
        {"key": item["key"], "label": item["label"]}
        for item in item_snapshots
        if item["result"] == "fail"
    ]
    moment = inspected_at or datetime.now(UTC)
    if moment > datetime.now(UTC):
        raise AppException(message="点检时间不能晚于当前时间", status_code=400)
    record = FireInspectionRecord(
        equipment_id=equipment.id,
        equipment_type=equipment.equipment_type,
        equipment_no=equipment.equipment_no,
        department=equipment.department,
        location=equipment.location,
        items=item_snapshots,
        result="fail" if failed_items else "pass",
        failed_items=failed_items,
        abnormal_action=(abnormal_action or "").strip() or None,
        inspector_id=inspector_id,
        inspector_name=(inspector_name or "").strip(),
        inspected_at=moment,
        source=source if source in ("scan", "web") else "web",
    )
    db.add(record)
    if (
        equipment.last_inspected_at is None
        or moment >= equipment.last_inspected_at
    ):
        equipment.last_inspected_at = moment
        equipment.last_inspection_result = record.result
    await db.commit()
    return record


# ── 点检记录写回飞书 ──

WRITEBACK_TABLE_NAME = "点检记录"

# 回写表列名（与飞书字段名一致；飞书侧表结构变更时同步调整这里）
WB_COL_DATE = "点检日期"
WB_COL_TYPE = "器材类型"
WB_COL_NO = "器材编号"
WB_COL_DEPT = "归属部门"
WB_COL_LOCATION = "存放位置"
WB_COL_RESULT = "检查结果"
WB_COL_FAILED = "不合格项"
WB_COL_ACTION = "异常处理措施"
WB_COL_INSPECTOR = "点检人"
WB_COL_SOURCE = "来源"

# 飞书字段类型：1=多行文本 3=单选 5=日期（bitable 通用枚举）
WRITEBACK_FIELD_SPECS: list[dict[str, Any]] = [
    {"field_name": WB_COL_DATE, "type": 5},
    {
        "field_name": WB_COL_TYPE,
        "type": 3,
        "property": {
            "options": [
                {"name": EQUIPMENT_TYPE_LABELS[EQUIPMENT_TYPE_EXTINGUISHER]},
                {"name": EQUIPMENT_TYPE_LABELS[EQUIPMENT_TYPE_HYDRANT]},
            ]
        },
    },
    {"field_name": WB_COL_NO, "type": 1},
    {"field_name": WB_COL_DEPT, "type": 1},
    {"field_name": WB_COL_LOCATION, "type": 1},
    {
        "field_name": WB_COL_RESULT,
        "type": 3,
        "property": {"options": [{"name": "合格"}, {"name": "不合格"}]},
    },
    {"field_name": WB_COL_FAILED, "type": 1},
    {"field_name": WB_COL_ACTION, "type": 1},
    {"field_name": WB_COL_INSPECTOR, "type": 1},
    {
        "field_name": WB_COL_SOURCE,
        "type": 3,
        "property": {"options": [{"name": "扫码"}, {"name": "网页"}]},
    },
]


async def _load_fire_config(db: AsyncSession) -> SafetyPageFeishuConfig | None:
    return (
        await db.execute(
            select(SafetyPageFeishuConfig).where(
                SafetyPageFeishuConfig.page_key == FIRE_EQUIPMENT_PAGE_KEY,
                SafetyPageFeishuConfig.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()


def _inspection_writeback_fields(record: FireInspectionRecord) -> dict[str, Any]:
    """点检记录 → 回写表字段值（列名与 WRITEBACK_FIELD_SPECS 一致）。"""
    failed_labels = "；".join(
        str(item.get("label") or "")
        for item in (record.failed_items or [])
        if isinstance(item, dict)
    )
    return {
        WB_COL_DATE: int(record.inspected_at.timestamp() * 1000),
        WB_COL_TYPE: EQUIPMENT_TYPE_LABELS.get(
            record.equipment_type, record.equipment_type
        ),
        WB_COL_NO: record.equipment_no,
        WB_COL_DEPT: record.department,
        WB_COL_LOCATION: record.location,
        WB_COL_RESULT: "合格" if record.result == "pass" else "不合格",
        WB_COL_FAILED: failed_labels,
        WB_COL_ACTION: record.abnormal_action or "",
        WB_COL_INSPECTOR: record.inspector_name,
        WB_COL_SOURCE: "扫码" if record.source == "scan" else "网页",
    }


async def ensure_writeback_table(db: AsyncSession) -> dict[str, Any]:
    """一键初始化「点检记录」回写子表（已存在则校验并复用）。

    绑定存 ``page_feishu_configs.writeback_table_id``；若该子表在飞书侧
    被删除，清掉失效绑定后重建。
    """
    config = await _load_fire_config(db)
    if (
        config is None
        or not config.is_enabled
        or not (config.app_token or "").strip()
        or not (config.table_id or "").strip()
    ):
        raise AppException(
            message="请先在「安全飞书设置」完成本页面的表格绑定", status_code=400
        )
    client = SafetyBitableClient(
        app_token=config.app_token, table_id=config.table_id or ""
    )
    existing = (config.writeback_table_id or "").strip()
    if existing:
        tables = await client.list_tables()
        match = next(
            (
                item
                for item in tables
                if str(item.get("table_id") or "") == existing
            ),
            None,
        )
        if match is not None:
            return {
                "table_id": existing,
                "table_name": str(match.get("name") or WRITEBACK_TABLE_NAME),
                "created": False,
            }
        logger.warning(
            "点检记录回写表在飞书侧已不存在，重建: table_id=%s", existing
        )
        config.writeback_table_id = None
        await db.commit()
    table_id, error = await client.create_table(
        WRITEBACK_TABLE_NAME, WRITEBACK_FIELD_SPECS
    )
    if not table_id:
        raise AppException(
            message=f"创建点检记录表失败：{error}", status_code=502
        )
    config.writeback_table_id = table_id
    await db.commit()
    logger.info(
        "点检记录回写表已创建并绑定: table_id=%s base=%s",
        table_id,
        config.app_token,
    )
    return {
        "table_id": table_id,
        "table_name": WRITEBACK_TABLE_NAME,
        "created": True,
    }


async def write_inspection_to_feishu(
    db: AsyncSession, record: FireInspectionRecord
) -> bool:
    """单条点检写回飞书（幂等：已有 feishu_record_id 跳过）。"""
    if record.feishu_record_id:
        return False
    config = await _load_fire_config(db)
    table_id = (config.writeback_table_id or "").strip() if config else ""
    if not config or not table_id:
        return False
    client = SafetyBitableClient(app_token=config.app_token, table_id=table_id)
    feishu_record_id, error = await client.create_record_with_result(
        _inspection_writeback_fields(record), table_id=table_id
    )
    if not feishu_record_id:
        logger.warning(
            "点检记录回写失败: record=%s err=%s", record.id, error
        )
        return False
    record.feishu_record_id = feishu_record_id
    await db.commit()
    logger.info(
        "点检记录回写成功: record=%s feishu=%s", record.id, feishu_record_id
    )
    return True


async def retry_pending_inspection_writebacks(
    db: AsyncSession, *, limit: int = 100
) -> dict[str, int]:
    """补写尚未回写飞书的点检记录（同步循环兜底，幂等）。"""
    config = await _load_fire_config(db)
    if config is None or not (config.writeback_table_id or "").strip():
        return {"pending": 0, "written": 0, "failed": 0}
    records = (
        (
            await db.execute(
                select(FireInspectionRecord)
                .where(
                    FireInspectionRecord.is_deleted.is_(False),
                    FireInspectionRecord.feishu_record_id.is_(None),
                )
                .order_by(FireInspectionRecord.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not records:
        return {"pending": 0, "written": 0, "failed": 0}
    written = failed = 0
    for record in records:
        try:
            if await write_inspection_to_feishu(db, record):
                written += 1
            else:
                failed += 1
        except Exception as exc:  # noqa: BLE001 —— 单条失败不阻塞其余补写
            await db.rollback()
            failed += 1
            logger.warning(
                "点检记录回写补写异常: record=%s err=%s", record.id, exc
            )
    result = {
        "pending": len(records),
        "written": written,
        "failed": failed,
    }
    logger.info("点检记录回写补写完成: %s", result)
    return result


async def _writeback_task(record_id: UUID) -> None:
    """独立会话的后台回写；失败只记日志，等待同步循环补写。"""
    from app.core.database import async_session_factory

    try:
        async with async_session_factory() as session:
            record = await session.get(FireInspectionRecord, record_id)
            if record is None or record.is_deleted:
                return
            await write_inspection_to_feishu(session, record)
    except Exception:
        logger.exception(
            "点检记录后台回写失败（等待同步补写）: record=%s", record_id
        )


def schedule_inspection_writeback(record_id: UUID) -> None:
    """提交成功后调度后台写回（best-effort，不阻塞响应）。"""
    asyncio.create_task(_writeback_task(record_id))
