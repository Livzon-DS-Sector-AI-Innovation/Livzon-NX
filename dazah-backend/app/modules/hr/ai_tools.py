"""HR AI 可调用的数据查询工具。

每个工具包含：
- 查询函数：接受 AsyncSession 和参数，返回结构化数据
- Tool Schema：OpenAI function calling 格式的工具定义
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.models import (
    Employee,
    HrDepartment,
    OffboardingRecord,
    PositionTransferRecord,
    TrainingLedger,
)
from app.modules.hr.public_api import (
    group_count_employees,
    query_employees,
)

logger = logging.getLogger(__name__)

# ── 单次最大返回条数 ────────────────────────────────

MAX_RESULTS = 50

# ── Employee 字段白名单（允许 group_by 的维度）──────

_VALID_GROUP_FIELDS = {
    "department",
    "education",
    "gender",
    "status",
    "position",
    "level",
    "employment_type",
    "political_status",
    "marital_status",
    "team",
}

# ═══════════════════════════════════════════════════════════════════
# Tool 1: 查询员工
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_EMPLOYEE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_employee",
        ("description"): (
            "根据姓名或工号查询员工详细信息。支持模糊搜索。返回姓名、工号"
            "、部门、职位、状态、入职日期、学历、性别、手机号等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "员工姓名（支持模糊匹配）或工号",
                },
            },
            "required": ["keyword"],
        },
    },
}


async def hr_query_employee(
    session: AsyncSession, keyword: str
) -> list[dict[str, Any]]:
    """根据姓名或工号查询员工。"""
    # 先精确匹配工号
    stmt = select(Employee).where(
        Employee.employee_number == keyword,
        Employee.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    emp = result.scalar_one_or_none()
    if emp:
        return [_emp_summary(emp)]

    # 模糊匹配
    pattern = f"%{keyword}%"
    stmt = (
        select(Employee)
        .where(
            Employee.is_deleted.is_(False),
            (Employee.name.ilike(pattern)) | (Employee.employee_number.ilike(pattern)),
        )
        .limit(MAX_RESULTS)
    )
    result = await session.execute(stmt)
    return [_emp_summary(e) for e in result.scalars().all()]


def _emp_summary(e: Employee) -> dict[str, Any]:
    return {
        "姓名": e.name,
        "工号": e.employee_number or "",
        "部门": e.department or "",
        "职位": e.position or "",
        "状态": e.status or "",
        "性别": e.gender or "",
        "入职日期": e.hire_date.isoformat() if e.hire_date else "",
        "学历": e.education or "",
        "手机": e.phone or "",
        "级别": e.level or "",
        "用工性质": e.employment_type or "",
    }


# ═══════════════════════════════════════════════════════════════════
# Tool 2: 按维度统计人数
# ═══════════════════════════════════════════════════════════════════

HR_COUNT_BY_FIELD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_count_by_field",
        "description": (
            "按指定维度分组统计在职员工人数。"
            "可统计的维度：department(部门)、education(学历)、gender(性别)、"
            "status(状态)、position(职位)、level(级别)、employment_type(用工性质)、"
            "political_status(政治面貌)、marital_status(婚姻状况)、team(班组)。"
            "也可不传 field 来统计总人数。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    ("description"): (
                        "统计维度，如 department、education、ge"
                        "nder 等。不传则只返回总人数。"
                    ),
                },
            },
        },
    },
}


async def hr_count_by_field(
    session: AsyncSession,
    field: str | None = None,
) -> dict[str, Any]:
    """按维度统计在职员工人数。"""
    filters = {"status": "在职"}

    if field and field in _VALID_GROUP_FIELDS:
        groups = await group_count_employees(session, group_by=field, filters=filters)
        items = [{"value": g["value"] or "未知", "count": g["count"]} for g in groups]
        total = sum(g["count"] for g in groups)
        return {
            "统计维度": field,
            "总人数": total,
            "明细": items,
        }

    # 只查总人数
    _, total = await query_employees(session, filters=filters, page=1, page_size=1)
    return {"总人数": total}


# ═══════════════════════════════════════════════════════════════════
# Tool 3: 查询部门
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_DEPARTMENTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_departments",
        (
            "description"
        ): "查询部门信息，包含编制人数、在岗人数、负责人等。可按关键词搜索。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "部门名称关键词，不传则返回所有部门",
                },
            },
        },
    },
}


async def hr_query_departments(
    session: AsyncSession,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """查询部门信息。"""
    stmt = select(HrDepartment).where(HrDepartment.is_deleted.is_(False))
    if keyword:
        stmt = stmt.where(HrDepartment.name.ilike(f"%{keyword}%"))
    stmt = stmt.limit(MAX_RESULTS)

    result = await session.execute(stmt)
    depts = result.scalars().all()

    return [
        {
            "部门名称": d.name,
            "负责人": d.leader_name or "",
            "编制人数": d.headcount,
            "在岗人数": d.current_count,
            "描述": d.description or "",
        }
        for d in depts
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 4: 合同到期查询
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_CONTRACT_EXPIRING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_contract_expiring",
        "description": "查询合同即将到期或已到期的员工。需要指定日期范围。",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "开始日期，格式 YYYY-MM-DD",
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，格式 YYYY-MM-DD",
                },
                "department": {
                    "type": "string",
                    "description": "部门筛选（可选）",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
}


async def hr_query_contract_expiring(
    session: AsyncSession,
    start_date: str,
    end_date: str,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """查询合同到期人员。会检查员工的全部合同（第1-6次合同到期日）和合同管理表。"""
    from sqlalchemy import or_

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    # 员工表：检查全部合同到期日（仅 Date 类型字段，_5/_6 是字符串跳过）
    stmt = select(Employee).where(
        Employee.is_deleted.is_(False),
        Employee.status == "在职",
        or_(
            Employee.contract_end_date.between(start, end),
            Employee.contract_end_2.between(start, end),
            Employee.contract_end_3.between(start, end),
            Employee.contract_end_4.between(start, end),
        ),
    )
    if department:
        stmt = stmt.where(Employee.department == department)
    stmt = stmt.order_by(Employee.contract_end_date.asc()).limit(MAX_RESULTS)
    result = await session.execute(stmt)
    employees = result.scalars().all()

    # 合同管理表：也查一份
    from app.modules.hr.models import ContractManagement

    cm_stmt = select(ContractManagement).where(
        ContractManagement.is_deleted.is_(False),
        ContractManagement.contract_end_1.between(start, end),
    )
    if department:
        cm_stmt = cm_stmt.where(ContractManagement.dept_level1 == department)
    cm_stmt = cm_stmt.limit(MAX_RESULTS)
    cm_result = await session.execute(cm_stmt)
    contracts = cm_result.scalars().all()

    # 合并去重（按工号）
    seen = set()
    merged = []

    for e in employees:
        key = e.employee_number
        if key and key not in seen:
            seen.add(key)
            merged.append(
                {
                    "姓名": e.name,
                    "工号": key,
                    "部门": e.department or "",
                    "职位": e.position or "",
                    "合同类型": e.contract_type or "",
                    "合同到期日": e.contract_end_date.isoformat()
                    if e.contract_end_date
                    else "",
                    "入职日期": e.hire_date.isoformat() if e.hire_date else "",
                    "数据来源": "员工档案",
                }
            )

    for c in contracts:
        key = c.employee_number
        if key and key not in seen:
            seen.add(key)
            merged.append(
                {
                    "姓名": c.name,
                    "工号": key,
                    "部门": c.dept_level1 or "",
                    "职位": c.position or "",
                    "合同类型": "",
                    "合同到期日": c.contract_end_1.isoformat()
                    if c.contract_end_1
                    else "",
                    "入职日期": "",
                    "数据来源": "合同管理表",
                }
            )

    return merged


# ═══════════════════════════════════════════════════════════════════
# Tool 5: 培训记录查询
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_TRAINING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_training_records",
        (
            "description"
        ): "查询指定员工的培训台账记录，包含培训日期、主题、方式、学时、考核结果等。",
        "parameters": {
            "type": "object",
            "properties": {
                "employee_number": {
                    "type": "string",
                    "description": "员工工号",
                },
            },
            "required": ["employee_number"],
        },
    },
}


async def hr_query_training_records(
    session: AsyncSession,
    employee_number: str,
) -> list[dict[str, Any]]:
    """查询员工培训台账。"""
    stmt = (
        select(TrainingLedger)
        .where(
            TrainingLedger.employee_number == employee_number,
            TrainingLedger.is_deleted.is_(False),
        )
        .order_by(TrainingLedger.training_date.desc())
        .limit(MAX_RESULTS)
    )
    result = await session.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "培训日期": r.training_date.isoformat() if r.training_date else "",
            "培训主题": r.training_subject or "",
            "培训方式": r.training_method or "",
            "学时": r.duration_hours or 0,
            "地点": r.location or "",
            "讲师": r.trainer or "",
            "考核结果": r.assessment_result or "",
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 6: 离职记录查询
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_OFFBOARDING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_offboarding",
        "description": (
            "查询离职记录。可按姓名/工号搜索特定人员，"
            "不传 keyword 则返回最近的全部离职记录（最多 50 条）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "员工姓名或工号（可选，不传则查全部）",
                },
            },
        },
    },
}


async def hr_query_offboarding(
    session: AsyncSession,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """查询离职记录。"""
    stmt = select(OffboardingRecord).where(OffboardingRecord.is_deleted.is_(False))

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            OffboardingRecord.name.ilike(pattern)
            | OffboardingRecord.employee_number.ilike(pattern)
        )

    stmt = stmt.order_by(OffboardingRecord.offboarding_date.desc()).limit(MAX_RESULTS)
    result = await session.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "姓名": r.name or "",
            "工号": r.employee_number or "",
            "部门": r.department or "",
            "职位": r.position or "",
            "最后工作日": r.offboarding_date.isoformat() if r.offboarding_date else "",
            "离职类型": r.offboarding_type or "",
            "离职原因": r.reason or "",
            "状态": r.status or "",
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 8: 入职查询
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_ONBOARDING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_onboarding",
        "description": (
            "查询入职记录（最近入职的员工）。可按姓名/工号搜索特定人员，"
            "不传 keyword 则返回最近入职的员工（最多 50 条）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "员工姓名或工号（可选，不传则查最近入职）",
                },
            },
        },
    },
}


async def hr_query_onboarding(
    session: AsyncSession,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """查询入职记录（基于员工档案的入职日期）。"""
    stmt = select(Employee).where(
        Employee.is_deleted == False,  # noqa: E712
        Employee.hire_date.is_not(None),
    )

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            Employee.name.ilike(pattern)
            | Employee.employee_number.ilike(pattern)
        )

    stmt = stmt.order_by(Employee.hire_date.desc()).limit(MAX_RESULTS)
    result = await session.execute(stmt)
    emps = result.scalars().all()

    return [
        {
            "姓名": e.name or "",
            "工号": e.employee_number or "",
            "部门": e.department or "",
            "职位": e.position or "",
            "入职日期": e.hire_date.isoformat() if e.hire_date else "",
            "状态": e.status or "",
        }
        for e in emps
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 7: 岗位调动查询
# ═══════════════════════════════════════════════════════════════════

HR_QUERY_TRANSFERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_query_position_transfers",
        "description": (
            "查询岗位调动记录。可按姓名/工号搜索特定人员，"
            "不传 keyword 则返回最近的全部调动记录（最多 50 条）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "员工姓名或工号（可选，不传则查全部）",
                },
            },
        },
    },
}


async def hr_query_position_transfers(
    session: AsyncSession,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """查询岗位调动记录。"""
    stmt = select(PositionTransferRecord).where(
        PositionTransferRecord.is_deleted.is_(False)
    )

    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            PositionTransferRecord.employee_name.ilike(pattern)
            | PositionTransferRecord.employee_number.ilike(pattern)
        )

    stmt = stmt.order_by(PositionTransferRecord.effective_date.desc()).limit(
        MAX_RESULTS
    )
    result = await session.execute(stmt)
    records = result.scalars().all()

    return [
        {
            "姓名": r.employee_name or "",
            "工号": r.employee_number or "",
            "原部门": r.department_before or "",
            "调入部门": r.apply_department or "",
            "原职位": r.original_position or "",
            "调入职位": r.apply_position or "",
            "生效日期": r.effective_date.isoformat() if r.effective_date else "",
            "审批状态": r.approval_status or "",
            "调动原因": r.transfer_reason or "",
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 8: 班组查询
# ═══════════════════════════════════════════════════════════════════

HR_LIST_TEAMS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_list_teams",
        "description": "查询班组列表，可按部门筛选。",
        "parameters": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string",
                    "description": "部门名称（可选，不传则返回全部班组）",
                },
            },
        },
    },
}


async def hr_list_teams(
    session: AsyncSession,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """查询班组。"""
    from app.modules.hr.models import Team

    stmt = select(Team).where(Team.is_deleted.is_(False))
    if department:
        stmt = stmt.join(HrDepartment).where(HrDepartment.name == department)
    stmt = stmt.limit(MAX_RESULTS)
    result = await session.execute(stmt)
    return [
        {"班组名称": t.name, "编码": t.code or "", "描述": t.description or ""}
        for t in result.scalars().all()
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 9: 培训师查询
# ═══════════════════════════════════════════════════════════════════

HR_LIST_TRAINERS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_list_trainers",
        "description": "查询培训师名单。",
        "parameters": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string",
                    "description": "部门筛选（可选）",
                },
            },
        },
    },
}


async def hr_list_trainers(
    session: AsyncSession,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """查询培训师。"""
    from app.modules.hr.models import Trainer

    stmt = select(Trainer).where(Trainer.is_deleted.is_(False))
    if department:
        stmt = stmt.where(Trainer.department == department)
    stmt = stmt.limit(MAX_RESULTS)
    result = await session.execute(stmt)
    return [
        {
            "姓名": t.name,
            "部门": t.department or "",
            "岗位": t.position or "",
            "备注": t.remarks or "",
        }
        for t in result.scalars().all()
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 10: 年度培训计划
# ═══════════════════════════════════════════════════════════════════

HR_LIST_TRAINING_PLANS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_list_training_plans",
        "description": "查询年度培训计划，包含计划明细。可按年度和部门筛选。",
        "parameters": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "年度（如 2026），不传则返回所有",
                },
                "department": {
                    "type": "string",
                    "description": "部门筛选（可选）",
                },
            },
        },
    },
}


async def hr_list_training_plans(
    session: AsyncSession,
    year: int | None = None,
    department: str | None = None,
) -> list[dict[str, Any]]:
    """查询年度培训计划（含明细）。"""
    from app.modules.hr.models import AnnualTrainingPlan, AnnualTrainingPlanItem

    stmt = select(AnnualTrainingPlan).where(AnnualTrainingPlan.is_deleted.is_(False))
    if year:
        stmt = stmt.where(AnnualTrainingPlan.year == year)
    if department:
        stmt = stmt.where(AnnualTrainingPlan.department == department)
    stmt = stmt.order_by(AnnualTrainingPlan.year.desc()).limit(MAX_RESULTS)
    result = await session.execute(stmt)
    plans = result.scalars().all()

    data = []
    for p in plans:
        # 查明细
        items_stmt = select(AnnualTrainingPlanItem).where(
            AnnualTrainingPlanItem.plan_id == p.id,
            AnnualTrainingPlanItem.is_deleted.is_(False),
        )
        items_result = await session.execute(items_stmt)
        items = items_result.scalars().all()
        data.append(
            {
                "年度": p.year,
                "部门": p.department,
                "计划级别": p.plan_level,
                "状态": p.status,
                "明细条数": len(items),
                "明细": [
                    {
                        "月份": it.month or "",
                        "培训内容": it.content_and_textbook or "",
                        "培训对象": it.target_audience or "",
                        "培训方式": it.training_method or "",
                        "学时": it.training_hours or 0,
                        "讲师": it.instructor or "",
                        "跟踪状态": it.tracking_status or "",
                    }
                    for it in items
                ],
            }
        )
    return data


# ═══════════════════════════════════════════════════════════════════
# Tool 11: 培训评估
# ═══════════════════════════════════════════════════════════════════

HR_LIST_TRAINING_EVALUATIONS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_list_training_evaluations",
        (
            "description"
        ): "查询培训评估记录，包含培训内容、应到/实到人数、考核成绩分布、评估结果等。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "培训内容关键词（可选）",
                },
            },
        },
    },
}


async def hr_list_training_evaluations(
    session: AsyncSession,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    """查询培训评估。"""
    from app.modules.hr.models import TrainingEvaluation

    stmt = select(TrainingEvaluation).where(TrainingEvaluation.is_deleted.is_(False))
    if keyword:
        stmt = stmt.where(TrainingEvaluation.training_content.ilike(f"%{keyword}%"))
    stmt = stmt.order_by(TrainingEvaluation.training_date.desc()).limit(MAX_RESULTS)
    result = await session.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "培训内容": r.training_content or "",
            "培训日期": r.training_date.isoformat() if r.training_date else "",
            "授课人": r.instructor or "",
            "应到": r.expected_count or 0,
            "实到": r.actual_count or 0,
            "优": r.excellent_count or 0,
            "良": r.good_count or 0,
            "合格": r.pass_count or 0,
            "不合格": r.fail_count or 0,
            "评估结果": r.evaluation_result or "",
            "评估人": r.evaluator or "",
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 12: 培训计划跟踪
# ═══════════════════════════════════════════════════════════════════

HR_LIST_PLAN_TRACKING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_list_plan_tracking",
        "description": "查询培训计划完成跟踪记录，了解各项培训是否按计划完成。",
        "parameters": {
            "type": "object",
            "properties": {
                "is_completed": {
                    "type": "boolean",
                    "description": "是否已完成（可选，不传则查全部）",
                },
            },
        },
    },
}


async def hr_list_plan_tracking(
    session: AsyncSession,
    is_completed: bool | None = None,
) -> list[dict[str, Any]]:
    """查询培训计划跟踪。"""
    from app.modules.hr.models import PlanTrackingRecord

    stmt = select(PlanTrackingRecord).where(PlanTrackingRecord.is_deleted.is_(False))
    if is_completed is not None:
        stmt = stmt.where(PlanTrackingRecord.is_completed == is_completed)
    stmt = stmt.order_by(PlanTrackingRecord.track_date.desc()).limit(MAX_RESULTS)
    result = await session.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "培训内容": r.training_content or "",
            "实际时间": r.actual_time or "",
            "培训对象": r.target_audience or "",
            "是否完成": "是" if r.is_completed else "否",
            "跟踪人": r.tracker or "",
            "跟踪日期": r.track_date.isoformat() if r.track_date else "",
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 14: 合同管理
# ═══════════════════════════════════════════════════════════════════

HR_LIST_CONTRACTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_list_contracts",
        ("description"): (
            "查询合同管理表中的全部合同记录，可按部门筛选。包含合同次数、"
            "起止日期、续签意见等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string",
                    "description": "部门筛选（可选）",
                },
                "employee_number": {
                    "type": "string",
                    "description": "按工号查特定员工的合同（可选）",
                },
            },
        },
    },
}


async def hr_list_contracts(
    session: AsyncSession,
    department: str | None = None,
    employee_number: str | None = None,
) -> list[dict[str, Any]]:
    """查询合同管理记录。"""
    from app.modules.hr.models import ContractManagement

    stmt = select(ContractManagement).where(ContractManagement.is_deleted.is_(False))
    if department:
        stmt = stmt.where(ContractManagement.dept_level1 == department)
    if employee_number:
        stmt = stmt.where(ContractManagement.employee_number == employee_number)
    stmt = stmt.limit(MAX_RESULTS)
    result = await session.execute(stmt)
    records = result.scalars().all()
    return [
        {
            "姓名": r.name,
            "工号": r.employee_number or "",
            "部门": r.dept_level1 or "",
            "职位": r.position or "",
            "第几次合同": r.contract_sequence or "",
            "合同开始": r.contract_start_1.isoformat() if r.contract_start_1 else "",
            "合同结束": r.contract_end_1.isoformat() if r.contract_end_1 else "",
            "续签意见": r.contract_opinion or "",
            "部门负责人": r.dept_leader_name or "",
        }
        for r in records
    ]


# ═══════════════════════════════════════════════════════════════════
# Tool 15: 创建培训记录（写操作）
# ═══════════════════════════════════════════════════════════════════

HR_CREATE_TRAINING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_create_training_record",
        "description": (
            "创建一条培训台账记录。使用前请向用户确认关键信息（工号、培训日期、主题）。"
            "系统会自动保存，无需额外审批。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "employee_number": {
                    "type": "string",
                    "description": "员工工号（必填）",
                },
                "training_date": {
                    "type": "string",
                    "description": "培训日期，格式 YYYY-MM-DD（必填）",
                },
                "training_subject": {
                    "type": "string",
                    "description": "培训主题/课程名称（必填）",
                },
                "training_method": {
                    "type": "string",
                    "description": "培训方式（可选）",
                },
                "duration_hours": {
                    "type": "number",
                    "description": "课时（小时，可选）",
                },
                "trainer": {"type": "string", "description": "培训师/单位（可选）"},
                "assessment_result": {
                    "type": "string",
                    "description": "考核结果（可选）",
                },
                "remarks": {"type": "string", "description": "备注（可选）"},
            },
            "required": ["employee_number", "training_date", "training_subject"],
        },
    },
}


async def hr_create_training_record(
    session: AsyncSession,
    employee_number: str,
    training_date: str,
    training_subject: str,
    training_method: str | None = None,
    duration_hours: float | None = None,
    trainer: str | None = None,
    assessment_result: str | None = None,
    remarks: str | None = None,
) -> dict[str, Any]:
    """创建培训台账记录。"""
    from app.modules.hr.schemas import TrainingLedgerCreate
    from app.modules.hr.service import TrainingLedgerService

    data = TrainingLedgerCreate(
        employee_number=employee_number,
        training_date=date.fromisoformat(training_date),
        training_subject=training_subject,
        training_method=training_method,
        duration_hours=duration_hours,
        trainer=trainer,
        assessment_result=assessment_result,
        remarks=remarks,
    )
    service = TrainingLedgerService(session)
    record = await service.create_record(data)
    return {
        "success": True,
        "id": str(record.id),
        "message": f"已为 {employee_number} 创建培训记录：{training_subject}",
    }


# ═══════════════════════════════════════════════════════════════════
# Tool 16: 创建离职记录（写操作）
# ═══════════════════════════════════════════════════════════════════

HR_CREATE_OFFBOARDING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_create_offboarding_record",
        "description": (
            "创建一条离职记录。⚠️ 此操作会将员工状态改为'离职'，请务必先与用户确认。"
            "需要提供工号、离职日期、离职类型和原因。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "employee_number": {
                    "type": "string",
                    "description": "员工工号（必填）",
                },
                "offboarding_date": {
                    "type": "string",
                    "description": "离职日期（最后工作日），格式 YYYY-MM-DD（必填）",
                },
                "offboarding_type": {
                    "type": "string",
                    "description": "离职类型：辞职/辞退/合同到期/退休/其他（必填）",
                },
                "reason": {"type": "string", "description": "离职原因（必填）"},
                "notes": {"type": "string", "description": "备注（可选）"},
            },
            "required": [
                "employee_number",
                "offboarding_date",
                "offboarding_type",
                "reason",
            ],
        },
    },
}


async def hr_create_offboarding_record(
    session: AsyncSession,
    employee_number: str,
    offboarding_date: str,
    offboarding_type: str,
    reason: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """创建离职记录。"""
    from app.modules.hr.schemas import OffboardingRecordCreate
    from app.modules.hr.service import OffboardingRecordService

    data = OffboardingRecordCreate(
        employee_number=employee_number,
        offboarding_date=date.fromisoformat(offboarding_date),
        offboarding_type=offboarding_type,
        reason=reason,
        notes=notes,
    )
    service = OffboardingRecordService(session)
    record = await service.create_record(data)
    return {
        "success": True,
        "id": str(record.id),
        "message": f"已为 {employee_number} 创建离职记录，员工状态已更新为离职",
    }


# ═══════════════════════════════════════════════════════════════════
# Tool 17: 更新员工基本信息（写操作）
# ═══════════════════════════════════════════════════════════════════

HR_UPDATE_EMPLOYEE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "hr_update_employee_basic",
        "description": (
            "更新员工的基本联系信息（手机、邮箱）。仅限非敏感字段。"
            "修改前请先查询确认工号无误。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "employee_number": {
                    "type": "string",
                    "description": "员工工号（必填）",
                },
                "phone": {"type": "string", "description": "手机号（可选）"},
                "email": {"type": "string", "description": "邮箱（可选）"},
            },
            "required": ["employee_number"],
        },
    },
}


async def hr_update_employee_basic(
    session: AsyncSession,
    employee_number: str,
    phone: str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    """更新员工基本信息。"""
    from app.modules.hr.schemas import EmployeeUpdate
    from app.modules.hr.service import EmployeeService

    # 先确认员工存在
    stmt = select(Employee).where(
        Employee.employee_number == employee_number,
        Employee.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    emp = result.scalar_one_or_none()
    if not emp:
        return {"success": False, "error": f"未找到工号为 {employee_number} 的员工"}

    update_data = EmployeeUpdate()
    if phone:
        update_data.phone = phone
    if email:
        update_data.email = email

    service = EmployeeService(session)
    await service.update_employee(emp.id, update_data)
    changes = []
    if phone:
        changes.append(f"手机→{phone}")
    if email:
        changes.append(f"邮箱→{email}")
    return {
        "success": True,
        "message": f"已更新 {emp.name}({employee_number}) 的 {', '.join(changes)}",
    }


# ═══════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════

# 所有工具 Schema 列表
ALL_TOOL_SCHEMAS = [
    HR_QUERY_EMPLOYEE_SCHEMA,
    HR_COUNT_BY_FIELD_SCHEMA,
    HR_QUERY_DEPARTMENTS_SCHEMA,
    HR_QUERY_CONTRACT_EXPIRING_SCHEMA,
    HR_QUERY_TRAINING_SCHEMA,
    HR_QUERY_OFFBOARDING_SCHEMA,
    HR_QUERY_TRANSFERS_SCHEMA,
    HR_QUERY_ONBOARDING_SCHEMA,
    HR_LIST_TEAMS_SCHEMA,
    HR_LIST_TRAINERS_SCHEMA,
    HR_LIST_TRAINING_PLANS_SCHEMA,
    HR_LIST_TRAINING_EVALUATIONS_SCHEMA,
    HR_LIST_PLAN_TRACKING_SCHEMA,
    HR_LIST_CONTRACTS_SCHEMA,
    HR_CREATE_TRAINING_SCHEMA,
    HR_CREATE_OFFBOARDING_SCHEMA,
    HR_UPDATE_EMPLOYEE_SCHEMA,
]

# 工具名 → 执行函数映射
TOOL_EXECUTORS: dict[str, Any] = {
    "hr_query_employee": hr_query_employee,
    "hr_count_by_field": hr_count_by_field,
    "hr_query_departments": hr_query_departments,
    "hr_query_contract_expiring": hr_query_contract_expiring,
    "hr_query_training_records": hr_query_training_records,
    "hr_query_offboarding": hr_query_offboarding,
    "hr_query_position_transfers": hr_query_position_transfers,
    "hr_query_onboarding": hr_query_onboarding,
    "hr_list_teams": hr_list_teams,
    "hr_list_trainers": hr_list_trainers,
    "hr_list_training_plans": hr_list_training_plans,
    "hr_list_training_evaluations": hr_list_training_evaluations,
    "hr_list_plan_tracking": hr_list_plan_tracking,
    "hr_list_contracts": hr_list_contracts,
    "hr_create_training_record": hr_create_training_record,
    "hr_create_offboarding_record": hr_create_offboarding_record,
    "hr_update_employee_basic": hr_update_employee_basic,
}
