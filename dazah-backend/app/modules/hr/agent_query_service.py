"""Bounded HR reads for Agent tools; no configuration or approval operations."""

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.contract_repository import ContractRepository
from app.modules.hr.contract_schemas import ContractApprovalResultItem
from app.modules.hr.models import ContractManagement, HrDepartment, HrFeishuMember


class ContactSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    department: str | None = None
    employee_no: str | None = None
    job_title: str | None = None
    status: str | None = None


class HrAgentQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_departments(
        self,
        *,
        keyword: str | None,
        page: int,
        page_size: int,
        dept_alias_set: set[str] | None,
    ) -> tuple[list[HrDepartment], int]:
        query = select(HrDepartment).where(HrDepartment.is_deleted.is_(False))
        if dept_alias_set is not None:
            query = query.where(HrDepartment.name.in_(dept_alias_set))
        if keyword:
            query = query.where(HrDepartment.name.ilike(f"%{keyword}%"))
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.db.scalars(
            query.order_by(HrDepartment.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(rows.all()), total or 0

    async def list_contacts(
        self,
        *,
        keyword: str | None,
        department: str | None,
        status: str | None,
        page: int,
        page_size: int,
        dept_alias_set: set[str] | None,
    ) -> tuple[list[ContactSummary], int]:
        query = select(HrFeishuMember).where(
            HrFeishuMember.is_deleted.is_(False),
            HrFeishuMember.employee_no.isnot(None),
        )
        if dept_alias_set is not None:
            query = query.where(HrFeishuMember.department.in_(dept_alias_set))
        if department:
            query = query.where(HrFeishuMember.department == department)
        if status:
            query = query.where(HrFeishuMember.status == status)
        if keyword:
            query = query.where(
                or_(
                    HrFeishuMember.name.ilike(f"%{keyword}%"),
                    HrFeishuMember.employee_no.ilike(f"%{keyword}%"),
                    HrFeishuMember.department.ilike(f"%{keyword}%"),
                )
            )
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.db.scalars(
            query.order_by(HrFeishuMember.department.asc(), HrFeishuMember.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [ContactSummary.model_validate(row) for row in rows.all()], total or 0

    async def list_contracts(
        self,
        *,
        keyword: str | None,
        department: str | None,
        contract_sequence: str | None,
        page: int,
        page_size: int,
        dept_alias_set: set[str] | None,
    ) -> tuple[list[ContractManagement], int]:
        rows, total = await ContractRepository(self.db).list(
            keyword=keyword,
            department=department,
            contract_sequence=contract_sequence,
            page=page,
            page_size=page_size,
            dept_alias_set=dept_alias_set,
            approval_statuses=["approved", "synced"],
        )
        return list(rows), int(total)

    async def list_contract_approval_results(
        self,
        *,
        department: str | None,
        result: str | None,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
        dept_alias_set: set[str] | None,
    ) -> tuple[list[dict[str, Any]], int]:
        completed_at = func.coalesce(
            ContractManagement.supervisor_approved_at,
            ContractManagement.dept_approved_at,
            ContractManagement.updated_at,
        )
        query = select(ContractManagement).where(
            ContractManagement.is_deleted.is_(False),
            ContractManagement.approval_status.in_(["approved", "rejected"]),
        )
        if dept_alias_set is not None:
            query = query.where(
                or_(
                    ContractManagement.dept_level1.in_(dept_alias_set),
                    ContractManagement.dept_level2.in_(dept_alias_set),
                )
            )
        if department:
            query = query.where(ContractManagement.dept_level1.ilike(f"{department}%"))
        if result:
            query = query.where(ContractManagement.approval_status == result)
        if start_date:
            query = query.where(
                completed_at
                >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
            )
        if end_date:
            query = query.where(
                completed_at
                <= datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)
            )
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.db.scalars(
            query.order_by(
                completed_at.desc().nullslast(),
                ContractManagement.employee_number.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = []
        for row in rows.all():
            item = ContractApprovalResultItem.model_validate(row).model_dump(
                mode="json"
            )
            ends = [
                str(value).strip()
                for index in range(1, 7)
                if (value := getattr(row, f"contract_end_{index}", None))
                and str(value).strip()
            ]
            item["contract_end_date"] = max(ends, default="")
            completed = row.supervisor_approved_at or row.dept_approved_at
            item["completed_at"] = completed.isoformat() if completed else None
            items.append(item)
        return items, total or 0
