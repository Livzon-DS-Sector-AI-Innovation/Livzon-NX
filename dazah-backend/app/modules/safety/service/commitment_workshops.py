"""安全承诺车间分填报服务。

流程：定时推车间填报卡（12 车间负责人）→ 各车间提交（覆盖更新）→
全部填齐自动汇总（数值按最后提交预填日报草稿 + 12 份明细存档 +
自动 AI 研判一次 + 推汇总卡到配置群）；催办与推群去重由调用方
（定时生成器 / Redis）控制，本模块只提供幂等的业务动作。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.safety.models import (
    SafetyCommitmentReport,
    SafetyCommitmentWorkshopConfig,
    SafetyCommitmentWorkshopFill,
)
from app.modules.safety.service import safety_commitment_risk
from app.modules.safety.service.safety_commitment import (
    get_or_create_report,
)
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

# 生产口径 12 车间（用户指定名单，含括号身份——括号是车间身份的一部分）
WORKSHOP_SEED_NAMES: tuple[str, ...] = (
    "201-1车间",
    "201-2车间（MC）",
    "201-2车间（DR）",
    "203车间",
    "102-2车间",
    "101-2发酵车间",
    "102-1发酵车间",
    "103发酵车间",
    "菌种中心",
    "污水车间",
    "锅炉",
    "动力部",
)


async def ensure_seed(db: AsyncSession) -> None:
    """配置表为空时播种 12 车间（含软删行则视为已初始化，不重复播种）。"""
    from sqlalchemy import func

    total = await db.scalar(select(func.count(SafetyCommitmentWorkshopConfig.id)))
    if total:
        return
    for idx, name in enumerate(WORKSHOP_SEED_NAMES):
        db.add(
            SafetyCommitmentWorkshopConfig(
                id=uuid4(), workshop_name=name, sort_order=idx, is_enabled=True
            )
        )
    await db.commit()
    logger.info("安全承诺车间配置已播种 %s 个车间", len(WORKSHOP_SEED_NAMES))


async def list_configs(
    db: AsyncSession, *, ensure: bool = True, enabled_only: bool = False
) -> list[SafetyCommitmentWorkshopConfig]:
    if ensure:
        await ensure_seed(db)
    stmt = select(SafetyCommitmentWorkshopConfig).where(
        SafetyCommitmentWorkshopConfig.is_deleted.is_(False)
    )
    if enabled_only:
        stmt = stmt.where(SafetyCommitmentWorkshopConfig.is_enabled.is_(True))
    stmt = stmt.order_by(
        SafetyCommitmentWorkshopConfig.sort_order.asc(),
        SafetyCommitmentWorkshopConfig.created_at.asc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def save_configs(
    db: AsyncSession,
    items: list[dict[str, Any]],
    user_id: UUID | None = None,
) -> list[SafetyCommitmentWorkshopConfig]:
    """批量保存配置：按 id 更新（名称/负责人/排序/启停），无 id 的新增。

    车间名不允许包含 ``|``（飞书卡片按钮 name 编码分隔符）。
    """
    existing = {str(row.id): row for row in await list_configs(db, ensure=True)}
    seen_ids: set[str] = set()
    for idx, payload in enumerate(items):
        ws_id = str(payload.get("id") or "")
        name = str(payload.get("workshop_name") or "").strip()
        if "|" in name:
            raise AppException(message=f"车间名称不能包含「|」：{name}")
        if ws_id and ws_id in existing:
            row = existing[ws_id]
            seen_ids.add(ws_id)
        else:
            row = SafetyCommitmentWorkshopConfig(id=uuid4(), workshop_name=name)
            db.add(row)
        row.workshop_name = name
        row.reporter_open_id = (
            str(payload.get("reporter_open_id") or "").strip() or None
        )
        row.reporter_name = str(payload.get("reporter_name") or "").strip() or None
        row.sort_order = int(payload.get("sort_order") or idx)
        row.is_enabled = bool(payload.get("is_enabled", True))
    await db.commit()
    return await list_configs(db, ensure=False)


async def get_fill(
    db: AsyncSession, report_date: date | str, workshop_name: str
) -> SafetyCommitmentWorkshopFill | None:
    from app.modules.safety.service.safety_commitment import _as_date

    result = await db.execute(
        select(SafetyCommitmentWorkshopFill)
        .where(
            SafetyCommitmentWorkshopFill.is_deleted.is_(False),
            SafetyCommitmentWorkshopFill.report_date == _as_date(report_date),
            SafetyCommitmentWorkshopFill.workshop_name == workshop_name,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_fills(
    db: AsyncSession, report_date: date | str
) -> list[SafetyCommitmentWorkshopFill]:
    from app.modules.safety.service.safety_commitment import _as_date

    result = await db.execute(
        select(SafetyCommitmentWorkshopFill)
        .where(
            SafetyCommitmentWorkshopFill.is_deleted.is_(False),
            SafetyCommitmentWorkshopFill.report_date == _as_date(report_date),
        )
        .order_by(SafetyCommitmentWorkshopFill.filled_at.desc())
    )
    return list(result.scalars().all())


async def save_workshop_fill(
    db: AsyncSession,
    report_date: date | str,
    workshop_name: str,
    fields: dict[str, Any],
    *,
    filled_by_name: str = "",
    filled_by_open_id: str = "",
    source: str = "feishu",
    remark: str | None = None,
) -> SafetyCommitmentWorkshopFill:
    """车间填报落库：同日同车间覆盖更新（可反复重填）。"""
    from app.modules.safety.service.safety_commitment import _as_date

    report_date = _as_date(report_date)
    if not workshop_name:
        raise AppException(message="缺少车间名称")
    fill = await get_fill(db, report_date, workshop_name)
    if fill is None:
        fill = SafetyCommitmentWorkshopFill(
            id=uuid4(), report_date=report_date, workshop_name=workshop_name
        )
        db.add(fill)
    fill.fields = fields
    fill.filled_by_name = filled_by_name or None
    fill.filled_by_open_id = filled_by_open_id or None
    fill.filled_at = datetime.now(UTC)
    fill.source = source
    if remark:
        fill.remark = remark
    try:
        await record_audit_log(
            db,
            action="workshop_fill",
            resource_type="safety_commitment_workshop_fill",
            resource_id=fill.id,
            new_value={"workshop": workshop_name, "source": source},
        )
    except Exception:
        logger.exception("车间填报审计记录失败")
    await db.commit()
    await db.refresh(fill)
    return fill


def _merge_latest(fills: list[SafetyCommitmentWorkshopFill]) -> dict[str, Any]:
    """汇总草稿：以最近提交的车间填报为基线（各车间填全厂口径全套）。"""
    ordered = sorted(
        fills, key=lambda row: row.filled_at or datetime.min.replace(tzinfo=UTC)
    )
    baseline: dict[str, Any] = {}
    for row in ordered:
        fields = row.fields if isinstance(row.fields, dict) else {}
        if fields:
            baseline = fields
    return baseline


def _summary_snapshot(
    fills: list[SafetyCommitmentWorkshopFill],
) -> list[dict[str, Any]]:
    ordered = sorted(
        fills, key=lambda row: row.filled_at or datetime.min.replace(tzinfo=UTC)
    )
    return [
        {
            "workshop_name": row.workshop_name,
            "filled_by_name": row.filled_by_name or "",
            "filled_at": (row.filled_at or datetime.now(UTC)).isoformat(),
            "fields": dict(row.fields or {}),
            "remark": row.remark or "",
        }
        for row in ordered
    ]


async def summarize_if_complete(
    db: AsyncSession, report_date: date | str, *, user_id: UUID | None = None
) -> tuple[bool, SafetyCommitmentReport | None]:
    """启用车间全部填齐时汇总进日报：返回（是否本次执行了汇总, 日报）。

    幂等：已汇总过（workshop_summary 非空）直接返回 False。汇总动作：
    草稿取最近提交的车间填报 → 写日报 + 明细快照 → 自动 AI 研判一次
    （失败不阻断）→ 审计。推群由调用方完成。
    """
    from app.modules.safety.service.safety_commitment import _as_date

    report_date = _as_date(report_date)
    configs = await list_configs(db, ensure=True, enabled_only=True)
    fills = await list_fills(db, report_date)
    filled_names = {row.workshop_name for row in fills}
    missing = [c.workshop_name for c in configs if c.workshop_name not in filled_names]
    if missing:
        return False, None

    report, _created = await get_or_create_report(db, report_date, user_id=user_id)
    if report.workshop_summary:
        return False, report
    report.workshop_summary = _summary_snapshot(fills)
    report.enterprise_status = _merge_latest(fills)
    report.fill_source = "feishu_summary"
    try:
        await record_audit_log(
            db,
            action="workshop_summary",
            user_id=user_id,
            resource_type="safety_commitment_report",
            resource_id=report.id,
            new_value={"workshops": len(fills)},
        )
    except Exception:
        logger.exception("车间汇总审计记录失败")
    await db.commit()
    await db.refresh(report)
    try:
        await safety_commitment_risk.generate_risk_assessment(db, report)
        await db.commit()
        await db.refresh(report)
    except Exception:
        logger.exception("车间汇总后自动 AI 研判失败 date=%s", report_date)
        await db.rollback()
    logger.info("车间填报汇总完成: date=%s 车间数=%s", report_date, len(fills))
    return True, report


async def missing_workshops(
    db: AsyncSession, report_date: date | str
) -> list[SafetyCommitmentWorkshopConfig]:
    """返回当日尚未填报的启用车间（含负责人，供催办）。"""
    from app.modules.safety.service.safety_commitment import _as_date

    configs = await list_configs(db, ensure=True, enabled_only=True)
    fills = await list_fills(db, _as_date(report_date))
    filled_names = {row.workshop_name for row in fills}
    return [c for c in configs if c.workshop_name not in filled_names]


async def fills_progress(db: AsyncSession, report_date: date | str) -> dict[str, Any]:
    """当日填报进度（前端展示）：启用车间清单 + 各车间填报状态。"""
    from app.modules.safety.service.safety_commitment import _as_date

    report_date = _as_date(report_date)
    configs = await list_configs(db, ensure=True, enabled_only=True)
    fills = {row.workshop_name: row for row in await list_fills(db, report_date)}
    rows = []
    filled = 0
    for cfg in configs:
        fill = fills.get(cfg.workshop_name)
        if fill is not None:
            filled += 1
        rows.append(
            {
                "workshop_name": cfg.workshop_name,
                "reporter_name": cfg.reporter_name or "",
                "reporter_open_id": cfg.reporter_open_id or "",
                "filled": fill is not None,
                "filled_by_name": (fill.filled_by_name if fill else "") or "",
                "filled_at": (
                    fill.filled_at.isoformat() if fill and fill.filled_at else None
                ),
                "fields": dict(fill.fields or {}) if fill else {},
                "remark": (fill.remark if fill else "") or "",
                "source": (fill.source if fill else "") or "",
            }
        )
    return {
        "report_date": report_date.isoformat()
        if hasattr(report_date, "isoformat")
        else str(report_date),
        "total": len(rows),
        "filled": filled,
        "workshops": rows,
    }
