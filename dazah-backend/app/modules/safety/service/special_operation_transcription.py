"""特殊作业台账自动转录：飞书「次日特殊危险作业审批」镜像 → 本地报备表。

由页面镜像同步循环在特殊危险作业页同步完成后自动调用（也可手动执行）。
按 report_no 幂等 upsert：飞书已删除或无作业类型的记录跳过；值未变化的
记录跳过写库。转录后调用关键作业规则重算，保证标记与规则一致。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.safety.models import (
    SafetyPageTableMirrorRecord,
    SpecialOperationReport,
)

logger = logging.getLogger(__name__)

SOURCE_PAGE_KEY = "safety:ops-safety:special-danger-work"

TYPE_MAP = {
    "动火作业": "hot_work",
    "受限空间作业": "confined_space",
    "盲板抽堵作业": "blind_plate",
    "高处作业": "height_work",
    "吊装作业": "lifting",
    "临电作业": "temporary_electricity",
    "动土作业": "excavation",
    "断路作业": "road_breaking",
}

LEVEL_MAP = {
    "特级": "special",
    "一级": "grade1",
    "二级": "grade2",
    "三级": "grade2",
    "四级": "grade2",
    "不涉及": "not_applicable",
    "涉及有毒有害、易燃、易爆（受限空间）": "not_applicable",
    "不涉及有毒有害、易燃、易爆（受限空间）": "not_applicable",
}

STATUS_MAP = {
    "已通过": "approved",
    "审批中": "submitted",
    "已拒绝": "rejected",
    "已取消": "rejected",
    "已终止": "rejected",
    "已撤回": "rejected",
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _person_names(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(
            str(item.get("name") or "").strip()
            for item in value
            if isinstance(item, dict) and item.get("name")
        )
    return ""


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if item)
    return _text(value)


def _date(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _truncate(value: str, limit: int) -> str:
    return value[:limit]


def _notes(fields: dict[str, Any]) -> str:
    parts: list[str] = []
    for label, value in [
        ("施工单位", _text(fields.get("施工单位"))),
        ("关联作业", _join_list(fields.get("关联作业"))),
        ("是否提级管理", _text(fields.get("作业是否提级管理"))),
        ("是否周六日节假日", _text(fields.get("是否为周六、日\\节假日"))),
        ("是否防爆区", _text(fields.get("是否为防爆区"))),
        ("发起人部门", _text(fields.get("发起人部门"))),
        ("作业时长(h)", _text(fields.get("时长"))),
    ]:
        if value:
            parts.append(f"{label}：{value}")
    for name in ("已签批的特殊作业票及关联票", "已验收的特殊作业票及关联票"):
        url_value = fields.get(name)
        if isinstance(url_value, dict) and url_value.get("link"):
            parts.append(f"{name}：{url_value['link']}")
    return "；".join(parts)


def _report_no(fields: dict[str, Any], record_id: str) -> str:
    url_value = fields.get("申请编号")
    raw = url_value.get("text") if isinstance(url_value, dict) else url_value
    return _text(raw) or f"FEISHU-{record_id[-12:]}"


def _build_values(fields: dict[str, Any]) -> dict[str, Any] | None:
    """把镜像字段映射为台账列值；无作业类型等无法映射时返回 None（跳过）。"""
    operation_type = TYPE_MAP.get(_text(fields.get("作业类型")))
    if operation_type is None:
        return None
    feishu_status = _text(fields.get("申请状态"))
    status = STATUS_MAP.get(feishu_status, "submitted")
    initiator = _person_names(fields.get("发起人"))
    return {
        "operation_type": operation_type,
        "operation_level": LEVEL_MAP.get(_text(fields.get("作业分级")), "grade2"),
        "department": _truncate(_text(fields.get("部门")), 100) or None,
        "location": _truncate(_text(fields.get("作业地点")), 255) or None,
        "work_description": _text(fields.get("作业内容")) or None,
        "planned_start_time": _date(fields.get("作业开始时间")),
        "planned_end_time": _date(fields.get("作业结束时间")),
        "work_leader_name": _truncate(initiator, 100) or None,
        "operator_names": _truncate(
            _text(fields.get("特殊作业人员（姓名+工种）")), 2000
        )
        or None,
        "guardian_name": _truncate(_person_names(fields.get("监护人")), 100) or None,
        "applicant_name": _truncate(initiator, 100) or None,
        "approved_at": _date(fields.get("完成时间")) if status == "approved" else None,
        "rejection_reason": (
            f"飞书状态：{feishu_status}"
            if status == "rejected" and feishu_status != "已拒绝"
            else None
        ),
        "status": status,
        "notes": _notes(fields) or None,
        # is_critical / is_critical_reason 由 recalculate_critical_flags 独占管理，
        # 转录不携带，避免每轮与重算互相覆盖被判为“已变化”
    }


async def sync_special_operation_ledger(db: AsyncSession) -> dict[str, int]:
    """镜像 → 台账转录 + 关键作业重算（幂等，可安全重跑）。"""
    from app.modules.safety.service.special_operation_report import (
        SpecialOperationReportService,
    )

    mirror_rows = (
        (
            await db.execute(
                select(SafetyPageTableMirrorRecord).where(
                    SafetyPageTableMirrorRecord.page_key == SOURCE_PAGE_KEY,
                    SafetyPageTableMirrorRecord.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    existing = {
        row.report_no: row
        for row in (
            (
                await db.execute(
                    select(SpecialOperationReport).where(
                        SpecialOperationReport.is_deleted.is_(False)
                    )
                )
            )
            .scalars()
            .all()
        )
    }

    created = updated = skipped = unchanged = 0
    for mirror in mirror_rows:
        fields = mirror.fields if isinstance(mirror.fields, dict) else {}
        if _text(fields.get("申请状态")) == "已删除":
            skipped += 1
            continue
        values = _build_values(fields)
        if values is None:
            skipped += 1
            continue

        report_no = _report_no(fields, mirror.record_id)
        current = existing.get(report_no)
        if current is None:
            db.add(SpecialOperationReport(report_no=report_no, **values))
            created += 1
            continue

        changed = False
        for key, value in values.items():
            if getattr(current, key) != value:
                setattr(current, key, value)
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    await db.commit()

    recalc = await SpecialOperationReportService(db).recalculate_critical_flags()
    result = {
        "mirror": len(mirror_rows),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "critical": recalc["critical"],
    }
    logger.info("特殊作业台账转录完成: %s", result)
    return result
