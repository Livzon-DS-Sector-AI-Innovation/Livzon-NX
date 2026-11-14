"""安全承诺日报服务（应急〔2018〕74号 承诺公告制度）。

日报按自然日一条：首次访问惰性初始化（企业状态/承诺正文继承最近一条
历史记录，便于「确认式填报」），AI 研判在无结果时自动生成一次；
发布以主要负责人名义落承诺公告。滚动信息卡（安全承诺信息/重大危险源
信息）为全局内容，独立 CRUD。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import (
    CommitmentCardType,
    CommitmentReportStatus,
    SafetyCommitmentCard,
    SafetyCommitmentReport,
)
from app.modules.safety.schemas.safety_commitment import (
    SafetyCommitmentCardCreateRequest,
    SafetyCommitmentCardUpdateRequest,
    SafetyCommitmentUpdateRequest,
)
from app.modules.safety.service import safety_commitment_risk
from app.platform.audit.service import record_audit_log

logger = logging.getLogger(__name__)

_CN_TZ = timezone(timedelta(hours=8))


def shanghai_today() -> date:
    """承诺日报按北京时间自然日划分（容器时区为 UTC，不能用 date.today()）。"""
    return datetime.now(_CN_TZ).date()


def _as_date(value: date | str) -> date:
    """飞书卡片/调度器传入 'YYYY-MM-DD' 字符串；asyncpg 的 DATE 参数只收 date。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise AppException(message=f"日期格式无效：{value}") from exc

DEFAULT_COMMITMENT_TEMPLATE = """今日本公司郑重向全体员工作出安全承诺：
一、当日所有生产装置、罐区、仓库均处于安全运行状态，各类安全风险得到有效管控；
二、全员、全过程、全天候、全方位落实安全生产主体责任；
三、特殊作业严格履行风险辨识、程序确认和许可审批，现场监督到位；
四、事故隐患已按规定排查治理，重大隐患均已落实治理措施；
五、储区、仓库等重大危险源处于安全状态，安全包保责任制已落实。

承诺人（主要负责人）：____
承诺日期：{date}
"""


def default_enterprise_status() -> dict[str, Any]:
    """企业状态结构化默认值（承诺公告内容项，74号文）。"""
    return {
        # 车间与装置运行状态
        "workshop_total": 0,
        "workshop_running": 0,
        "workshop_stopped": 0,
        "workshop_maintenance": 0,
        "trial_production_count": 0,
        "startup_count": 0,
        "shutdown_count": 0,
        # 当日特殊危险作业
        "special_work_total": 0,
        "special_work": {
            "hot_work_level1": 0,
            "hot_work_level2": 0,
            "height_work": 0,
            "confined_space": 0,
            "other": 0,
        },
        # 一般安全生产隐患
        "hazard_count": 0,
        "hazard_rectified": None,
        "hazard_temp_measures": None,
        # 承包商作业
        "contractor_work": False,
        "contractor_trained": None,
        # 重大危险源
        "major_hazard_safe": None,
        "responsibility_implemented": None,
        "person_main": "",
        "person_tech": "",
        "person_ops": "",
    }


def _to_item(report: SafetyCommitmentReport) -> dict[str, Any]:
    return {
        "id": report.id,
        "report_date": report.report_date,
        "enterprise_status": dict(report.enterprise_status or {}),
        "commitment_text": report.commitment_text,
            "risk_assessment": (
            dict(report.risk_assessment) if report.risk_assessment else None
        ),
        "status": report.status,
        "publisher_name": report.publisher_name,
        "published_at": report.published_at,
        "fill_source": report.fill_source,
        "workshop_summary": list(report.workshop_summary or []) or None,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


async def _audit(
    db: AsyncSession,
    action: str,
    resource_id: UUID | None = None,
    user_id: UUID | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    try:
        await record_audit_log(
            db,
            action=action,
            user_id=user_id,
            resource_type="safety_commitment_report",
            resource_id=resource_id,
            new_value=new_value,
        )
    except Exception:
        logger.exception("安全承诺审计日志记录失败 (%s)", action)


async def _get_by_date(
    db: AsyncSession, report_date: Any
) -> SafetyCommitmentReport | None:
    result = await db.execute(
        select(SafetyCommitmentReport)
        .where(
            SafetyCommitmentReport.is_deleted.is_(False),
            SafetyCommitmentReport.report_date == report_date,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_previous(
    db: AsyncSession, report_date: Any
) -> SafetyCommitmentReport | None:
    result = await db.execute(
        select(SafetyCommitmentReport)
        .where(
            SafetyCommitmentReport.is_deleted.is_(False),
            SafetyCommitmentReport.report_date < report_date,
        )
        .order_by(SafetyCommitmentReport.report_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_report(
    db: AsyncSession, report_date: date | str, user_id: UUID | None = None
) -> tuple[SafetyCommitmentReport, bool]:
    """取指定日期日报，不存在则惰性初始化（继承上一日 + 自动 AI 研判）。"""
    report_date = _as_date(report_date)
    existing = await _get_by_date(db, report_date)
    if existing is not None:
        return existing, False

    previous = await _latest_previous(db, report_date)
    inherited_status = (
        dict(previous.enterprise_status)
        if previous and previous.enterprise_status
        else default_enterprise_status()
    )
    commitment_text = (
        previous.commitment_text
        if previous and previous.commitment_text
        else DEFAULT_COMMITMENT_TEMPLATE.format(date=report_date)
    )
    report = SafetyCommitmentReport(
        id=uuid4(),
        report_date=report_date,
        enterprise_status=inherited_status,
        commitment_text=commitment_text,
        status=CommitmentReportStatus.DRAFT.value,
    )
    db.add(report)
    await db.flush()

    # AI 研判不再在创建时自动生成（数据不全时无意义），改由车间汇总
    # 完成时自动生成一次；网页端保留手动「重新研判」。
    await _audit(db, "create", resource_id=report.id, user_id=user_id)
    await db.commit()
    await db.refresh(report)
    # 信息卡从未创建过时播种 74 号文要点（可编辑/删除）；失败不影响日报
    try:
        await seed_default_cards_if_empty(db)
    except Exception:
        logger.exception("安全承诺默认信息卡播种失败")
        await db.rollback()
    return report, True


async def get_report_by_date(
    db: AsyncSession, report_date: date | str
) -> dict[str, Any]:
    """只读查询指定日期日报（历史查看，不落新记录）。"""
    report = await _get_by_date(db, _as_date(report_date))
    if report is None:
        raise AppException(status_code=404, message="该日期无安全承诺日报")
    return _to_item(report)


async def list_reports(
    db: AsyncSession, limit: int = 30, offset: int = 0
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(SafetyCommitmentReport)
        .where(SafetyCommitmentReport.is_deleted.is_(False))
        .order_by(SafetyCommitmentReport.report_date.desc())
        .offset(offset)
        .limit(min(limit, 100))
    )
    return [_to_item(row) for row in result.scalars().all()]


async def update_report(
    db: AsyncSession,
    report_id: UUID,
    data: SafetyCommitmentUpdateRequest,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    report = await db.get(SafetyCommitmentReport, report_id)
    if report is None or report.is_deleted:
        raise NotFoundException("安全承诺日报")
    if data.enterprise_status is not None:
        report.enterprise_status = data.enterprise_status
        report.fill_source = "web"
    if data.commitment_text is not None:
        report.commitment_text = data.commitment_text
    report.updated_by = user_id
    await _audit(db, "update", resource_id=report.id, user_id=user_id)
    await db.commit()
    await db.refresh(report)
    return _to_item(report)


async def save_enterprise_status_from_feishu(
    db: AsyncSession, report_date: date | str, enterprise_status: dict[str, Any]
) -> SafetyCommitmentReport:
    """飞书卡片填报落库：不存在则先惰性初始化，再整体覆盖企业状态。"""
    report, _created = await get_or_create_report(db, report_date)
    report.enterprise_status = enterprise_status
    report.fill_source = "feishu"
    report.updated_at = datetime.now(UTC)
    await _audit(db, "update", resource_id=report.id)
    await db.commit()
    await db.refresh(report)
    return report


async def publish_report(
    db: AsyncSession,
    report_id: UUID,
    publisher_name: str,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """以主要负责人名义发布当日承诺公告。"""
    report = await db.get(SafetyCommitmentReport, report_id)
    if report is None or report.is_deleted:
        raise NotFoundException("安全承诺日报")
    if not (report.enterprise_status or {}):
        raise AppException(message="请先完善当日企业状态后再发布承诺公告")
    if not (report.commitment_text or "").strip():
        raise AppException(message="请先填写企业安全承诺正文")
    report.status = CommitmentReportStatus.PUBLISHED.value
    report.publisher_name = publisher_name.strip()
    report.published_by = user_id
    report.published_at = datetime.now(UTC)
    await _audit(
        db,
        "publish",
        resource_id=report.id,
        user_id=user_id,
        new_value={"publisher_name": report.publisher_name},
    )
    await db.commit()
    await db.refresh(report)
    return _to_item(report)


# ==================== 滚动信息卡（安全承诺信息 / 重大危险源信息） ====================


async def list_cards(
    db: AsyncSession, card_type: str | None = None
) -> list[SafetyCommitmentCard]:
    stmt = select(SafetyCommitmentCard).where(
        SafetyCommitmentCard.is_deleted.is_(False)
    )
    if card_type:
        stmt = stmt.where(SafetyCommitmentCard.card_type == card_type)
    stmt = stmt.order_by(
        SafetyCommitmentCard.sort_order.asc(), SafetyCommitmentCard.created_at.asc()
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _card_to_item(card: SafetyCommitmentCard) -> dict[str, Any]:
    return {
        "id": card.id,
        "card_type": card.card_type,
        "title": card.title or "",
        "content": card.content or "",
        "sort_order": card.sort_order,
        "updated_at": card.updated_at,
    }


async def create_card(
    db: AsyncSession,
    data: SafetyCommitmentCardCreateRequest,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    valid_types = (
        CommitmentCardType.COMMITMENT.value,
        CommitmentCardType.MAJOR_HAZARD.value,
    )
    if data.card_type not in valid_types:
        raise AppException(message="卡片类型无效")
    card = SafetyCommitmentCard(
        card_type=data.card_type,
        title=data.title.strip(),
        content=data.content,
        sort_order=data.sort_order,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)
    return _card_to_item(card)


async def update_card(
    db: AsyncSession,
    card_id: UUID,
    data: SafetyCommitmentCardUpdateRequest,
) -> dict[str, Any]:
    card = await db.get(SafetyCommitmentCard, card_id)
    if card is None or card.is_deleted:
        raise NotFoundException("安全承诺信息卡")
    if data.title is not None:
        card.title = data.title.strip()
    if data.content is not None:
        card.content = data.content
    if data.sort_order is not None:
        card.sort_order = data.sort_order
    await db.commit()
    await db.refresh(card)
    return _card_to_item(card)


async def delete_card(db: AsyncSession, card_id: UUID) -> None:
    card = await db.get(SafetyCommitmentCard, card_id)
    if card is None or card.is_deleted:
        raise NotFoundException("安全承诺信息卡")
    card.is_deleted = True
    await db.commit()


async def seed_default_cards_if_empty(db: AsyncSession) -> None:
    """信息卡从未创建过时播种两条 74 号文要点，便于开箱编辑。

    计数含软删记录：用户删除默认卡后不会在次日被重新播种。
    """
    total = await db.scalar(select(func.count(SafetyCommitmentCard.id)))
    if total:
        return
    defaults = [
        SafetyCommitmentCard(
            id=uuid4(),
            card_type=CommitmentCardType.COMMITMENT.value,
            title="安全承诺公告制度",
            content=(
                "依据《危险化学品企业安全风险研判与承诺公告制度》"
                "（应急〔2018〕74号）：公司以主要负责人名义每日签署安全承诺公告，"
                "每天上午10时更新，在工厂主门外公告栏及门岗显示屏公开。"
                "仅在装置、罐区、仓库安全运行、重大隐患落实治理措施、"
                "主要风险可控的前提下方可发布当日承诺。"
            ),
            sort_order=0,
        ),
        SafetyCommitmentCard(
            id=uuid4(),
            card_type=CommitmentCardType.MAJOR_HAZARD.value,
            title="重大危险源管控要点",
            content=(
                "储罐、管道、机泵、阀门及仪表完好无泄漏；液位、温度、压力不超限；"
                "内浮顶储罐浮盘不得落底；切水、切罐、装卸车时人员在岗；"
                "可燃及有毒气体报警联锁可靠；仓库按标准分区分类储存，"
                "不超量、不超品种，禁配物质不混放。"
            ),
            sort_order=0,
        ),
    ]
    for card in defaults:
        db.add(card)
    await db.commit()
