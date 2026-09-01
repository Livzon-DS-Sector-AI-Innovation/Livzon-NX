"""HR 模块暴露给 AI Agent 的 MCP Tools。

设计原则：
- 只暴露查询类接口，写操作需要通过审批流程
- 返回结构化数据供 LLM 理解和回复
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.modules.hr.models import (
    Employee,
    HrDepartment,
    OffboardingRecord,
    PositionTransferRecord,
    TrainingLedger,
)
from app.platform.mcp.deps import get_db
from app.platform.mcp.server import mcp

logger = logging.getLogger(__name__)

# ── Tool 1: 查询员工 ──────────────────────────────────────


@mcp.tool()
async def hr_query_employee(keyword: str) -> list[dict[str, Any]]:
    """
    根据姓名或工号模糊查询人事系统中的员工信息。
    返回匹配的员工列表，包含姓名、工号、部门、职位、状态、入职日期等。

    Args:
        keyword: 员工姓名（支持模糊匹配）或工号
    """
    db = get_db()

    # 先精确匹配工号
    stmt = select(Employee).where(
        Employee.employee_number == keyword,
        Employee.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    emp = result.scalar_one_or_none()
    if emp:
        return [_emp_to_dict(emp)]

    # 模糊匹配姓名或工号
    pattern = f"%{keyword}%"
    stmt = (
        select(Employee)
        .where(
            Employee.is_deleted == False,  # noqa: E712
            (Employee.name.ilike(pattern)) | (Employee.employee_number.ilike(pattern)),
        )
        .limit(10)
    )
    result = await db.execute(stmt)
    employees = result.scalars().all()
    return [_emp_to_dict(e) for e in employees]


def _emp_to_dict(e: Employee) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "name": e.name,
        "employee_number": e.employee_number,
        "department": e.department or "",
        "sub_department": e.sub_department or "",
        "position": e.position or "",
        "status": e.status or "",
        "gender": e.gender or "",
        "phone": e.phone or "",
        "email": e.email or "",
        "hire_date": e.hire_date.isoformat() if e.hire_date else "",
        "education": e.education or "",
        "level": e.level or "",
        "employment_type": e.employment_type or "",
    }


# ── Tool 2: 查询培训记录 ──────────────────────────────────


@mcp.tool()
async def hr_query_training_records(employee_number: str) -> list[dict[str, Any]]:
    """
    查询指定员工的培训台账记录。

    Args:
        employee_number: 员工工号
    """
    db = get_db()

    stmt = (
        select(TrainingLedger)
        .where(
            TrainingLedger.employee_number == employee_number,
            TrainingLedger.is_deleted == False,  # noqa: E712
        )
        .order_by(TrainingLedger.training_date.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "training_date": r.training_date.isoformat() if r.training_date else "",
            "training_subject": r.training_subject or "",
            "training_method": r.training_method or "",
            "duration_hours": r.duration_hours or 0,
            "location": r.location or "",
            "trainer": r.trainer or "",
            "assessment_result": r.assessment_result or "",
            "remarks": r.remarks or "",
        }
        for r in records
    ]


# ── Tool 6: 合同到期人员 ──────────────────────────────────


@mcp.tool()
async def hr_query_contract_expiring(
    start_date: str,
    end_date: str,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """
    批量查询合同到期人员。输入日期范围，返回该期间内合同到期的员工列表。
    日期格式：YYYY-MM-DD

    Args:
        start_date: 开始日期（如 2026-01-01）
        end_date: 结束日期（如 2026-03-31）
        department: 部门筛选，可选
    """
    db = get_db()
    from datetime import date

    from app.modules.hr.service import EmployeeService

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    service = EmployeeService(db)
    employees, _total = await service.list_contract_expiring(
        start_date=start,
        end_date=end,
        department=department,
        page=1,
        page_size=100,
    )
    return [
        {
            "name": e.get("name", ""),
            "employee_number": e.get("employee_number", ""),
            "department": e.get("department", ""),
            "position": e.get("position", ""),
            "contract_end_date": e.get("contract_end_date", ""),
            "contract_type": e.get("contract_type", ""),
        }
        for e in employees
    ]


# ── Tool 3: 查询部门 ──────────────────────────────────────


@mcp.tool()
async def hr_query_departments(keyword: str | None = None) -> list[dict[str, Any]]:
    """
    查询部门列表，支持按关键词搜索。

    Args:
        keyword: 部门名称关键词，不传则返回所有部门
    """
    db = get_db()

    stmt = select(HrDepartment).where(
        HrDepartment.is_deleted == False,  # noqa: E712
    )
    if keyword:
        stmt = stmt.where(HrDepartment.name.ilike(f"%{keyword}%"))
    stmt = stmt.limit(100)

    result = await db.execute(stmt)
    depts = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "leader_name": d.leader_name or "",
            "parent_name": getattr(d, "parent_name", "") or "",
            "description": getattr(d, "description", "") or "",
        }
        for d in depts
    ]


# ── Tool 4: 查询离职记录 ──────────────────────────────────


@mcp.tool()
async def hr_query_offboarding(keyword: str) -> list[dict[str, Any]]:
    """
    查询离职记录，按姓名或工号搜索。

    Args:
        keyword: 员工姓名或工号
    """
    db = get_db()

    pattern = f"%{keyword}%"
    stmt = (
        select(OffboardingRecord)
        .where(
            OffboardingRecord.is_deleted == False,  # noqa: E712
            (
                OffboardingRecord.name.ilike(pattern)
                | OffboardingRecord.employee_number.ilike(pattern)
            ),
        )
        .limit(20)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "employee_name": r.name or "",
            "employee_number": r.employee_number or "",
            "department": r.department or "",
            "position": r.position or "",
            "last_working_day": r.offboarding_date.isoformat()
            if r.offboarding_date
            else "",
            "offboarding_type": r.offboarding_type or "",
            "offboarding_reason": r.reason or "",
            "status": r.status or "",
        }
        for r in records
    ]


# ── Tool 5: 查询岗位调动 ──────────────────────────────────


@mcp.tool()
async def hr_query_position_transfers(keyword: str) -> list[dict[str, Any]]:
    """
    查询岗位调动记录，按姓名或工号搜索。

    Args:
        keyword: 员工姓名或工号
    """
    db = get_db()

    pattern = f"%{keyword}%"
    stmt = (
        select(PositionTransferRecord)
        .where(
            PositionTransferRecord.is_deleted == False,  # noqa: E712
            (
                PositionTransferRecord.employee_name.ilike(pattern)
                | PositionTransferRecord.employee_number.ilike(pattern)
            ),
        )
        .order_by(PositionTransferRecord.effective_date.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "employee_name": r.employee_name or "",
            "employee_number": r.employee_number or "",
            "department_before": r.department_before or "",
            "apply_department": r.apply_department or "",
            "original_position": r.original_position or "",
            "apply_position": r.apply_position or "",
            "effective_date": r.effective_date.isoformat() if r.effective_date else "",
            "approval_status": r.approval_status or "",
            "transfer_reason": r.transfer_reason or "",
        }
        for r in records
    ]
