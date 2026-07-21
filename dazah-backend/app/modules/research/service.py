"""Research business workflows."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateException, NotFoundException
from app.modules.research import repository as repo
from app.modules.research.models import ResearchProject
from app.modules.research.schemas import (
    ResearchProjectCreate,
    ResearchProjectUpdate,
)


async def create_project(
    db: AsyncSession, data: ResearchProjectCreate
) -> ResearchProject:
    # Auto-generate project_no if not provided
    project_no = data.project_no
    if not project_no:
        project_no = f"PRJ-{str(uuid.uuid4())[:8].upper()}"
    
    if await repo.exists_by_project_no(db, project_no):
        raise DuplicateException("项目编号", project_no)
    
    project_data = data.model_dump()
    project_data["project_no"] = project_no
    return await repo.create_project(db, project_data)


async def get_project(db: AsyncSession, project_id: uuid.UUID) -> ResearchProject:
    project = await repo.get_project_by_id(db, project_id)
    if not project:
        raise NotFoundException("研发项目", str(project_id))
    return project


async def get_projects(
    db: AsyncSession,
    stage: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    project_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ResearchProject], int]:
    return await repo.get_projects(
        db, stage=stage, status=status, keyword=keyword, project_type=project_type,
        page=page, page_size=page_size
    )


async def update_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: ResearchProjectUpdate,
) -> ResearchProject:
    project = await get_project(db, project_id)
    update_data = data.model_dump(exclude_unset=True)
    if "project_no" in update_data and update_data["project_no"] != project.project_no:
        if await repo.exists_by_project_no(db, update_data["project_no"], exclude_id=project_id):
            raise DuplicateException("项目编号", update_data["project_no"])
    return await repo.update_project(db, project, update_data)


async def delete_project(db: AsyncSession, project_id: uuid.UUID) -> None:
    project = await get_project(db, project_id)
    await repo.delete_project(db, project)


# ICH Analysis functions
from app.modules.research.models import ICHAnalysisRecord
from sqlalchemy import select, func


async def analyze_ich_q3c(
    db: AsyncSession,
    file_content: bytes,
    filename: str,
    route: str | None = None,
) -> dict:
    """Analyze ICH Q3C solvent residuals from uploaded file."""
    # TODO: Implement actual Q3C analysis logic
    # For now, create a placeholder record
    record = ICHAnalysisRecord(
        filename=filename,
        route=route,
        q3c_result={"status": "pending", "message": "Q3C analysis not yet implemented"},
        q3d_result=None,
        llm_used=False,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    
    return {
        "id": str(record.id),
        "filename": record.filename,
        "route": record.route,
        "q3c_result": record.q3c_result,
        "q3d_result": record.q3d_result,
        "llm_used": record.llm_used,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


async def analyze_ich_combined(
    db: AsyncSession,
    file_content: bytes,
    filename: str,
    route: str | None = None,
    use_llm: bool = False,
) -> dict:
    """Analyze ICH Q3C/Q3D combined analysis from uploaded file."""
    # TODO: Implement actual combined analysis logic
    # For now, create a placeholder record
    record = ICHAnalysisRecord(
        filename=filename,
        route=route,
        q3c_result={"status": "pending", "message": "Q3C analysis not yet implemented"},
        q3d_result={"status": "pending", "message": "Q3D analysis not yet implemented"},
        llm_used=use_llm,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    
    return {
        "id": str(record.id),
        "filename": record.filename,
        "route": record.route,
        "q3c_result": record.q3c_result,
        "q3d_result": record.q3d_result,
        "llm_used": record.llm_used,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


async def get_ich_records(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ICHAnalysisRecord], int]:
    """Get paginated ICH analysis records."""
    # Get total count
    count_query = select(func.count()).select_from(ICHAnalysisRecord)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated records
    query = (
        select(ICHAnalysisRecord)
        .order_by(ICHAnalysisRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    records = list(result.scalars().all())
    
    return records, total


async def get_ich_record(
    db: AsyncSession,
    record_id: uuid.UUID,
) -> ICHAnalysisRecord:
    """Get single ICH analysis record by ID."""
    query = select(ICHAnalysisRecord).where(ICHAnalysisRecord.id == record_id)
    result = await db.execute(query)
    record = result.scalar_one_or_none()
    
    if not record:
        raise NotFoundException("ICH Q3C/Q3D 杂质识别记录", str(record_id))
    
    return record


async def delete_ich_record(
    db: AsyncSession,
    record_id: uuid.UUID,
) -> None:
    """Delete ICH analysis record by ID."""
    record = await get_ich_record(db, record_id)
    await db.delete(record)
    await db.commit()



