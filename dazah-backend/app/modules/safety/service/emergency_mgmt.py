"""应急管理：应急预案台账、演练计划/记录与应急物资。"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import EmergencyDrill, EmergencyPlan, EmergencySupply
from app.modules.safety.schemas.emergency_mgmt import (
    EmergencyDrillCreate,
    EmergencyDrillUpdate,
    EmergencyMgmtStatsResponse,
    EmergencyPlanCreate,
    EmergencyPlanUpdate,
    EmergencySupplyCreate,
    EmergencySupplyUpdate,
)

PLAN_TYPES = {"comprehensive", "special", "onsite"}
PLAN_STATUSES = {"active", "revising", "obsolete"}
DRILL_TYPES = {"tabletop", "practical", "comprehensive"}
DRILL_STATUSES = {"planned", "done", "cancelled"}
SUPPLY_CATEGORIES = {
    "firefighting",
    "protective",
    "medical",
    "communication",
    "leak_sealing",
    "other",
}
SUPPLY_STATUSES = {"good", "repair", "scrapped"}


def plan_search_text(plan: EmergencyPlan) -> str:
    return " ".join(
        part
        for part in (plan.name, plan.plan_type, plan.department, plan.version)
        if part
    )


def drill_search_text(drill: EmergencyDrill) -> str:
    return " ".join(
        part
        for part in (
            drill.name,
            drill.drill_type,
            drill.scenario,
            drill.plan_name,
            drill.location,
            drill.departments,
        )
        if part
    )


def supply_search_text(supply: EmergencySupply) -> str:
    return " ".join(
        part
        for part in (
            supply.name,
            supply.category,
            supply.spec,
            supply.location,
            supply.department,
        )
        if part
    )


class EmergencyMgmtService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------- 应急预案 ----------

    async def list_plans(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        plan_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[EmergencyPlan], int]:
        conditions: list[ColumnElement[bool]] = [EmergencyPlan.is_deleted.is_(False)]
        if plan_type:
            conditions.append(EmergencyPlan.plan_type == plan_type)
        if status:
            conditions.append(EmergencyPlan.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    EmergencyPlan.name.ilike(pattern),
                    EmergencyPlan.search_text.ilike(pattern),
                )
            )
        total = (
            await self.db.execute(
                select(func.count()).select_from(EmergencyPlan).where(*conditions)
            )
        ).scalar() or 0
        rows = await self.db.execute(
            select(EmergencyPlan)
            .where(*conditions)
            .order_by(EmergencyPlan.status.asc(), EmergencyPlan.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def get_plan(self, plan_id: UUID) -> EmergencyPlan | None:
        result = await self.db.execute(
            select(EmergencyPlan).where(
                EmergencyPlan.id == plan_id, EmergencyPlan.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_plan(
        self, data: EmergencyPlanCreate, user_id: UUID | None = None
    ) -> EmergencyPlan:
        if data.plan_type not in PLAN_TYPES:
            raise AppException(status_code=422, message="无效的预案类型")
        if data.status not in PLAN_STATUSES:
            raise AppException(status_code=422, message="无效的预案状态")
        plan = EmergencyPlan(
            **data.model_dump(),
            created_by=user_id,
            updated_by=user_id,
        )
        plan.search_text = plan_search_text(plan)
        self.db.add(plan)
        await self.db.flush()
        return plan

    async def update_plan(
        self, plan_id: UUID, data: EmergencyPlanUpdate, user_id: UUID | None = None
    ) -> EmergencyPlan:
        plan = await self.get_plan(plan_id)
        if plan is None:
            raise NotFoundException("应急预案不存在")
        changes = data.model_dump(exclude_unset=True)
        if "plan_type" in changes and changes["plan_type"] not in PLAN_TYPES:
            raise AppException(status_code=422, message="无效的预案类型")
        if "status" in changes and changes["status"] not in PLAN_STATUSES:
            raise AppException(status_code=422, message="无效的预案状态")
        for field, value in changes.items():
            setattr(plan, field, value)
        plan.search_text = plan_search_text(plan)
        plan.updated_by = user_id
        await self.db.flush()
        return plan

    async def delete_plan(self, plan_id: UUID) -> bool:
        plan = await self.get_plan(plan_id)
        if plan is None:
            return False
        plan.is_deleted = True
        await self.db.flush()
        return True

    async def set_plan_file(
        self, plan_id: UUID, file_path: str, file_name: str, user_id: UUID | None = None
    ) -> EmergencyPlan:
        plan = await self.get_plan(plan_id)
        if plan is None:
            raise NotFoundException("应急预案不存在")
        plan.file_path = file_path
        plan.file_name = file_name
        plan.updated_by = user_id
        await self.db.flush()
        return plan

    # ---------- 应急演练 ----------

    async def list_drills(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        drill_type: str | None = None,
        status: str | None = None,
        year: int | None = None,
        keyword: str | None = None,
    ) -> tuple[list[EmergencyDrill], int]:
        conditions: list[ColumnElement[bool]] = [EmergencyDrill.is_deleted.is_(False)]
        if drill_type:
            conditions.append(EmergencyDrill.drill_type == drill_type)
        if status:
            conditions.append(EmergencyDrill.status == status)
        if year is not None:
            conditions.append(
                func.coalesce(
                    EmergencyDrill.actual_date, EmergencyDrill.planned_date
                ).between(date(year, 1, 1), date(year, 12, 31))
            )
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    EmergencyDrill.name.ilike(pattern),
                    EmergencyDrill.search_text.ilike(pattern),
                )
            )
        total = (
            await self.db.execute(
                select(func.count()).select_from(EmergencyDrill).where(*conditions)
            )
        ).scalar() or 0
        rows = await self.db.execute(
            select(EmergencyDrill)
            .where(*conditions)
            .order_by(
                func.coalesce(
                    EmergencyDrill.actual_date, EmergencyDrill.planned_date
                ).desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def get_drill(self, drill_id: UUID) -> EmergencyDrill | None:
        result = await self.db.execute(
            select(EmergencyDrill).where(
                EmergencyDrill.id == drill_id, EmergencyDrill.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_drill(
        self, data: EmergencyDrillCreate, user_id: UUID | None = None
    ) -> EmergencyDrill:
        if data.drill_type not in DRILL_TYPES:
            raise AppException(status_code=422, message="无效的演练类型")
        if data.status not in DRILL_STATUSES:
            raise AppException(status_code=422, message="无效的演练状态")
        drill = EmergencyDrill(
            **data.model_dump(),
            created_by=user_id,
            updated_by=user_id,
        )
        drill.search_text = drill_search_text(drill)
        self.db.add(drill)
        await self.db.flush()
        return drill

    async def update_drill(
        self, drill_id: UUID, data: EmergencyDrillUpdate, user_id: UUID | None = None
    ) -> EmergencyDrill:
        drill = await self.get_drill(drill_id)
        if drill is None:
            raise NotFoundException("应急演练不存在")
        changes = data.model_dump(exclude_unset=True)
        if "drill_type" in changes and changes["drill_type"] not in DRILL_TYPES:
            raise AppException(status_code=422, message="无效的演练类型")
        if "status" in changes and changes["status"] not in DRILL_STATUSES:
            raise AppException(status_code=422, message="无效的演练状态")
        for field, value in changes.items():
            setattr(drill, field, value)
        drill.search_text = drill_search_text(drill)
        drill.updated_by = user_id
        await self.db.flush()
        return drill

    async def delete_drill(self, drill_id: UUID) -> bool:
        drill = await self.get_drill(drill_id)
        if drill is None:
            return False
        drill.is_deleted = True
        await self.db.flush()
        return True

    # ---------- 应急物资 ----------

    async def list_supplies(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        status: str | None = None,
        department: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[EmergencySupply], int]:
        conditions: list[ColumnElement[bool]] = [EmergencySupply.is_deleted.is_(False)]
        if category:
            conditions.append(EmergencySupply.category == category)
        if status:
            conditions.append(EmergencySupply.status == status)
        if department:
            conditions.append(EmergencySupply.department == department)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    EmergencySupply.name.ilike(pattern),
                    EmergencySupply.search_text.ilike(pattern),
                )
            )
        total = (
            await self.db.execute(
                select(func.count()).select_from(EmergencySupply).where(*conditions)
            )
        ).scalar() or 0
        rows = await self.db.execute(
            select(EmergencySupply)
            .where(*conditions)
            .order_by(
                EmergencySupply.category.asc(),
                EmergencySupply.department.asc(),
                EmergencySupply.name.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.scalars().all()), total

    async def get_supply(self, supply_id: UUID) -> EmergencySupply | None:
        result = await self.db.execute(
            select(EmergencySupply).where(
                EmergencySupply.id == supply_id, EmergencySupply.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def create_supply(
        self, data: EmergencySupplyCreate, user_id: UUID | None = None
    ) -> EmergencySupply:
        if data.category not in SUPPLY_CATEGORIES:
            raise AppException(status_code=422, message="无效的物资类别")
        if data.status not in SUPPLY_STATUSES:
            raise AppException(status_code=422, message="无效的物资状态")
        supply = EmergencySupply(
            **data.model_dump(),
            created_by=user_id,
            updated_by=user_id,
        )
        supply.search_text = supply_search_text(supply)
        self.db.add(supply)
        await self.db.flush()
        return supply

    async def update_supply(
        self, supply_id: UUID, data: EmergencySupplyUpdate, user_id: UUID | None = None
    ) -> EmergencySupply:
        supply = await self.get_supply(supply_id)
        if supply is None:
            raise NotFoundException("应急物资不存在")
        changes = data.model_dump(exclude_unset=True)
        if "category" in changes and changes["category"] not in SUPPLY_CATEGORIES:
            raise AppException(status_code=422, message="无效的物资类别")
        if "status" in changes and changes["status"] not in SUPPLY_STATUSES:
            raise AppException(status_code=422, message="无效的物资状态")
        for field, value in changes.items():
            setattr(supply, field, value)
        supply.search_text = supply_search_text(supply)
        supply.updated_by = user_id
        await self.db.flush()
        return supply

    async def delete_supply(self, supply_id: UUID) -> bool:
        supply = await self.get_supply(supply_id)
        if supply is None:
            return False
        supply.is_deleted = True
        await self.db.flush()
        return True

    # ---------- 统计 ----------

    async def get_stats(self) -> EmergencyMgmtStatsResponse:
        today = date.today()
        horizon = today + timedelta(days=30)

        plan_rows = (
            await self.db.execute(
                select(
                    EmergencyPlan.status,
                    EmergencyPlan.review_due_date,
                ).where(EmergencyPlan.is_deleted.is_(False))
            )
        ).all()
        drills = (
            await self.db.execute(
                select(
                    EmergencyDrill.status,
                    EmergencyDrill.planned_date,
                ).where(EmergencyDrill.is_deleted.is_(False))
            )
        ).all()
        supply_rows = (
            await self.db.execute(
                select(
                    EmergencySupply.category,
                    EmergencySupply.status,
                ).where(EmergencySupply.is_deleted.is_(False))
            )
        ).all()

        by_category: dict[str, int] = {}
        supplies_abnormal = 0
        for category, status in supply_rows:
            by_category[category] = by_category.get(category, 0) + 1
            if status != "good":
                supplies_abnormal += 1

        return EmergencyMgmtStatsResponse(
            plans_total=len(plan_rows),
            plans_active=sum(1 for status, _ in plan_rows if status == "active"),
            plans_review_due_30d=sum(
                1
                for _, review_due in plan_rows
                if review_due is not None and today <= review_due <= horizon
            ),
            drills_total=len(drills),
            drills_planned=sum(1 for status, _ in drills if status == "planned"),
            drills_done=sum(1 for status, _ in drills if status == "done"),
            drills_due_30d=sum(
                1
                for status, planned in drills
                if status == "planned"
                and planned is not None
                and today <= planned <= horizon
            ),
            supplies_total=len(supply_rows),
            supplies_abnormal=supplies_abnormal,
            supplies_by_category=by_category,
        )
