"""新员工培训 Repository."""

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import (
    Employee,
    NewEmployeeTrainingPlan,
    PositionTrainingList,
    TrainingLedger,
)
from app.modules.hr.training_dept_resolver import training_dept_aliases_of


class NewEmployeeTrainingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── 培训计划 ───

    async def list_plans(
        self,
        page: int = 1,
        page_size: int = 20,
        department: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[NewEmployeeTrainingPlan], int]:
        query = select(NewEmployeeTrainingPlan).where(
            NewEmployeeTrainingPlan.is_deleted.is_(False)
        )
        count_query = (
            select(func.count())
            .select_from(NewEmployeeTrainingPlan)
            .where(NewEmployeeTrainingPlan.is_deleted.is_(False))
        )

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（含档案名与培训规范名）
            query = query.where(
                (NewEmployeeTrainingPlan.department.in_(dept_alias_set))
                | (NewEmployeeTrainingPlan.sub_department.in_(dept_alias_set))
            )
            count_query = count_query.where(
                (NewEmployeeTrainingPlan.department.in_(dept_alias_set))
                | (NewEmployeeTrainingPlan.sub_department.in_(dept_alias_set))
            )
        elif department:
            # 部门归一匹配：选中部门（培训规范名）展开为全部别名（如 201二车间（MC）→
            # 裸名/霉酚酸/201三车间），
            # department 或 sub_department
            # 任一命中即算该部门（员工档案部门与培训部门名不同）
            dept_values = await training_dept_aliases_of(self.session, department)
            query = query.where(
                (NewEmployeeTrainingPlan.department.in_(dept_values))
                | (NewEmployeeTrainingPlan.sub_department.in_(dept_values))
            )
            count_query = count_query.where(
                (NewEmployeeTrainingPlan.department.in_(dept_values))
                | (NewEmployeeTrainingPlan.sub_department.in_(dept_values))
            )
        if status:
            query = query.where(NewEmployeeTrainingPlan.status == status)
            count_query = count_query.where(NewEmployeeTrainingPlan.status == status)
        if keyword:
            like = f"%{keyword}%"
            query = query.where(NewEmployeeTrainingPlan.employee_name.ilike(like))
            count_query = count_query.where(
                NewEmployeeTrainingPlan.employee_name.ilike(like)
            )

        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(NewEmployeeTrainingPlan.hire_date.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_by_id(self, plan_id: UUID) -> NewEmployeeTrainingPlan | None:
        query = select(NewEmployeeTrainingPlan).where(
            NewEmployeeTrainingPlan.id == plan_id,
            NewEmployeeTrainingPlan.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_employee_id(
        self, employee_id: UUID
    ) -> NewEmployeeTrainingPlan | None:
        query = select(NewEmployeeTrainingPlan).where(
            NewEmployeeTrainingPlan.employee_id == employee_id,
            NewEmployeeTrainingPlan.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name_and_department(
        self, name: str, department: str
    ) -> NewEmployeeTrainingPlan | None:
        """按姓名 + 部门查重（手动新增离岗复训员工时防重复创建）。"""
        query = select(NewEmployeeTrainingPlan).where(
            NewEmployeeTrainingPlan.employee_name == name,
            NewEmployeeTrainingPlan.department == department,
            NewEmployeeTrainingPlan.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, plan: NewEmployeeTrainingPlan) -> NewEmployeeTrainingPlan:
        self.session.add(plan)
        await self.session.flush()
        return plan

    async def update(
        self, plan: NewEmployeeTrainingPlan, data: dict[str, Any]
    ) -> NewEmployeeTrainingPlan:
        for key, value in data.items():
            if value is not None:
                setattr(plan, key, value)
        await self.session.flush()
        await self.session.refresh(plan)
        return plan

    async def delete(self, plan: NewEmployeeTrainingPlan) -> None:
        plan.is_deleted = True
        await self.session.flush()

    async def list_available_trainees(
        self,
        department: str | None = None,
        exclude_plan_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict[str, str]]:
        """获取可一起培训的新员工（未完成计划的员工，排除当前计划）。

        部门过滤：入参为培训部门规范名（前端已按 resolveTrainingDept 解析），
        用 training_dept_aliases_of 展开全部别名后匹配 department/sub_department，
        与列表页 list_plans 过滤规则保持一致——手动新增（department=培训部门名）
        与自动拉取（department=档案一级+sub_department=档案二级）两种存储格式
        均可被正确匹配，且不会跨部门混入其他车间人员。
        """
        query = select(NewEmployeeTrainingPlan).where(
            NewEmployeeTrainingPlan.is_deleted.is_(False),
            NewEmployeeTrainingPlan.status != "已完成",
        )
        if department:
            dept_values = await training_dept_aliases_of(self.session, department)
            # 部门匹配：department 或 sub_department 任一等于别名集合即命中
            query = query.where(
                (NewEmployeeTrainingPlan.department.in_(dept_values))
                | (NewEmployeeTrainingPlan.sub_department.in_(dept_values))
            )
        if exclude_plan_id:
            query = query.where(NewEmployeeTrainingPlan.id != exclude_plan_id)

        query = query.order_by(NewEmployeeTrainingPlan.employee_name)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        plans = list(result.scalars().all())
        return [
            {
                "name": p.employee_name,
                "department": p.department,
                "sub_department": p.sub_department or "",
            }
            for p in plans
        ]

    # ─── 员工 / 岗位培训清单 / 台账 ───

    async def list_recent_employees(
        self, hire_date_from: date, page: int, page_size: int
    ) -> tuple[list[Employee], int]:
        """入职日期在指定日期之后（含）的在职员工。"""
        query = select(Employee).where(
            Employee.is_deleted.is_(False),
            Employee.hire_date >= hire_date_from,
        )
        count_query = (
            select(func.count())
            .select_from(Employee)
            .where(Employee.is_deleted.is_(False), Employee.hire_date >= hire_date_from)
        )
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Employee.hire_date.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_employee_by_id(self, employee_id: UUID) -> Employee | None:
        query = select(Employee).where(
            Employee.id == employee_id,
            Employee.is_deleted.is_(False),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _dept_alias_set(self, departments: list[str]) -> set[str]:
        """员工档案部门 → 培训规范名 → 全部别名展开（双端归一）。

        员工表 department/sub_department 均为飞书叫法（如 201二车间、动力科），
        岗位培训清单按培训规范名（201二车间（MC）、动力部）或裸名存储，
        先把入参解析为规范名，再展开规范名的全部别名作为 IN 集合，两侧即可命中。
        """
        from app.modules.hr.training_dept_resolver import (
            resolve_training_department,
            training_dept_aliases_of,
        )

        alias_set: set[str] = set()
        for name in (d for d in departments if d):
            norm = await resolve_training_department(self.session, name)
            if norm:
                alias_set.update(await training_dept_aliases_of(self.session, norm))
        return alias_set

    async def list_position_training_lists_by_dept(
        self, departments: list[str]
    ) -> list[PositionTrainingList]:
        """按部门名集合查询岗位培训清单（含明细），入参部门与清单部门双端归一匹配。"""
        from sqlalchemy.orm import selectinload

        alias_set = await self._dept_alias_set(departments)
        if not alias_set:
            return []
        query = (
            select(PositionTrainingList)
            .where(
                PositionTrainingList.is_deleted.is_(False),
                PositionTrainingList.department.in_(sorted(alias_set)),
            )
            .options(selectinload(PositionTrainingList.items))
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def list_position_training_lists_by_dept_and_position(
        self, departments: list[str], position: str
    ) -> list[PositionTrainingList]:
        """按部门集合+岗位匹配岗位培训清单（含明细），入参部门与清单部门双端归一匹配。"""
        from sqlalchemy.orm import selectinload

        alias_set = await self._dept_alias_set(departments)
        if not alias_set:
            return []
        query = (
            select(PositionTrainingList)
            .where(
                PositionTrainingList.is_deleted.is_(False),
                PositionTrainingList.department.in_(sorted(alias_set)),
                PositionTrainingList.position == position,
            )
            .options(selectinload(PositionTrainingList.items))
        )
        result = await self.session.execute(query)
        return list(result.scalars().unique().all())

    async def list_ledgers_by_employee_name(
        self, employee_name: str
    ) -> list[TrainingLedger]:
        """查询培训对象名单中包含该员工姓名的台账记录（按培训日期升序）。"""
        query = (
            select(TrainingLedger)
            .where(
                TrainingLedger.is_deleted.is_(False),
                TrainingLedger.trainees.is_not(None),
                TrainingLedger.trainees.ilike(f"%{employee_name}%"),
            )
            .order_by(TrainingLedger.training_date.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
