"""培训计划跟踪 Service."""

import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.hr.models import (
    AnnualTrainingPlan,
    PlanTrackingRecord,
    TrainingSession,
)
from app.modules.hr.plan_tracking_repository import PlanTrackingRepository

logger = logging.getLogger(__name__)


def _parse_month_int(value: str | None) -> int | None:
    """归一化月份字符串为整数月，兼容 "1"/"01"/"1月" 等格式."""
    if not value:
        return None
    m = re.search(r"\d{1,2}", str(value))
    if not m:
        return None
    try:
        month = int(m.group())
    except ValueError:
        return None
    return month if 1 <= month <= 12 else None


def _format_session_time(session: TrainingSession) -> str:
    """格式化单场培训时间为「日期 时间段」（如 8月15日 14:00-16:00）."""
    if not session.training_date:
        return ""
    text = f"{session.training_date.month}月{session.training_date.day}日"
    if session.time_start and session.time_end:
        text += f" {session.time_start}-{session.time_end}"
    elif session.time_start:
        text += f" {session.time_start}"
    return text


class PlanTrackingService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = PlanTrackingRepository(session)
        self.session = session

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        plan_id: UUID | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[PlanTrackingRecord], int]:
        return await self.repo.list_records(
            page=page,
            page_size=page_size,
            plan_id=plan_id,
            dept_alias_set=dept_alias_set,
        )

    async def get_by_id(self, record_id: UUID) -> PlanTrackingRecord | None:
        return await self.repo.get_by_id(record_id)

    async def create(self, data: dict[str, Any]) -> PlanTrackingRecord:
        record = PlanTrackingRecord(**data)
        return await self.repo.create(record)

    async def update(
        self, record_id: UUID, data: dict[str, Any]
    ) -> PlanTrackingRecord | None:
        record = await self.repo.get_by_id(record_id)
        if not record:
            return None
        await self.repo.update(record, data)
        # updated_at 由服务端 onupdate 生成，flush 后处于过期态；
        # 显式刷新避免响应序列化时触发异步懒加载（MissingGreenlet）
        await self.session.refresh(record)
        return record

    async def delete(self, record_id: UUID) -> bool:
        record = await self.repo.get_by_id(record_id)
        if not record:
            return False
        await self.repo.delete(record)
        return True

    # ─── 按年按月自动录入（公司级/部门级）───

    async def _find_period_plans(
        self,
        year: int,
        plan_level: str,
        department: str | None,
        dept_alias_set: set[str] | None = None,
    ) -> list[AnnualTrainingPlan]:
        """查找年度+级别(+部门)的计划；公司级取最新一个，部门级按部门去重取最新."""
        query = (
            select(AnnualTrainingPlan)
            .options(selectinload(AnnualTrainingPlan.items))
            .where(
                AnnualTrainingPlan.is_deleted.is_(False),
                AnnualTrainingPlan.year == year,
                AnnualTrainingPlan.plan_level == plan_level,
            )
        )
        if plan_level == "部门级" and department:
            query = query.where(AnnualTrainingPlan.department == department)
        elif plan_level == "部门级" and dept_alias_set is not None:
            # 部门级数据隔离：部门级汇总仅包含可见部门
            query = query.where(AnnualTrainingPlan.department.in_(dept_alias_set))
        query = query.order_by(
            AnnualTrainingPlan.department.asc(), AnnualTrainingPlan.created_at.desc()
        )
        result = await self.session.execute(query)
        plans = list(result.scalars().all())
        if plan_level == "公司级":
            # 公司级取最新创建的一个计划（查询已按 created_at.desc 排序）
            return plans[:1]
        # 部门级：同一部门多个计划时取最新者，全部部门汇总
        seen: set[str] = set()
        out: list[AnnualTrainingPlan] = []
        for p in plans:
            if p.department in seen:
                continue
            seen.add(p.department)
            out.append(p)
        return out

    async def _aggregate_sessions(self, plan_item_ids: list[UUID]) -> dict[UUID, str]:
        """按计划明细聚合关联培训资料（TrainingSession）的多场时间，每场一行."""
        if not plan_item_ids:
            return {}
        query = (
            select(TrainingSession)
            .where(
                TrainingSession.is_deleted.is_(False),
                TrainingSession.plan_item_id.in_(plan_item_ids),
            )
            .order_by(
                TrainingSession.training_date.asc(), TrainingSession.created_at.asc()
            )
        )
        result = await self.session.execute(query)
        grouped: dict[UUID, list[str]] = {}
        for s in result.scalars().all():
            line = _format_session_time(s)
            if line and s.plan_item_id:
                grouped.setdefault(s.plan_item_id, []).append(line)
        return {k: "\n".join(v) for k, v in grouped.items()}

    async def sync_period(
        self,
        year: int,
        month: int,
        plan_level: str,
        department: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> list[PlanTrackingRecord]:
        """幂等自动录入：将年度计划当月明细补录为跟踪记录，并汇总培训会话时间.

        - 部门级未指定部门时全部部门汇总；培训对象前拼接部门（如「QA 全员」）
        - 实际培训时间自动汇总关联培训资料的多场时间（每场一行）；
          仅在为空或等于上次汇总值时回填，手工修改过的不覆盖
        """
        plans = await self._find_period_plans(
            year, plan_level, department, dept_alias_set=dept_alias_set
        )
        existing = {
            r.plan_item_id: r
            for r in await self.repo.list_by_period(
                year=year,
                month=month,
                plan_level=plan_level,
                department=department,
                dept_alias_set=dept_alias_set,
            )
            if r.plan_item_id
        }
        created: list[PlanTrackingRecord] = []
        for plan in plans:
            for item in plan.items:
                if item.is_deleted:
                    continue
                if _parse_month_int(item.training_month or item.month) != month:
                    continue
                if item.id in existing:
                    continue
                audience = item.target_audience_new or item.target_audience
                if plan_level == "部门级" and audience:
                    audience = f"{plan.department} {audience}"
                record = PlanTrackingRecord(
                    plan_id=plan.id,
                    plan_item_id=item.id,
                    year=year,
                    month=str(month),
                    plan_level=plan_level,
                    department=plan.department,
                    sort_order=item.sort_order,
                    training_content=item.content_textbook or item.content_and_textbook,
                    target_audience=audience,
                    training_type=item.training_type,
                    tracking_assessment_method=item.assessment_method,
                )
                await self.repo.create(record)
                created.append(record)
        await self.session.flush()
        if created:
            # server_default 会使新行
            # is_completed=false；显式置 NULL 保持未跟踪态（□是
            # □否）
            await self.session.execute(
                sa_update(PlanTrackingRecord)
                .where(PlanTrackingRecord.id.in_([r.id for r in created]))
                .values(is_completed=None)
            )
            await self.session.flush()

        # 培训会话时间汇总回填（仅覆盖未手工修改过的记录）
        records = await self.repo.list_by_period(
            year=year,
            month=month,
            plan_level=plan_level,
            department=department,
            dept_alias_set=dept_alias_set,
        )
        aggregated = await self._aggregate_sessions(
            [r.plan_item_id for r in records if r.plan_item_id]
        )
        changed = False
        for r in records:
            if not r.plan_item_id:
                continue
            agg = aggregated.get(r.plan_item_id, "")
            manual_modified = bool(r.actual_time) and r.actual_time != (
                r.sessions_snapshot or ""
            )
            if manual_modified:
                continue
            if (r.actual_time or "") != agg:
                r.actual_time = agg or None
                changed = True
            if (r.sessions_snapshot or "") != agg:
                r.sessions_snapshot = agg or None
                changed = True
        if changed:
            await self.session.flush()
            records = await self.repo.list_by_period(
                year=year,
                month=month,
                plan_level=plan_level,
                department=department,
                dept_alias_set=dept_alias_set,
            )
        return records
