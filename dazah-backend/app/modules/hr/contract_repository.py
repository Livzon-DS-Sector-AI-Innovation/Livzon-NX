"""合同管理 Repository"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import ContractManagement
from app.platform.identity.data_scope import (
    current_page_actor,
    resolve_user_department_scope,
)


class ContractRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(
        self,
        page: Any = 1,
        page_size: Any = 20,
        keyword: Any = None,
        department: Any = None,
        contract_sequence: Any = None,
        approval_statuses: Any = None,
        dept_alias_set: Any = None,
    ) -> Any:
        base = select(ContractManagement).where(
            ContractManagement.is_deleted.is_(False),
        )
        actor = current_page_actor.get()
        if actor is not None:
            scope = await resolve_user_department_scope(self.session, actor)
            if not scope.is_all:
                base = base.where(
                    or_(
                        ContractManagement.dept_level1.in_(scope.department_names),
                        ContractManagement.dept_level2.in_(scope.department_names),
                    )
                )
        if approval_statuses:
            base = base.where(ContractManagement.approval_status.in_(approval_statuses))
        if keyword:
            base = base.where(
                or_(
                    ContractManagement.name.ilike(f"{keyword}%"),
                    ContractManagement.employee_number.ilike(f"{keyword}%"),
                )
            )
        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（一级/二级部门任一命中）
            base = base.where(
                or_(
                    ContractManagement.dept_level1.in_(dept_alias_set),
                    ContractManagement.dept_level2.in_(dept_alias_set),
                )
            )
        elif department:
            base = base.where(ContractManagement.dept_level1.ilike(f"{department}%"))
        if contract_sequence:
            base = base.where(ContractManagement.contract_sequence == contract_sequence)
        count_stmt = select(func.count()).select_from(base.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        stmt = base.order_by(ContractManagement.employee_number.asc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_by_id(self, record_id: UUID) -> Any:
        statement = select(ContractManagement).where(
            ContractManagement.id == record_id,
            ContractManagement.is_deleted.is_(False),
        )
        actor = current_page_actor.get()
        if actor is not None:
            scope = await resolve_user_department_scope(self.session, actor)
            if not scope.is_all:
                statement = statement.where(
                    or_(
                        ContractManagement.dept_level1.in_(scope.department_names),
                        ContractManagement.dept_level2.in_(scope.department_names),
                    )
                )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> Any:
        record = ContractManagement(**data)
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def update(self, record: ContractManagement, data: dict[str, Any]) -> Any:
        for key, value in data.items():
            setattr(record, key, value)
        await self.session.flush()
        await self.session.refresh(record)
        return record

    async def soft_delete(self, record: ContractManagement) -> Any:
        record.is_deleted = True
        await self.session.flush()
