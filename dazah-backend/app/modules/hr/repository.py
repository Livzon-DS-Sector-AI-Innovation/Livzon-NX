"""HR database queries live here."""

from datetime import date
from datetime import datetime as dt
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import (
    and_,
    asc,
    desc,
    func,
    literal_column,
    or_,
    select,
    union_all,
    update,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.modules.hr.legacy_models import DepartureRecord, OnboardingRecord
from app.modules.hr.models import (
    AnnualTrainingPlan,
    AnnualTrainingPlanItem,
    ContractManagement,
    Employee,
    EmployeeTrainingListMember,
    HrDepartment,
    OffboardingRecord,
    PlanAttachment,
    PlanAttachmentSection,
    PositionTransferRecord,
    Team,
    TrainingImportMapping,
    TrainingLedger,
    TrainingLedgerPage,
    TrainingPersonnelConfig,
    TrainingSession,
)

if TYPE_CHECKING:
    from app.modules.hr.models import HrCustomTrainingDepartment, TrainingDeptMapping


class EmployeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, employee_id: UUID) -> Employee | None:
        result = await self.session.execute(
            select(Employee).where(
                Employee.id == employee_id, Employee.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_include_deleted(self, employee_id: UUID) -> Employee | None:
        """按 ID 查员工，不区分是否软删（离职台账转抄员工档案时需要）。"""
        result = await self.session.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        return result.scalar_one_or_none()

    async def get_by_employee_number(self, employee_number: str) -> Employee | None:
        result = await self.session.execute(
            select(Employee).where(
                Employee.employee_number == employee_number,
                Employee.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_employee_number_include_deleted(
        self, employee_number: str
    ) -> Employee | None:
        """按工号查员工，不区分是否软删（离职台账转抄员工档案时需要）。"""
        result = await self.session.execute(
            select(Employee).where(Employee.employee_number == employee_number)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Employee | None:
        result = await self.session.execute(
            select(Employee).where(
                Employee.name == name,
                Employee.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_employee_number_map(self) -> dict[str, Employee]:
        """Return {employee_number: Employee} for all non-deleted employees.

        Used by Feishu sync to avoid N+1 SELECT queries.
        """
        result = await self.session.execute(
            select(Employee).where(Employee.is_deleted.is_(False))
        )
        return {
            emp.employee_number: emp
            for emp in result.scalars().all()
            if emp.employee_number
        }

    async def get_max_seq_number(self) -> int:
        """Get the maximum seq_number across all employees."""
        result = await self.session.execute(
            select(func.max(Employee.seq_number)).where(Employee.is_deleted.is_(False))
        )
        max_val = result.scalar()
        return max_val if max_val is not None else 0

    async def list_by_department_for_auto(
        self, department: str
    ) -> list[tuple[str, str | None]]:
        """在职员工（含软删除前档案）中，部门解析后 == 目标培训部门的 (姓名, 工号) 列表.

        供员工培训清单"新员工自动合并"：解析规则与培训模块其他页面一致。
        """
        from sqlalchemy import or_

        from app.modules.hr.training_dept_resolver import resolve_training_department

        result = await self.session.execute(
            select(
                Employee.name,
                Employee.employee_number,
                Employee.department,
                Employee.sub_department,
            ).where(
                Employee.is_deleted.is_(False),
                or_(Employee.status.is_(None), Employee.status == "在职"),
            )
        )
        matched: list[tuple[str, str | None]] = []
        for name, emp_no, dept, sub in result.all():
            resolved = await resolve_training_department(self.session, dept, sub)
            if resolved == department:
                matched.append((name, emp_no))
        return matched

    async def list_employees(
        self,
        *,
        department: str | None = None,
        sub_department: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
        team: str | None = None,
        position: str | None = None,
        job_category: str | None = None,
        level: str | None = None,
        gender: str | None = None,
        education: str | None = None,
        political_status: str | None = None,
        marital_status: str | None = None,
        status_category: str | None = None,
        age_min: int | None = None,
        age_max: int | None = None,
        birth_year_min: int | None = None,
        birth_year_max: int | None = None,
        hire_date_after: date | None = None,
        hire_date_before: date | None = None,
        factory_entry_date_after: date | None = None,
        factory_entry_date_before: date | None = None,
        work_start_date_after: date | None = None,
        work_start_date_before: date | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[Employee], int]:
        stmt = select(Employee).where(Employee.is_deleted.is_(False))

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（含档案名与培训规范名），
            # department/sub_department 任一命中即可见
            stmt = stmt.where(
                (Employee.department.in_(dept_alias_set))
                | (Employee.sub_department.in_(dept_alias_set))
            )
        elif department:
            # 培训部门名与员工档案部门是两套叫法：先归一为培训规范名再展开全部别名，
            # department 或 sub_department 任一命中即选中（与培训列表页规则一致）；
            # 档案部门名（如 201车间）非规范名，展开后为自身，行为不变
            from app.modules.hr.training_dept_resolver import (
                resolve_training_department,
                training_dept_aliases_of,
            )

            norm = await resolve_training_department(self.session, department)
            dept_values = await training_dept_aliases_of(
                self.session, norm or department
            )
            stmt = stmt.where(
                (Employee.department.in_(dept_values))
                | (Employee.sub_department.in_(dept_values))
            )
        if sub_department:
            stmt = stmt.where(Employee.sub_department.ilike(f"{sub_department}%"))
        if status:
            stmt = stmt.where(Employee.status == status)
        else:
            # 默认排除待审批员工，只有显式筛选时才显示
            stmt = stmt.where(Employee.status != "待审批")
        if keyword:
            stmt = stmt.where(
                Employee.name.ilike(f"{keyword}%")
                | Employee.employee_number.ilike(f"{keyword}%")
            )
        if team:
            stmt = stmt.where(Employee.team == team)
        if position:
            stmt = stmt.where(Employee.position.ilike(f"{position}%"))
        if job_category:
            stmt = stmt.where(Employee.job_category == job_category)
        if level:
            stmt = stmt.where(Employee.level == level)
        if gender:
            stmt = stmt.where(Employee.gender == gender)
        if education:
            stmt = stmt.where(Employee.education == education)
        if political_status:
            stmt = stmt.where(Employee.political_status == political_status)
        if marital_status:
            stmt = stmt.where(Employee.marital_status == marital_status)
        if status_category:
            stmt = stmt.where(Employee.status_category == status_category)
        if age_min is not None:
            stmt = stmt.where(Employee.age >= age_min)
        if age_max is not None:
            stmt = stmt.where(Employee.age <= age_max)
        if birth_year_min is not None:
            stmt = stmt.where(Employee.birth_year >= birth_year_min)
        if birth_year_max is not None:
            stmt = stmt.where(Employee.birth_year <= birth_year_max)
        if hire_date_after:
            stmt = stmt.where(Employee.hire_date >= hire_date_after)
        if hire_date_before:
            stmt = stmt.where(Employee.hire_date <= hire_date_before)
        if factory_entry_date_after:
            stmt = stmt.where(Employee.factory_entry_date >= factory_entry_date_after)
        if factory_entry_date_before:
            stmt = stmt.where(Employee.factory_entry_date <= factory_entry_date_before)
        if work_start_date_after:
            stmt = stmt.where(Employee.work_start_date >= work_start_date_after)
        if work_start_date_before:
            stmt = stmt.where(Employee.work_start_date <= work_start_date_before)

        # 并行执行 COUNT 和数据查询，减少 TTFB
        count_stmt = select(func.count()).select_from(stmt.subquery())
        sort_column = getattr(Employee, sort_by, Employee.created_at)
        order_func = desc if sort_order == "desc" else asc
        data_stmt = (
            stmt.order_by(order_func(sort_column))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        # NOTE: asyncio.gather 在共享 AsyncSession 下可能无法真正并行，
        # 且小数据量时顺序执行更稳定。保留顺序执行。
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        data_result = await self.session.execute(data_stmt)
        return list(data_result.scalars().all()), total

    async def list_recent_entries(
        self,
        *,
        start_date: date,
        end_date: date,
        dept_alias_set: set[str] | None = None,
    ) -> list[Employee]:
        """查询 factory_entry_date 在 [start_date, end_date] 范围内的员工"""
        stmt = (
            select(Employee)
            .where(
                Employee.is_deleted.is_(False),
                Employee.factory_entry_date.is_not(None),
                Employee.factory_entry_date >= start_date,
                Employee.factory_entry_date <= end_date,
            )
            .order_by(asc(Employee.factory_entry_date))
        )
        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合
            stmt = stmt.where(
                (Employee.department.in_(dept_alias_set))
                | (Employee.sub_department.in_(dept_alias_set))
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, employee: Employee) -> Employee:
        self.session.add(employee)
        await self.session.flush()
        await self.session.refresh(employee)
        return employee

    async def update(self, employee: Employee) -> Employee:
        await self.session.flush()
        await self.session.refresh(employee)
        return employee

    async def upsert_by_employee_number(self, data: dict[str, Any]) -> Employee | None:
        """Create or update employee by employee_number (used for Feishu sync).

        以飞书为主：data 中显式携带的字段（含 None/空值）都会覆盖本地，
        保证"飞书没有的字段，本地也清空"。
        已离职（软删或状态=离职）的员工不被同步复活：即使飞书员工档案表里还有
        该记录，也跳过（保持离职状态），避免离职后又被拉回员工管理。
        """
        emp = await self.get_by_employee_number_include_deleted(
            data["employee_number"]
        )
        if emp:
            if getattr(emp, "is_deleted", False) or (
                getattr(emp, "status", None) == "离职"
            ):
                # 本地已离职/已软删 → 跳过，不复活、不更新
                return None
            for key, value in data.items():
                if key != "id":
                    setattr(emp, key, value)
            await self.session.flush()
            await self.session.refresh(emp)
            return emp
        else:
            new_emp = Employee(
                **{k: v for k, v in data.items() if v is not None and v != ""}
            )
            self.session.add(new_emp)
            await self.session.flush()
            await self.session.refresh(new_emp)
            return new_emp

    async def delete_not_in_feishu(self, feishu_record_ids: set[str]) -> int:
        """软删除本地有但飞书中已不存在的员工记录（按 feishu_record_id 判断）。

        以飞书为主：飞书没有的本地记录标记为软删除。
        软删除前先清理引用该员工的外键记录（offboarding_records /
        position_transfer_records）。
        """
        if not feishu_record_ids:
            return 0
        # 找出待删除的员工 id
        target_subq = select(Employee.id).where(
            Employee.feishu_record_id.isnot(None),
            ~Employee.feishu_record_id.in_(feishu_record_ids),
        )
        # 先清理外键引用（离职记录 / 岗位调动记录）
        await self.session.execute(
            update(OffboardingRecord)
            .where(OffboardingRecord.employee_id.in_(target_subq))
            .values(employee_id=None)
        )
        await self.session.execute(
            update(PositionTransferRecord)
            .where(PositionTransferRecord.employee_id.in_(target_subq))
            .values(employee_id=None)
        )
        # 软删除员工
        result = cast(
            CursorResult[Any],
            await self.session.execute(
                update(Employee)
                .where(
                    Employee.feishu_record_id.isnot(None),
                    ~Employee.feishu_record_id.in_(feishu_record_ids),
                )
                .values(is_deleted=True)
            ),
        )
        return result.rowcount

    async def get_feishu_record_map(self) -> dict[str, str]:
        """Return {employee_number: feishu_record_id} for all non-deleted employees."""
        result = await self.session.execute(
            select(Employee.employee_number, Employee.feishu_record_id).where(
                Employee.is_deleted.is_(False),
                Employee.feishu_record_id.isnot(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def count_total(self) -> int:
        result = await self.session.execute(
            select(func.count()).where(Employee.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def get_stats(self, dept_alias_set: set[str] | None = None) -> dict[str, Any]:
        """Return employee statistics for dashboard."""
        # 部门级数据隔离：非管理员只统计可见部门
        dept_scope = None
        if dept_alias_set is not None:
            dept_scope = (Employee.department.in_(dept_alias_set)) | (
                Employee.sub_department.in_(dept_alias_set)
            )
        base = select(Employee).where(Employee.is_deleted.is_(False))
        if dept_scope is not None:
            base = base.where(dept_scope)

        # Total count
        total_result = await self.session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = total_result.scalar() or 0

        # Status distribution
        status_stmt = select(Employee.status, func.count()).where(
            Employee.is_deleted.is_(False)
        )
        if dept_scope is not None:
            status_stmt = status_stmt.where(dept_scope)
        status_result = await self.session.execute(
            status_stmt.group_by(Employee.status)
        )
        status_distribution = {row[0]: row[1] for row in status_result.all()}

        # Department distribution - 直接按员工一级部门（department 字段）分组统计。
        # 不依赖部门表名字匹配（部门表用"XX一车间"、员工用"XX车间"，名字不一致）。
        dept_stmt = select(Employee.department, func.count()).where(
            Employee.is_deleted.is_(False),
            Employee.department.isnot(None),
            Employee.department != "",
        )
        if dept_scope is not None:
            dept_stmt = dept_stmt.where(dept_scope)
        dept_result = await self.session.execute(
            dept_stmt.group_by(Employee.department).order_by(func.count().desc())
        )
        department_distribution = [
            {"department": row[0], "count": row[1]} for row in dept_result.all()
        ]

        # Education distribution
        edu_stmt = select(Employee.education, func.count()).where(
            Employee.is_deleted.is_(False),
            Employee.education.isnot(None),
            Employee.education != "",
        )
        if dept_scope is not None:
            edu_stmt = edu_stmt.where(dept_scope)
        edu_result = await self.session.execute(edu_stmt.group_by(Employee.education))
        education_distribution = {row[0]: row[1] for row in edu_result.all()}

        # Contract expiring（当前季度，与员工档案「合同到期提醒」口径完全一致：
        # 全公司在职员工，取 6 个合同字段中最晚的非空日期，判断是否在本季度内到期；
        # 不按部门可见范围过滤，避免与员工档案季度提醒结果不一致）
        from datetime import date as _date
        from datetime import datetime as _dt
        from datetime import timedelta as _timedelta

        today = _date.today()
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        q_start = _date(today.year, q_start_month, 1)
        if q_start_month == 10:
            q_end = _date(today.year, 12, 31)
        else:
            # 下季度首月 1 日减一天 = 本季度最后一天（如 7 月季度 → 9-30）
            q_end = _date(today.year, q_start_month + 3, 1) + _timedelta(days=-1)

        emp_query = select(Employee).where(
            Employee.is_deleted.is_(False),
            Employee.status == "在职",
        )
        all_emps = (await self.session.execute(emp_query)).scalars().all()

        def _max_contract_date(emp: Employee) -> date | None:
            dates: list[date] = []
            for attr in (
                "contract_end_date",
                "contract_end_2",
                "contract_end_3",
                "contract_end_4",
            ):
                val = getattr(emp, attr, None)
                if isinstance(val, date):
                    dates.append(val)
            for attr in ("contract_end_5", "contract_end_6"):
                val = getattr(emp, attr, None)
                if isinstance(val, str) and val.strip():
                    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
                        try:
                            dates.append(_dt.strptime(val.strip(), fmt).date())
                            break
                        except ValueError:
                            continue
            return max(dates) if dates else None

        expiring: list[dict[str, Any]] = []
        for emp in all_emps:
            max_date = _max_contract_date(emp)
            if max_date and q_start <= max_date <= q_end:
                expiring.append(
                    {
                        "employee_number": emp.employee_number,
                        "name": emp.name,
                        "department": emp.department,
                        "position": emp.position,
                        "contract_end_date": str(max_date),
                    }
                )
        expiring.sort(key=lambda item: item["contract_end_date"])
        contract_expiring_count = len(expiring)
        contract_expiring_list = expiring

        return {
            "total": total,
            "status_distribution": status_distribution,
            "department_distribution": department_distribution,
            "education_distribution": education_distribution,
            "contract_expiring_count": contract_expiring_count,
            "contract_expiring_list": contract_expiring_list,
        }

    def _apply_filters(self, stmt: Any, **filters: Any) -> Any:
        """Apply common filters to a select statement."""
        if filters.get("department"):
            stmt = stmt.where(Employee.department.ilike(f"{filters['department']}%"))
        if filters.get("status"):
            stmt = stmt.where(Employee.status == filters["status"])
        else:
            stmt = stmt.where(Employee.status != "待审批")
        if filters.get("keyword"):
            stmt = stmt.where(
                Employee.name.ilike(f"{filters['keyword']}%")
                | Employee.employee_number.ilike(f"{filters['keyword']}%")
            )
        if filters.get("team"):
            stmt = stmt.where(Employee.team == filters["team"])
        if filters.get("position"):
            stmt = stmt.where(Employee.position.ilike(f"{filters['position']}%"))
        if filters.get("job_category"):
            stmt = stmt.where(Employee.job_category == filters["job_category"])
        if filters.get("level"):
            stmt = stmt.where(Employee.level == filters["level"])
        if filters.get("gender"):
            stmt = stmt.where(Employee.gender == filters["gender"])
        if filters.get("education"):
            stmt = stmt.where(Employee.education == filters["education"])
        if filters.get("political_status"):
            stmt = stmt.where(Employee.political_status == filters["political_status"])
        if filters.get("marital_status"):
            stmt = stmt.where(Employee.marital_status == filters["marital_status"])
        if filters.get("status_category"):
            stmt = stmt.where(Employee.status_category == filters["status_category"])
        if filters.get("age_min") is not None:
            stmt = stmt.where(Employee.age >= filters["age_min"])
        if filters.get("age_max") is not None:
            stmt = stmt.where(Employee.age <= filters["age_max"])
        if filters.get("birth_year_min") is not None:
            stmt = stmt.where(Employee.birth_year >= filters["birth_year_min"])
        if filters.get("birth_year_max") is not None:
            stmt = stmt.where(Employee.birth_year <= filters["birth_year_max"])
        if filters.get("hire_date_after"):
            stmt = stmt.where(Employee.hire_date >= filters["hire_date_after"])
        if filters.get("hire_date_before"):
            stmt = stmt.where(Employee.hire_date <= filters["hire_date_before"])
        if filters.get("factory_entry_date_after"):
            stmt = stmt.where(
                Employee.factory_entry_date >= filters["factory_entry_date_after"]
            )
        if filters.get("factory_entry_date_before"):
            stmt = stmt.where(
                Employee.factory_entry_date <= filters["factory_entry_date_before"]
            )
        if filters.get("work_start_date_after"):
            stmt = stmt.where(
                Employee.work_start_date >= filters["work_start_date_after"]
            )
        if filters.get("work_start_date_before"):
            stmt = stmt.where(
                Employee.work_start_date <= filters["work_start_date_before"]
            )
        return stmt

    async def group_count(
        self, field_name: str, **filters: Any
    ) -> list[dict[str, Any]]:
        """Group employees by a field and count occurrences.

        Returns:
            List of {"value": field_value, "count": int} sorted by count descending.
        """
        field = getattr(Employee, field_name, None)
        if field is None:
            return []

        stmt = select(field, func.count().label("count")).where(
            Employee.is_deleted.is_(False)
        )
        stmt = self._apply_filters(stmt, **filters)
        stmt = stmt.group_by(field).order_by(desc("count"))
        result = cast(CursorResult[Any], await self.session.execute(stmt))
        rows = result.all()
        return [
            {"value": row[0], "count": row[1]} for row in rows if row[0] is not None
        ]

    async def get_distinct_values(self, field_name: str, **filters: Any) -> list[str]:
        """Get distinct non-null values for a field.

        Returns:
            List of distinct values.
        """
        field = getattr(Employee, field_name, None)
        if field is None:
            return []

        stmt = select(field).where(Employee.is_deleted.is_(False)).distinct()
        stmt = self._apply_filters(stmt, **filters)
        result = await self.session.execute(stmt)
        rows = result.all()
        return [row[0] for row in rows if row[0] is not None]

    async def count_synced(self) -> int:
        result = await self.session.execute(
            select(func.count()).where(
                Employee.is_deleted.is_(False),
                Employee.feishu_record_id.isnot(None),
            )
        )
        return result.scalar() or 0

    async def soft_delete(self, employee: Employee) -> None:
        employee.is_deleted = True
        await self.session.flush()

    async def list_contract_expiring(
        self,
        start_date: date,
        end_date: date,
        department: str | None = None,
        page: int = 1,
        page_size: int = 20,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """筛选合同到期人员。取6个合同字段中最晚的非空日期。"""
        from datetime import date

        # Ensure date objects (defensive)
        if isinstance(start_date, str):
            start_date = dt.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str):
            end_date = dt.strptime(end_date, "%Y-%m-%d").date()

        stmt = select(Employee).where(
            Employee.is_deleted.is_(False),
            Employee.status == "在职",
        )
        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合
            stmt = stmt.where(
                (Employee.department.in_(dept_alias_set))
                | (Employee.sub_department.in_(dept_alias_set))
            )
        elif department:
            stmt = stmt.where(Employee.department.ilike(f"{department}%"))

        result = await self.session.execute(stmt)
        all_employees = result.scalars().all()

        def _get_max_contract_date(emp: Employee) -> date | None:
            dates: list[date] = []
            for attr_name in (
                "contract_end_date",
                "contract_end_2",
                "contract_end_3",
                "contract_end_4",
            ):
                val = getattr(emp, attr_name, None)
                if isinstance(val, date):
                    dates.append(val)
            # contract_end_5 and _6 are strings, try parse
            for attr_name in ("contract_end_5", "contract_end_6"):
                val = getattr(emp, attr_name, None)
                if isinstance(val, str) and val.strip():
                    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
                        try:
                            parsed = dt.strptime(val.strip(), fmt).date()
                            dates.append(parsed)
                            break
                        except ValueError:
                            continue
            return max(dates) if dates else None

        def _get_contract_seq_and_sign(
            emp: Employee, max_date: date
        ) -> tuple[int, date | None]:
            "Return (sequence_number, sign_date) for the contract ending at max_date."
            pairs = [
                (1, emp.contract_end_date, emp.contract_start_date),
                (2, emp.contract_end_2, emp.contract_start_2),
                (3, emp.contract_end_3, emp.contract_start_3),
                (4, emp.contract_end_4, emp.contract_start_4),
            ]
            for seq, end_dt, sign_dt in pairs:
                if isinstance(end_dt, date) and end_dt == max_date:
                    return seq, sign_dt if isinstance(sign_dt, date) else None
            # Check string fields
            for seq, attr_name, sign_attrs in [
                (5, "contract_end_5", ["contract_start_5"]),
                (6, "contract_end_6", ["contract_start_6"]),
            ]:
                val = getattr(emp, attr_name, None)
                if isinstance(val, str) and val.strip():
                    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
                        try:
                            d = dt.strptime(val.strip(), fmt).date()
                            if d == max_date:
                                sign_val = getattr(emp, sign_attrs[0], None)
                                sign_d = None
                                if isinstance(sign_val, str) and sign_val.strip():
                                    try:
                                        sign_d = dt.strptime(
                                            sign_val.strip(), "%Y/%m/%d"
                                        ).date()
                                    except ValueError:
                                        pass
                                return seq, sign_d
                            break
                        except ValueError:
                            continue
            return 1, None

        expiring: list[dict[str, Any]] = []
        for emp in all_employees:
            max_date = _get_max_contract_date(emp)
            if max_date is None:
                continue
            if start_date <= max_date <= end_date:
                seq, sign_date = _get_contract_seq_and_sign(emp, max_date)
                expiring.append(
                    {
                        "employee_id": str(emp.id),
                        "employee_number": emp.employee_number,
                        "name": emp.name,
                        "department": emp.department,
                        "sub_department": getattr(emp, "sub_department", None),
                        "position": emp.position,
                        "contract_sign_date": sign_date.isoformat()
                        if sign_date
                        else None,
                        "contract_end_date": max_date.isoformat(),
                        "contract_sequence": seq,
                    }
                )

        # Sort by contract_end_date ascending
        expiring.sort(key=lambda x: x["contract_end_date"])
        total = len(expiring)
        offset = (page - 1) * page_size
        return expiring[offset : offset + page_size], total


class DepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, department_id: UUID) -> HrDepartment | None:
        result = await self.session.execute(
            select(HrDepartment).where(
                HrDepartment.id == department_id, HrDepartment.is_deleted.is_(False)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> HrDepartment | None:
        # 包含已删除记录，确保唯一性检查覆盖软删除数据
        result = await self.session.execute(
            select(HrDepartment).where(HrDepartment.code == code)
        )
        return result.scalar_one_or_none()

    async def list_departments(
        self,
        *,
        keyword: str | None = None,
        parent_id: UUID | None = None,
        leader_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[HrDepartment], int]:
        stmt = select(HrDepartment).where(HrDepartment.is_deleted.is_(False))

        if keyword:
            stmt = stmt.where(
                HrDepartment.name.ilike(f"%{keyword}%")
                | HrDepartment.code.ilike(f"%{keyword}%")
            )

        if parent_id is not None:
            stmt = stmt.where(HrDepartment.parent_id == parent_id)

        if leader_name:
            stmt = stmt.where(HrDepartment.leader_name.ilike(f"%{leader_name}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(asc(HrDepartment.sort_order), asc(HrDepartment.name))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_all_departments(self) -> list[HrDepartment]:
        """获取所有未删除的部门，用于构建组织机构树。"""
        stmt: Select[Any] = (
            select(HrDepartment)
            .where(HrDepartment.is_deleted.is_(False))
            .order_by(asc(HrDepartment.sort_order), asc(HrDepartment.name))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_feishu_open_department_id(
        self, open_id: str
    ) -> HrDepartment | None:
        result = await self.session.execute(
            select(HrDepartment).where(
                HrDepartment.feishu_open_department_id == open_id,
                HrDepartment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, department: HrDepartment) -> HrDepartment:
        self.session.add(department)
        await self.session.flush()
        await self.session.refresh(department)
        return department

    async def update(self, department: HrDepartment) -> HrDepartment:
        await self.session.flush()
        await self.session.refresh(department)
        return department

    async def soft_delete(self, department: HrDepartment) -> None:
        department.is_deleted = True
        await self.session.flush()


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, team_id: UUID) -> Team | None:
        result = await self.session.execute(
            select(Team)
            .where(Team.id == team_id, Team.is_deleted.is_(False))
            .options(selectinload(Team.department))
        )
        return result.scalar_one_or_none()

    async def list_teams(
        self,
        *,
        department_id: UUID | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Team], int]:
        stmt = (
            select(Team)
            .where(Team.is_deleted.is_(False))
            .options(selectinload(Team.department))
        )

        if department_id:
            stmt = stmt.where(Team.department_id == department_id)
        if keyword:
            stmt = stmt.where(
                Team.name.ilike(f"%{keyword}%") | Team.code.ilike(f"%{keyword}%")
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(asc(Team.created_at))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = cast(CursorResult[Any], await self.session.execute(stmt))
        return list(result.scalars().all()), total

    async def create(self, team: Team) -> Team:
        self.session.add(team)
        await self.session.flush()
        await self.session.refresh(team)
        return team

    async def update(self, team: Team) -> Team:
        await self.session.flush()
        await self.session.refresh(team)
        return team

    async def soft_delete(self, team: Team) -> None:
        team.is_deleted = True
        await self.session.flush()


class OffboardingRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: UUID) -> OffboardingRecord | None:
        result = await self.session.execute(
            select(OffboardingRecord)
            .where(
                OffboardingRecord.id == record_id,
                OffboardingRecord.is_deleted.is_(False),
            )
            .options(selectinload(OffboardingRecord.employee))
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        *,
        employee_id: UUID | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[OffboardingRecord], int]:
        stmt = (
            select(OffboardingRecord)
            .where(OffboardingRecord.is_deleted.is_(False))
            .options(selectinload(OffboardingRecord.employee))
        )

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（档案口径）
            stmt = stmt.where(
                (OffboardingRecord.department.in_(dept_alias_set))
                | (OffboardingRecord.sub_department.in_(dept_alias_set))
            )
        if employee_id:
            stmt = stmt.where(OffboardingRecord.employee_id == employee_id)
        if keyword:
            stmt = stmt.join(Employee).where(
                Employee.name.ilike(f"%{keyword}%")
                | Employee.employee_number.ilike(f"%{keyword}%")
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(desc(OffboardingRecord.created_at))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, record: OffboardingRecord) -> OffboardingRecord:
        self.session.add(record)
        await self.session.flush()
        return record

    async def update(self, record: OffboardingRecord) -> OffboardingRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def soft_delete(self, record: OffboardingRecord) -> None:
        record.is_deleted = True
        await self.session.flush()

    async def get_by_feishu_record_id(
        self, feishu_record_id: str
    ) -> OffboardingRecord | None:
        result = await self.session.execute(
            select(OffboardingRecord).where(
                OffboardingRecord.feishu_record_id == feishu_record_id,
                OffboardingRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[OffboardingRecord]:
        """获取所有记录（含已软删残留，用于飞书主源同步对比后物理清理）"""
        result = await self.session.execute(select(OffboardingRecord))
        return list(result.scalars().all())


class PositionTransferRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: UUID) -> PositionTransferRecord | None:
        result = await self.session.execute(
            select(PositionTransferRecord)
            .where(
                PositionTransferRecord.id == record_id,
                PositionTransferRecord.is_deleted.is_(False),
            )
            .options(selectinload(PositionTransferRecord.employee))
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        *,
        employee_id: UUID | None = None,
        approval_status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[PositionTransferRecord], int]:
        stmt = (
            select(PositionTransferRecord)
            .where(PositionTransferRecord.is_deleted.is_(False))
            .options(selectinload(PositionTransferRecord.employee))
        )

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（原部门/申请部门任一命中）
            stmt = stmt.where(
                (PositionTransferRecord.department_before.in_(dept_alias_set))
                | (PositionTransferRecord.apply_department.in_(dept_alias_set))
            )
        if employee_id:
            stmt = stmt.where(PositionTransferRecord.employee_id == employee_id)
        if approval_status:
            stmt = stmt.where(PositionTransferRecord.approval_status == approval_status)
        if keyword:
            stmt = stmt.where(
                PositionTransferRecord.employee_name.ilike(f"%{keyword}%")
                | PositionTransferRecord.employee_number.ilike(f"%{keyword}%")
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(desc(PositionTransferRecord.effective_date))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, record: PositionTransferRecord) -> PositionTransferRecord:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def update(self, record: PositionTransferRecord) -> PositionTransferRecord:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def soft_delete(self, record: PositionTransferRecord) -> None:
        record.is_deleted = True
        await self.session.flush()

    async def get_by_feishu_record_id(
        self, feishu_record_id: str
    ) -> PositionTransferRecord | None:
        result = await self.session.execute(
            select(PositionTransferRecord).where(
                PositionTransferRecord.feishu_record_id == feishu_record_id,
                PositionTransferRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_all_with_feishu_id(self) -> list[PositionTransferRecord]:
        "查所有有 feishu_record_id 的记录（含已软删"
        "残留，用于飞书主源同步对比后物理清理）。"
        result = await self.session.execute(
            select(PositionTransferRecord).where(
                PositionTransferRecord.feishu_record_id.isnot(None),
                PositionTransferRecord.feishu_record_id != "",
            )
        )
        return list(result.scalars().all())


class _LegacyFeishuRecordRepository:
    model: type[OnboardingRecord] | type[DepartureRecord]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: UUID) -> Any | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == record_id,
                self.model.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_feishu_record_id(self, feishu_record_id: str) -> Any | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.feishu_record_id == feishu_record_id,
                self.model.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, record: Any) -> Any:
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def update(self, record: Any) -> Any:
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def upsert_by_feishu_record_id(self, data: dict[str, Any]) -> Any:
        record_id = data.get("feishu_record_id")
        if not record_id:
            raise ValueError("feishu_record_id is required for upsert")
        record = await self.get_by_feishu_record_id(record_id)
        if record:
            for key, value in data.items():
                if key != "id" and value is not None:
                    setattr(record, key, value)
            return await self.update(record)
        return await self.create(
            self.model(
                **{key: value for key, value in data.items() if value is not None}
            )
        )

    async def count_total(self) -> int:
        result = await self.session.execute(
            select(func.count()).where(self.model.is_deleted.is_(False))
        )
        return result.scalar() or 0

    async def count_synced(self) -> int:
        result = await self.session.execute(
            select(func.count()).where(
                self.model.is_deleted.is_(False),
                self.model.feishu_record_id.isnot(None),
            )
        )
        return result.scalar() or 0

    async def soft_delete(self, record: Any) -> None:
        record.is_deleted = True
        await self.session.flush()


class OnboardingRecordRepository(_LegacyFeishuRecordRepository):
    model = OnboardingRecord

    async def list_records(
        self,
        *,
        department: str | None = None,
        position: str | None = None,
        is_employed: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[OnboardingRecord], int]:
        stmt = select(OnboardingRecord).where(OnboardingRecord.is_deleted.is_(False))
        if dept_alias_set is not None:
            stmt = stmt.where(OnboardingRecord.department.in_(dept_alias_set))
        if department:
            stmt = stmt.where(OnboardingRecord.department == department)
        if position:
            stmt = stmt.where(OnboardingRecord.position.ilike(f"%{position}%"))
        if is_employed:
            stmt = stmt.where(OnboardingRecord.is_employed == is_employed)
        if keyword:
            stmt = stmt.where(
                OnboardingRecord.name.ilike(f"%{keyword}%")
                | OnboardingRecord.employee_number.ilike(f"%{keyword}%")
            )
        return await self._paginate(stmt, sort_by, sort_order, page, page_size)

    async def _paginate(
        self,
        stmt: Any,
        sort_by: str,
        sort_order: str,
        page: int,
        page_size: int,
    ) -> tuple[list[OnboardingRecord], int]:
        total_result = await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        sort_column = getattr(OnboardingRecord, sort_by, OnboardingRecord.created_at)
        result = await self.session.execute(
            stmt.order_by((desc if sort_order == "desc" else asc)(sort_column))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total_result.scalar() or 0


class DepartureRecordRepository(_LegacyFeishuRecordRepository):
    model = DepartureRecord

    async def list_records(
        self,
        *,
        department: str | None = None,
        offboarding_type: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "offboarding_date",
        sort_order: str = "desc",
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[DepartureRecord], int]:
        stmt = select(DepartureRecord).where(DepartureRecord.is_deleted.is_(False))
        if dept_alias_set is not None:
            stmt = stmt.where(DepartureRecord.department.in_(dept_alias_set))
        if department:
            stmt = stmt.where(DepartureRecord.department == department)
        if offboarding_type:
            stmt = stmt.where(DepartureRecord.offboarding_type == offboarding_type)
        if keyword:
            stmt = stmt.where(
                DepartureRecord.name.ilike(f"%{keyword}%")
                | DepartureRecord.department.ilike(f"%{keyword}%")
                | DepartureRecord.position.ilike(f"%{keyword}%")
            )
        total_result = await self.session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
        sort_column = getattr(
            DepartureRecord, sort_by, DepartureRecord.offboarding_date
        )
        result = await self.session.execute(
            stmt.order_by((desc if sort_order == "desc" else asc)(sort_column))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total_result.scalar() or 0


class TrainingLedgerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, record_id: UUID) -> TrainingLedger | None:
        result = await self.session.execute(
            select(TrainingLedger).where(
                TrainingLedger.id == record_id,
                TrainingLedger.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        *,
        employee_number: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        session_id: UUID | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "training_date",
        sort_order: str = "desc",
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[TrainingLedger], int]:
        stmt = select(TrainingLedger).where(TrainingLedger.is_deleted.is_(False))

        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（兼容存量空值回退授课部门）
            stmt = stmt.where(
                or_(
                    TrainingLedger.ledger_department.in_(dept_alias_set),
                    and_(
                        TrainingLedger.ledger_department.is_(None),
                        TrainingLedger.teaching_dept.in_(dept_alias_set),
                    ),
                )
            )
        if employee_number:
            stmt = stmt.where(TrainingLedger.employee_number == employee_number)
        if session_id:
            stmt = stmt.where(TrainingLedger.session_id == session_id)
        if date_from:
            stmt = stmt.where(TrainingLedger.training_date >= date_from)
        if date_to:
            stmt = stmt.where(TrainingLedger.training_date <= date_to)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        sort_column = getattr(TrainingLedger, sort_by, TrainingLedger.training_date)
        order_func = desc if sort_order == "desc" else asc
        data_stmt = (
            stmt.order_by(order_func(sort_column))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        data_result = await self.session.execute(data_stmt)
        return list(data_result.scalars().all()), total

    async def list_all_for_employee_list(self) -> list[TrainingLedger]:
        """全部未删除且呈现中的台账，按培训日期/时间升序（员工培训清单按姓名全量匹配用）."""
        result = await self.session.execute(
            select(TrainingLedger)
            .where(
                TrainingLedger.is_deleted.is_(False),
                TrainingLedger.is_presented.is_(True),
            )
            .order_by(
                TrainingLedger.training_date.asc(),
                TrainingLedger.training_datetime.asc(),
            )
        )
        return list(result.scalars().all())

    async def list_by_date(self, training_date: date) -> list[TrainingLedger]:
        """查询指定日期的所有未删除台账记录."""
        result = await self.session.execute(
            select(TrainingLedger).where(
                TrainingLedger.training_date == training_date,
                TrainingLedger.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def create(self, record: TrainingLedger) -> TrainingLedger:
        self.session.add(record)
        await self.session.flush()
        # INSERT 后 PostgreSQL RETURNING 自动回填 id/created_at/updated_at
        return record

    async def add_all(self, records: list[TrainingLedger]) -> None:
        """批量新增并一次 flush（导入大批量记录时避免逐行 DB 往返）。"""
        if not records:
            return
        self.session.add_all(records)
        await self.session.flush()

    async def update(self, record: TrainingLedger) -> TrainingLedger:
        await self.session.flush()
        # UPDATE 后必须 select re-fetch 获取 onupdate 回填值
        result = await self.session.execute(
            select(TrainingLedger).where(
                TrainingLedger.id == record.id,
                TrainingLedger.is_deleted.is_(False),
            )
        )
        return result.scalar_one()

    async def soft_delete(self, record: TrainingLedger) -> None:
        record.is_deleted = True
        await self.session.flush()

    @staticmethod
    def bare201_hidden_when_split() -> Any:
        """裸名「201二车间」总副本隐藏条件：同会话已存在规范(MC/DR)拆分副本时.

        返回 SQLAlchemy 条件表达式，作为附加 where 使用；
        无拆分副本的老培训（如 ICH Q7）裸名副本保持可见。
        """
        from sqlalchemy import exists, not_
        from sqlalchemy.orm import aliased

        sibling = aliased(TrainingLedger)
        has_split = exists(
            select(sibling.id).where(
                sibling.session_id == TrainingLedger.session_id,
                sibling.ledger_department.in_(("201二车间（MC）", "201二车间（DR）")),
                sibling.is_deleted.is_(False),
            )
        )
        return not_(
            and_(
                TrainingLedger.ledger_department == "201二车间",
                TrainingLedger.session_id.is_not(None),
                has_split,
            )
        )

    async def list_by_department(
        self,
        department: str,
        page: int = 1,
        page_size: int = 200,
    ) -> tuple[list[TrainingLedger], int]:
        # 按归属部门（ledger_department）筛选；兼容存量空值回退授课部门
        # 201二车间 家族读端集合见 ledger_dept_read_family（MC/DR 不互见）
        from app.modules.hr.training_dept_resolver import ledger_dept_read_family

        dept_values = await ledger_dept_read_family(self.session, department)
        is_201_family = department in ("201二车间（MC）", "201二车间（DR）")
        # 201 家族裸名「201二车间」不能通过 ledger_department/teaching_dept 直接匹配
        # （否则裸名记录会无条件落入 MC/DR），只能按 trainees 的飞书部门归属（下方裸名条件）
        if is_201_family:
            dept_values = [v for v in dept_values if v != "201二车间"]
        conditions = [
            TrainingLedger.ledger_department.in_(dept_values),
            and_(
                TrainingLedger.ledger_department.is_(None),
                TrainingLedger.teaching_dept.in_(dept_values),
            ),
        ]
        # 201 家族裸名「201二车间」记录（归属部门或授课部门为裸名）：
        # 按 trainees 姓名在飞书联系人中的部门判断归属
        # MC 匹配飞书部门 "201二车间"，DR 匹配 "201二车间（多拉）"/"201二车间（多拉菌素）"
        # 仅 201 家族生效；其他部门保持原逻辑（不受影响）
        if is_201_family:
            from sqlalchemy import exists

            from app.modules.hr.models import HrFeishuMember
            from app.modules.hr.training_dept_resolver import training_dept_aliases_of

            feishu_depts = await training_dept_aliases_of(self.session, department)
            if feishu_depts:
                # trainees 是顿号/换行分隔的姓名字符串，
                # 用正则边界匹配飞书联系人姓名 → 检查其 department 是否在目标集合
                has_matching_trainee = exists(
                    select(HrFeishuMember.id).where(
                        HrFeishuMember.is_deleted.is_(False),
                        HrFeishuMember.department.in_(feishu_depts),
                        TrainingLedger.trainees.regexp_match(
                            func.concat(
                                "(^|[、\\s\\n\\r])",
                                HrFeishuMember.name,
                                "([、\\s\\n\\r]|$)",
                            )
                        ),
                    )
                )
                bare_ledger = or_(
                    TrainingLedger.ledger_department == "201二车间",
                    and_(
                        TrainingLedger.ledger_department.is_(None),
                        TrainingLedger.teaching_dept == "201二车间",
                    ),
                )
                conditions.append(
                    and_(
                        bare_ledger,
                        has_matching_trainee,
                    )
                )
        stmt = select(TrainingLedger).where(
            or_(*conditions),
            TrainingLedger.is_deleted.is_(False),
        )
        if is_201_family:
            # 有拆分副本时隐藏裸名总副本（列表与 ESG 同步同口径）
            stmt = stmt.where(self.bare201_hidden_when_split())
        stmt = stmt.order_by(TrainingLedger.training_datetime.desc())

        count_stmt = select(func.count()).select_from(stmt.subquery())
        data_stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        data_result = await self.session.execute(data_stmt)
        return list(data_result.scalars().all()), total

    async def mark_owner_deleted(self, session_id: UUID, exclude_id: UUID) -> None:
        """主办方删除后，同 session 其他未删除副本标记 owner_deleted（变红提示）."""
        await self.session.execute(
            update(TrainingLedger)
            .where(
                TrainingLedger.session_id == session_id,
                TrainingLedger.id != exclude_id,
                TrainingLedger.is_deleted.is_(False),
            )
            .values(owner_deleted=True)
        )

    async def delete_all_by_department(self, department: str) -> int:
        """批量软删除部门全部台账记录，返回删除条数.

        主办方（落款部门）记录被清空时，同培训其他部门副本标记
        owner_deleted（变红提示）。
        """
        rows = (
            (
                await self.session.execute(
                    select(TrainingLedger).where(
                        or_(
                            TrainingLedger.ledger_department == department,
                            and_(
                                TrainingLedger.ledger_department.is_(None),
                                TrainingLedger.teaching_dept == department,
                            ),
                        ),
                        TrainingLedger.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return 0
        # 主办方记录被清空 → 同培训其他部门副本标记 owner_deleted
        for record in rows:
            if record.session_id:
                session = await self.session.get(TrainingSession, record.session_id)
                if (
                    session
                    and session.department
                    and record.ledger_department == session.department
                ):
                    await self.mark_owner_deleted(
                        session_id=record.session_id, exclude_id=record.id
                    )
        for record in rows:
            record.is_deleted = True
        await self.session.flush()
        return len(rows)

    async def get_by_source(
        self, source_type: str, source_id: str
    ) -> TrainingLedger | None:
        result = await self.session.execute(
            select(TrainingLedger).where(
                TrainingLedger.source_type == source_type,
                TrainingLedger.source_id == source_id,
                TrainingLedger.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_all_training_departments(self) -> list[str]:
        "培训模块所有有数据的部门：台账/ESG/年度计划/岗位清单/"
        "培训师/培训会话 并集（单条 UNION 查询）."

        from app.modules.hr.models import (
            EsgTrainingRecord,
            PositionTrainingList,
            Trainer,
            TrainingSession,
        )

        def _dept_stmt(column: Any, model: Any) -> Any:
            return select(column.label("dept")).where(
                model.is_deleted.is_(False),
                column.is_not(None),
                column != "",
            )

        stmts = [
            _dept_stmt(TrainingLedger.teaching_dept, TrainingLedger),
            _dept_stmt(EsgTrainingRecord.department, EsgTrainingRecord),
            _dept_stmt(AnnualTrainingPlan.department, AnnualTrainingPlan),
            _dept_stmt(PositionTrainingList.department, PositionTrainingList),
            _dept_stmt(Trainer.department, Trainer),
            _dept_stmt(TrainingSession.department, TrainingSession),
        ]
        union_subq = union_all(*stmts).subquery()
        # 排除公司级伪部门：培训会话存"公司级"，公司级年度计划存"公司"
        stmt: Select[Any] = (
            select(literal_column("dept"))
            .select_from(union_subq)
            .where(literal_column("dept").not_in(["公司级", "公司"]))
            .distinct()
            .order_by(literal_column("dept"))
        )
        result = await self.session.execute(stmt)
        depts = [row[0] for row in result.all()]

        # 叠加“呈现部门”底：人员配置的部门 +
        # 配置内人员真实部门（稳定，不随培训数据删除而消失）
        from app.modules.hr.models import TrainingPersonnelConfig

        cfg_rows = (
            await self.session.execute(
                select(
                    TrainingPersonnelConfig.department,
                    TrainingPersonnelConfig.personnel,
                ).where(TrainingPersonnelConfig.is_deleted.is_(False))
            )
        ).all()
        for cfg_dept, personnel in cfg_rows:
            if cfg_dept:
                depts.append(cfg_dept)
            if personnel:
                for item in personnel:
                    if isinstance(item, dict) and item.get("department"):
                        depts.append(item["department"])

        # 叠加手动添加的自定义部门（补充数据驱动部门）
        from app.modules.hr.models import HrCustomTrainingDepartment

        custom_rows = (
            await self.session.execute(
                select(HrCustomTrainingDepartment.name).where(
                    HrCustomTrainingDepartment.is_deleted.is_(False)
                )
            )
        ).all()
        for row in custom_rows:
            depts.append(row[0])

        # 后处理：按配置表归一/排除/强制补入（替代原硬编码 201 变体字典）
        # 一次查询，本地分拆为 norm_map / exclude / force_show
        all_mappings = await self.list_dept_mappings()
        norm_map = {
            m.source_name: m.target_name
            for m in all_mappings
            if m.mapping_type in ("special", "alias") and m.target_name
        }
        exclude = {m.source_name for m in all_mappings if m.mapping_type == "exclude"}
        force_show = {
            m.source_name for m in all_mappings if m.mapping_type == "force_show"
        }
        depts = [norm_map.get(d, d) for d in depts]
        depts = [d for d in depts if d not in exclude]
        for sub in sorted(force_show):
            if sub not in depts:
                depts.append(sub)
        return sorted(set(depts))

    async def list_custom_training_departments(self) -> list[str]:
        """获取手动添加的自定义部门列表"""
        from app.modules.hr.models import HrCustomTrainingDepartment

        stmt = (
            select(HrCustomTrainingDepartment.name)
            .where(HrCustomTrainingDepartment.is_deleted.is_(False))
            .order_by(HrCustomTrainingDepartment.name)
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def add_custom_training_department(
        self, name: str
    ) -> "HrCustomTrainingDepartment":
        """新增自定义部门"""
        from app.modules.hr.models import HrCustomTrainingDepartment

        dept = HrCustomTrainingDepartment(name=name)
        self.session.add(dept)
        await self.session.flush()
        return dept

    async def delete_custom_training_department(self, name: str) -> bool:
        """软删除自定义部门，返回是否找到并删除"""
        from app.modules.hr.models import HrCustomTrainingDepartment

        stmt = select(HrCustomTrainingDepartment).where(
            HrCustomTrainingDepartment.name == name,
            HrCustomTrainingDepartment.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        dept = result.scalar_one_or_none()
        if not dept:
            return False
        dept.is_deleted = True
        await self.session.flush()
        return True

    # ─── 培训部门映射配置（HR 设置维护）───

    async def list_dept_mappings(self) -> list["TrainingDeptMapping"]:
        """全部未删除的映射配置（解析层与前端共用，按优先级排序）"""
        from app.modules.hr.models import TrainingDeptMapping

        stmt = (
            select(TrainingDeptMapping)
            .where(TrainingDeptMapping.is_deleted.is_(False))
            .order_by(TrainingDeptMapping.priority, TrainingDeptMapping.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_dept_mapping(self, mapping_id: UUID) -> "TrainingDeptMapping | None":
        """按 ID 查询未删除的映射配置"""
        from app.modules.hr.models import TrainingDeptMapping

        stmt = select(TrainingDeptMapping).where(
            TrainingDeptMapping.id == mapping_id,
            TrainingDeptMapping.is_deleted.is_(False),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create_dept_mapping(self, data: dict[str, Any]) -> "TrainingDeptMapping":
        """新增映射配置"""
        from app.modules.hr.models import TrainingDeptMapping

        mapping = TrainingDeptMapping(**data)
        self.session.add(mapping)
        await self.session.flush()
        return mapping

    async def delete_dept_mapping(self, mapping: Any) -> None:
        """软删除映射配置"""
        mapping.is_deleted = True
        await self.session.flush()

    async def sync_by_session_id(
        self,
        *,
        session_id: UUID,
        exclude_id: UUID,
        update_data: dict[str, Any],
    ) -> int:
        """通过 session_id 批量同步核心字段到同会话的其他台账记录.

        排除当前记录自身，只更新未软删除的记录。
        返回实际更新的行数。
        """
        if not update_data:
            return 0
        stmt = (
            update(TrainingLedger)
            .where(
                TrainingLedger.session_id == session_id,
                TrainingLedger.id != exclude_id,
                TrainingLedger.is_deleted.is_(False),
            )
            .values(**update_data)
        )
        result = cast(CursorResult[Any], await self.session.execute(stmt))
        await self.session.flush()
        return result.rowcount or 0


class TrainingImportMappingRepository:
    """部门培训统计导入格式记忆."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_dept_fingerprint(
        self, department: str, fingerprint: str
    ) -> TrainingImportMapping | None:
        result = await self.session.execute(
            select(TrainingImportMapping).where(
                TrainingImportMapping.department == department,
                TrainingImportMapping.header_fingerprint == fingerprint,
                TrainingImportMapping.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, record: TrainingImportMapping) -> TrainingImportMapping:
        self.session.add(record)
        await self.session.flush()
        # INSERT 后 PostgreSQL RETURNING 自动回填 id/created_at/updated_at
        return record

    async def update(self, record: TrainingImportMapping) -> TrainingImportMapping:
        await self.session.flush()
        # UPDATE 后必须 select re-fetch 获取 onupdate 回填值
        result = await self.session.execute(
            select(TrainingImportMapping).where(
                TrainingImportMapping.id == record.id,
                TrainingImportMapping.is_deleted.is_(False),
            )
        )
        return result.scalar_one()


class TrainingLedgerPageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_pages(self) -> list[TrainingLedgerPage]:
        result = await self.session.execute(
            select(TrainingLedgerPage).where(TrainingLedgerPage.is_deleted.is_(False))
        )
        return list(result.scalars().all())

    async def get_by_employee_number(
        self, employee_number: str
    ) -> TrainingLedgerPage | None:
        result = await self.session.execute(
            select(TrainingLedgerPage).where(
                TrainingLedgerPage.employee_number == employee_number,
                TrainingLedgerPage.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_pages_with_department(
        self,
    ) -> list[tuple[TrainingLedgerPage, str | None]]:
        """List all training ledger pages joined with employee department."""
        result = await self.session.execute(
            select(TrainingLedgerPage, Employee.department)
            .outerjoin(
                Employee, TrainingLedgerPage.employee_number == Employee.employee_number
            )
            .where(TrainingLedgerPage.is_deleted.is_(False))
        )
        return [(row[0], row[1]) for row in result.all()]

    async def create(self, page: TrainingLedgerPage) -> TrainingLedgerPage:
        self.session.add(page)
        await self.session.flush()
        await self.session.refresh(page)
        return page


class AnnualTrainingPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, plan_id: UUID) -> AnnualTrainingPlan | None:
        result = await self.session.execute(
            select(AnnualTrainingPlan)
            .where(
                AnnualTrainingPlan.id == plan_id,
                AnnualTrainingPlan.is_deleted.is_(False),
            )
            .options(selectinload(AnnualTrainingPlan.items))
        )
        return result.scalar_one_or_none()

    async def get_by_year_and_department(
        self, year: int, department: str
    ) -> AnnualTrainingPlan | None:
        result = await self.session.execute(
            select(AnnualTrainingPlan).where(
                AnnualTrainingPlan.year == year,
                AnnualTrainingPlan.department == department,
                AnnualTrainingPlan.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        *,
        year: int | None = None,
        department: str | None = None,
        page: int = 1,
        page_size: int = 20,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[AnnualTrainingPlan], int]:
        stmt = select(AnnualTrainingPlan).where(
            AnnualTrainingPlan.is_deleted.is_(False)
        )

        if year is not None:
            stmt = stmt.where(AnnualTrainingPlan.year == year)
        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合
            stmt = stmt.where(AnnualTrainingPlan.department.in_(dept_alias_set))
        elif department:
            stmt = stmt.where(AnnualTrainingPlan.department.ilike(f"%{department}%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(
            desc(AnnualTrainingPlan.year), asc(AnnualTrainingPlan.department)
        )
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, plan: AnnualTrainingPlan) -> AnnualTrainingPlan:
        self.session.add(plan)
        await self.session.flush()
        await self.session.refresh(plan)
        return plan

    async def update(self, plan: AnnualTrainingPlan) -> AnnualTrainingPlan:
        await self.session.flush()
        await self.session.refresh(plan)
        return plan

    async def soft_delete(self, plan: AnnualTrainingPlan) -> None:
        plan.is_deleted = True
        await self.session.flush()


class AnnualTrainingPlanItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_items(self, plan_id: UUID) -> list[AnnualTrainingPlanItem]:
        result = await self.session.execute(
            select(AnnualTrainingPlanItem)
            .where(
                AnnualTrainingPlanItem.plan_id == plan_id,
                AnnualTrainingPlanItem.is_deleted.is_(False),
            )
            .order_by(
                asc(AnnualTrainingPlanItem.sort_order),
                asc(AnnualTrainingPlanItem.created_at),
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, item_id: UUID) -> AnnualTrainingPlanItem | None:
        result = await self.session.execute(
            select(AnnualTrainingPlanItem).where(
                AnnualTrainingPlanItem.id == item_id,
                AnnualTrainingPlanItem.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, item: AnnualTrainingPlanItem) -> AnnualTrainingPlanItem:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update(self, item: AnnualTrainingPlanItem) -> AnnualTrainingPlanItem:
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete(self, item: AnnualTrainingPlanItem) -> None:
        item.is_deleted = True
        await self.session.flush()

    async def delete_by_plan_id(self, plan_id: UUID) -> None:
        await self.session.execute(
            update(AnnualTrainingPlanItem)
            .where(AnnualTrainingPlanItem.plan_id == plan_id)
            .values(is_deleted=True)
        )
        await self.session.flush()


class TrainingPersonnelConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_configs(
        self,
        *,
        level: str | None = None,
        department: str | None = None,
        owner_id: str | None = None,
    ) -> list[TrainingPersonnelConfig]:
        """列出该级别+部门下配置（如 201车间→A班/B班/C班）。

        owner_id 非空时按创建人隔离（只返回该用户创建的配置）；
        为空（超管）返回全部（含 created_by 为空的历史公共配置）。
        """
        stmt = select(TrainingPersonnelConfig).where(
            TrainingPersonnelConfig.is_deleted.is_(False)
        )
        if level:
            stmt = stmt.where(TrainingPersonnelConfig.level == level)
        if department:
            stmt = stmt.where(TrainingPersonnelConfig.department == department)
        if owner_id:
            stmt = stmt.where(TrainingPersonnelConfig.created_by == owner_id)
        stmt = stmt.order_by(TrainingPersonnelConfig.updated_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(
        self,
        level: str,
        department: str | None,
        config_name: str,
        owner_id: str | None = None,
    ) -> TrainingPersonnelConfig | None:
        """按 (level, department, config_name, created_by) 查找。

        owner_id 非空时限定创建人（同人同名才复用，不同人可各自建同名）；
        为空需显式 created_by IS NULL（历史公共配置），避免误命中他人配置。
        """
        stmt = select(TrainingPersonnelConfig).where(
            TrainingPersonnelConfig.level == level,
            TrainingPersonnelConfig.config_name == config_name,
            TrainingPersonnelConfig.is_deleted.is_(False),
        )
        if department is None:
            stmt = stmt.where(TrainingPersonnelConfig.department.is_(None))
        else:
            stmt = stmt.where(TrainingPersonnelConfig.department == department)
        if owner_id:
            stmt = stmt.where(TrainingPersonnelConfig.created_by == owner_id)
        else:
            stmt = stmt.where(TrainingPersonnelConfig.created_by.is_(None))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, config_id: UUID) -> TrainingPersonnelConfig | None:
        stmt = select(TrainingPersonnelConfig).where(
            TrainingPersonnelConfig.id == config_id,
            TrainingPersonnelConfig.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, record: TrainingPersonnelConfig) -> TrainingPersonnelConfig:
        self.session.add(record)
        await self.session.flush()
        return record

    async def update_fields(
        self,
        record: TrainingPersonnelConfig,
        *,
        personnel: list[Any],
        remarks: str | None,
        config_name: str | None = None,
    ) -> TrainingPersonnelConfig:
        record.personnel = personnel
        if remarks is not None:
            record.remarks = remarks
        if config_name is not None:
            record.config_name = config_name
        await self.session.flush()
        result = await self.session.execute(
            select(TrainingPersonnelConfig)
            .where(TrainingPersonnelConfig.id == record.id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def soft_delete(self, record: TrainingPersonnelConfig) -> None:
        record.is_deleted = True
        await self.session.flush()


class ContractManagementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_new_hires(
        self, *, start_date: date, end_date: date
    ) -> list[ContractManagement]:
        """查询首次签订合同日期在 [start_date, end_date] 范围内的合同记录"""
        stmt = (
            select(ContractManagement)
            .where(
                ContractManagement.is_deleted.is_(False),
                ContractManagement.contract_start_1.is_not(None),
                ContractManagement.contract_start_1 >= start_date,
                ContractManagement.contract_start_1 <= end_date,
            )
            .order_by(asc(ContractManagement.contract_start_1))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class PlanAttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_plan(self, plan_id: UUID) -> list[PlanAttachment]:
        result = await self.session.execute(
            select(PlanAttachment)
            .where(
                PlanAttachment.plan_id == plan_id,
                PlanAttachment.is_deleted.is_(False),
            )
            .order_by(asc(PlanAttachment.created_at))
        )
        return list(result.scalars().all())

    async def get_by_id(self, attachment_id: UUID) -> PlanAttachment | None:
        result = await self.session.execute(
            select(PlanAttachment).where(
                PlanAttachment.id == attachment_id,
                PlanAttachment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, attachment: PlanAttachment) -> PlanAttachment:
        self.session.add(attachment)
        await self.session.flush()
        await self.session.refresh(attachment)
        return attachment

    async def soft_delete(self, attachment: PlanAttachment) -> None:
        attachment.is_deleted = True
        await self.session.flush()


class PlanAttachmentSectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_plan(self, plan_id: UUID) -> list[PlanAttachmentSection]:
        result = await self.session.execute(
            select(PlanAttachmentSection)
            .where(
                PlanAttachmentSection.plan_id == plan_id,
                PlanAttachmentSection.is_deleted.is_(False),
            )
            .order_by(asc(PlanAttachmentSection.created_at))
        )
        return list(result.scalars().all())

    async def list_by_attachment(
        self, attachment_id: UUID
    ) -> list[PlanAttachmentSection]:
        result = await self.session.execute(
            select(PlanAttachmentSection).where(
                PlanAttachmentSection.attachment_id == attachment_id,
                PlanAttachmentSection.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, section_id: UUID) -> PlanAttachmentSection | None:
        result = await self.session.execute(
            select(PlanAttachmentSection).where(
                PlanAttachmentSection.id == section_id,
                PlanAttachmentSection.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, section: PlanAttachmentSection) -> PlanAttachmentSection:
        self.session.add(section)
        await self.session.flush()
        await self.session.refresh(section)
        return section

    async def soft_delete_by_attachment(self, attachment_id: UUID) -> None:
        await self.session.execute(
            update(PlanAttachmentSection)
            .where(PlanAttachmentSection.attachment_id == attachment_id)
            .values(is_deleted=True)
        )
        await self.session.flush()


class EmployeeTrainingListRepository:
    """员工培训清单人员配置（部门→人员；一键导入/手动添加/自动合并）."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_department(
        self, department: str
    ) -> list[EmployeeTrainingListMember]:
        result = await self.session.execute(
            select(EmployeeTrainingListMember)
            .where(
                EmployeeTrainingListMember.department == department,
                EmployeeTrainingListMember.is_deleted.is_(False),
            )
            .order_by(EmployeeTrainingListMember.name.asc())
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[EmployeeTrainingListMember]:
        result = await self.session.execute(
            select(EmployeeTrainingListMember).where(
                EmployeeTrainingListMember.is_deleted.is_(False)
            )
        )
        return list(result.scalars().all())

    async def get_by_department_name(
        self, department: str, name: str
    ) -> EmployeeTrainingListMember | None:
        result = await self.session.execute(
            select(EmployeeTrainingListMember).where(
                EmployeeTrainingListMember.department == department,
                EmployeeTrainingListMember.name == name,
                EmployeeTrainingListMember.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_any_by_department_name(
        self, department: str, name: str
    ) -> EmployeeTrainingListMember | None:
        """按 (department, name) 查询（不过滤软删，供幂等写入时激活历史记录）."""
        result = await self.session.execute(
            select(EmployeeTrainingListMember).where(
                EmployeeTrainingListMember.department == department,
                EmployeeTrainingListMember.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, member_id: UUID) -> EmployeeTrainingListMember | None:
        result = await self.session.execute(
            select(EmployeeTrainingListMember).where(
                EmployeeTrainingListMember.id == member_id,
                EmployeeTrainingListMember.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def upsert_member(
        self,
        department: str,
        name: str,
        employee_number: str | None,
        source: str,
    ) -> EmployeeTrainingListMember:
        """按 (department, name) 幂等插入：已存在则激活/更新工号来源，否则新建.

        历史软删记录（如清除后重新导入）会被重新激活，避免唯一约束冲突。
        """
        existing = await self.get_any_by_department_name(department, name)
        if existing:
            if existing.is_deleted:
                existing.is_deleted = False
            if employee_number and not existing.employee_number:
                existing.employee_number = employee_number
            if existing.source != source and source == "manual":
                existing.source = source
            await self.session.flush()
            return existing
        member = EmployeeTrainingListMember(
            department=department,
            name=name,
            employee_number=employee_number,
            source=source,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def soft_delete(self, member: EmployeeTrainingListMember) -> None:
        member.is_deleted = True
        await self.session.flush()
