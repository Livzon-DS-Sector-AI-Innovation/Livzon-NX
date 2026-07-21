"""Deviation automation service - overdue reminders and weekly confirmations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models import Deviation, DepartmentContact, DepartmentWeeklyConfirmation

logger = logging.getLogger(__name__)

# Overdue thresholds (days) for each approval step
STEP_OVERDUE_DAYS = {
    "investigation": 7,
    "dept_head_review": 3,
    "cross_dept_head_review": 5,
    "qa_review": 3,
    "qa_head_review": 3,
    "quality_head_review": 3,
    "final_code_input": 3,
}

# Status to approval step mapping
STATUS_TO_STEP = {
    "pending_investigation": "investigation",
    "pending_dept_head_review": "dept_head_review",
    "pending_cross_dept_head_review": "cross_dept_head_review",
    "pending_qa_review": "qa_review",
    "pending_qa_head_review": "qa_head_review",
    "pending_quality_head_review": "quality_head_review",
    "pending_final_code": "final_code_input",
}

APPROVAL_STEP_LABELS = {
    "investigation": "调查",
    "dept_head_review": "部门负责人审核",
    "cross_dept_head_review": "跨部门负责人审核",
    "qa_review": "QA审核",
    "qa_head_review": "QA主管审核",
    "quality_head_review": "质量负责人审核",
    "final_code_input": "填写最终编号",
}

PENDING_STATUSES = list(STATUS_TO_STEP.keys())


async def check_overdue_deviations(db: AsyncSession) -> list[dict]:
    """Find deviations that have exceeded their step deadline."""
    query = select(Deviation).where(
        and_(
            Deviation.is_deleted == False,
            Deviation.status.in_(PENDING_STATUSES),
            Deviation.status_updated_at.isnot(None),
        )
    )
    
    result = await db.execute(query)
    deviations = result.scalars().all()
    
    overdue_items = []
    now = datetime.now(timezone.utc)
    
    for dev in deviations:
        step = STATUS_TO_STEP.get(dev.status)
        if not step:
            continue
        
        limit_days = STEP_OVERDUE_DAYS.get(step, 7)
        if dev.status_updated_at:
            days_elapsed = (now - dev.status_updated_at).days
            if days_elapsed > limit_days:
                overdue_items.append({
                    "id": str(dev.id),
                    "code": dev.deviation_code,
                    "title": dev.title,
                    "status": dev.status,
                    "department": dev.department,
                    "handler": dev.handler,
                    "status_updated_at": dev.status_updated_at.isoformat(),
                    "overdue_days": days_elapsed - limit_days,
                    "step": step,
                    "step_label": APPROVAL_STEP_LABELS.get(step, step),
                })
    
    return overdue_items


async def check_unsubmitted_weekly_confirmations(db: AsyncSession) -> list[dict]:
    """Find departments with production but no deviation submission this week."""
    # Get current week key (e.g., "2026-W23")
    now = datetime.now(timezone.utc)
    iso_cal = now.isocalendar()
    current_week_key = f"{iso_cal[0]}-W{iso_cal[1]:02d}"
    
    # Get all production workshops
    workshop_query = select(DepartmentContact).where(
        and_(
            DepartmentContact.is_deleted == False,
            DepartmentContact.is_production_workshop == True,
        )
    )
    result = await db.execute(workshop_query)
    workshops = result.scalars().all()
    
    unsubmitted = []
    for workshop in workshops:
        # Check if there's a confirmation for this week
        confirm_query = select(DepartmentWeeklyConfirmation).where(
            and_(
                DepartmentWeeklyConfirmation.department == workshop.department,
                DepartmentWeeklyConfirmation.week_key == current_week_key,
            )
        )
        confirm_result = await db.execute(confirm_query)
        confirm = confirm_result.scalar_one_or_none()
        
        if not confirm:
            # No confirmation yet - check if they have production
            unsubmitted.append({
                "department": workshop.department,
                "dept_head_id": str(workshop.dept_head_id) if workshop.dept_head_id else None,
                "gmp_staff_ids": workshop.gmp_staff_ids or [],
            })
        elif confirm.production_status == "production" and confirm.deviation_status == "unsubmitted":
            # Confirmed production but no deviation submitted
            unsubmitted.append({
                "department": workshop.department,
                "dept_head_id": str(workshop.dept_head_id) if workshop.dept_head_id else None,
                "gmp_staff_ids": workshop.gmp_staff_ids or [],
            })
    
    return unsubmitted


def format_overdue_notification(item: dict) -> str:
    """Format an overdue deviation notification message."""
    return (
        f"⚠️ 偏差超期提醒\n\n"
        f"**偏差编号**: {item['code']}\n"
        f"**标题**: {item['title']}\n"
        f"**当前状态**: {item['step_label']}\n"
        f"**超期天数**: {item['overdue_days']}天\n"
        f"**处理人**: {item['handler'] or '未指定'}\n"
        f"**部门**: {item['department'] or '未知'}\n\n"
        f"请及时处理该偏差，避免进一步延误。"
    )


def format_weekly_unsubmitted_notification(dept: dict) -> str:
    """Format a weekly unsubmitted deviation notification message."""
    return (
        f"📋 周偏差确认提醒\n\n"
        f"**部门**: {dept['department']}\n\n"
        f"本周尚未提交偏差确认，请确认本周是否有偏差发生并提交确认。"
    )
