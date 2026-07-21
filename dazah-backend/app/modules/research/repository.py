"""Research database queries."""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.research.models import (
    PilotWorkflow,
    PilotWorkflowStep,
    ResearchProject,
)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def exists_by_project_no(
    db: AsyncSession,
    project_no: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    query = select(ResearchProject.id).where(
        ResearchProject.project_no == project_no,
        ResearchProject.is_deleted == False,  # noqa: E712
    )
    if exclude_id:
        query = query.where(ResearchProject.id != exclude_id)
    result = await db.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def create_project(db: AsyncSession, data: dict[str, Any]) -> ResearchProject:
    project = ResearchProject(**data)
    db.add(project)
    await db.flush()
    return project


async def get_project_by_id(
    db: AsyncSession, project_id: uuid.UUID
) -> ResearchProject | None:
    result = await db.execute(
        select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_projects(
    db: AsyncSession,
    stage: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    project_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ResearchProject], int]:
    query = select(ResearchProject).where(
        ResearchProject.is_deleted == False,  # noqa: E712
    )
    count_query = select(func.count()).select_from(ResearchProject).where(
        ResearchProject.is_deleted == False,  # noqa: E712
    )

    if stage:
        query = query.where(ResearchProject.stage == stage)
        count_query = count_query.where(ResearchProject.stage == stage)
    if status:
        query = query.where(ResearchProject.status == status)
        count_query = count_query.where(ResearchProject.status == status)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        like_filter = or_(
            ResearchProject.project_no.ilike(pattern),
            ResearchProject.name.ilike(pattern),
        )
        query = query.where(like_filter)
        count_query = count_query.where(like_filter)
    if project_type is not None:
        if project_type == "":
            query = query.where(ResearchProject.project_type == None)
            count_query = count_query.where(ResearchProject.project_type == None)
        else:
            query = query.where(ResearchProject.project_type == project_type)
            count_query = count_query.where(ResearchProject.project_type == project_type)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(ResearchProject.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def update_project(
    db: AsyncSession,
    project: ResearchProject,
    data: dict[str, Any],
) -> ResearchProject:
    for key, value in data.items():
        setattr(project, key, value)
    await db.flush()
    return project


async def delete_project(db: AsyncSession, project: ResearchProject) -> None:
    project.is_deleted = True
    await db.flush()




# ===== Pilot Workflow Repository =====



async def create_workflow(
    db: AsyncSession, data: dict[str, Any]
) -> PilotWorkflow:
    workflow = PilotWorkflow(**data)
    db.add(workflow)
    await db.flush()
    return workflow


async def get_workflow_by_id(
    db: AsyncSession, workflow_id: uuid.UUID
) -> PilotWorkflow | None:
    result = await db.execute(
        select(PilotWorkflow).where(
            PilotWorkflow.id == workflow_id,
            PilotWorkflow.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_workflows(
    db: AsyncSession,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PilotWorkflow], int]:
    query = select(PilotWorkflow).where(
        PilotWorkflow.is_deleted == False,  # noqa: E712
    )
    count_query = select(func.count()).select_from(PilotWorkflow).where(
        PilotWorkflow.is_deleted == False,  # noqa: E712
    )

    if status:
        query = query.where(PilotWorkflow.status == status)
        count_query = count_query.where(PilotWorkflow.status == status)
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        query = query.where(PilotWorkflow.product_name.ilike(pattern))
        count_query = count_query.where(PilotWorkflow.product_name.ilike(pattern))

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(PilotWorkflow.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    result = await db.execute(query)
    return result.scalars().all(), total


async def delete_workflow(
    db: AsyncSession, workflow: PilotWorkflow
) -> None:
    workflow.is_deleted = True
    await db.flush()


async def get_workflow_steps(
    db: AsyncSession, workflow_id: uuid.UUID
) -> list[PilotWorkflowStep]:
    result = await db.execute(
        select(PilotWorkflowStep)
        .where(
            PilotWorkflowStep.workflow_id == workflow_id,
            PilotWorkflowStep.is_deleted == False,  # noqa: E712
        )
        .order_by(PilotWorkflowStep.step_order)
    )
    return list(result.scalars().all())


async def get_workflow_step_by_id(
    db: AsyncSession, step_id: uuid.UUID
) -> PilotWorkflowStep | None:
    result = await db.execute(
        select(PilotWorkflowStep).where(
            PilotWorkflowStep.id == step_id,
            PilotWorkflowStep.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()
