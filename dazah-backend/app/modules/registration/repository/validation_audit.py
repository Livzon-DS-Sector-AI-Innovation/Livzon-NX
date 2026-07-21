"""Validation Audit database queries."""

from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registration.models.validation_audit import (
    ValidationAuditFile,
    ValidationAuditIssue,
    ValidationAuditKnowledgeBase,
    ValidationAuditReport,
    ValidationAuditTask,
)


class ValidationAuditTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, task_id: UUID) -> ValidationAuditTask | None:
        result = await self.session.execute(
            select(ValidationAuditTask).where(
                ValidationAuditTask.id == task_id,
                ValidationAuditTask.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        *,
        product_name: str | None = None,
        source_company: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[ValidationAuditTask], int]:
        stmt = select(ValidationAuditTask).where(
            ValidationAuditTask.is_deleted.is_(False)
        )

        if product_name:
            stmt = stmt.where(
                ValidationAuditTask.product_name.ilike(f"%{product_name}%")
            )
        if source_company:
            stmt = stmt.where(
                ValidationAuditTask.source_company.ilike(f"%{source_company}%")
            )
        if status:
            stmt = stmt.where(ValidationAuditTask.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        default_sort = ValidationAuditTask.created_at
        sort_column = getattr(ValidationAuditTask, sort_by, default_sort)
        order_func = desc if sort_order == "desc" else asc
        stmt = stmt.order_by(order_func(sort_column))
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, task: ValidationAuditTask) -> ValidationAuditTask:
        self.session.add(task)
        await self.session.flush()
        # Re-fetch with select (no db.refresh)
        result = await self.session.execute(
            select(ValidationAuditTask).where(
                ValidationAuditTask.id == task.id,
            )
        )
        return result.scalar_one()

    async def update(self, task: ValidationAuditTask, **kwargs) -> ValidationAuditTask:
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        await self.session.flush()
        # Re-fetch with select (no db.refresh)
        result = await self.session.execute(
            select(ValidationAuditTask).where(
                ValidationAuditTask.id == task.id,
            )
        )
        return result.scalar_one()

    async def soft_delete(self, task: ValidationAuditTask) -> None:
        """级联软删除：任务 + 关联文件 + 问题 + 报告"""
        task.is_deleted = True

        # Soft delete related files
        result = await self.session.execute(
            select(ValidationAuditFile).where(
                ValidationAuditFile.task_id == task.id,
                ValidationAuditFile.is_deleted.is_(False),
            )
        )
        for file in result.scalars().all():
            file.is_deleted = True

        # Soft delete related issues
        result = await self.session.execute(
            select(ValidationAuditIssue).where(
                ValidationAuditIssue.task_id == task.id,
                ValidationAuditIssue.is_deleted.is_(False),
            )
        )
        for issue in result.scalars().all():
            issue.is_deleted = True

        # Soft delete related reports
        result = await self.session.execute(
            select(ValidationAuditReport).where(
                ValidationAuditReport.task_id == task.id,
                ValidationAuditReport.is_deleted.is_(False),
            )
        )
        for report in result.scalars().all():
            report.is_deleted = True

        await self.session.flush()


class ValidationAuditFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, file_id: UUID) -> ValidationAuditFile | None:
        result = await self.session.execute(
            select(ValidationAuditFile).where(
                ValidationAuditFile.id == file_id,
                ValidationAuditFile.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_task_id(self, task_id: UUID) -> list[ValidationAuditFile]:
        result = await self.session.execute(
            select(ValidationAuditFile).where(
                ValidationAuditFile.task_id == task_id,
                ValidationAuditFile.is_deleted.is_(False),
            ).order_by(ValidationAuditFile.created_at)
        )
        return list(result.scalars().all())

    async def create(self, file: ValidationAuditFile) -> ValidationAuditFile:
        self.session.add(file)
        await self.session.flush()
        result = await self.session.execute(
            select(ValidationAuditFile).where(
                ValidationAuditFile.id == file.id,
            )
        )
        return result.scalar_one()

    async def update_parse_result(
        self, file: ValidationAuditFile, *, parse_status: str, parsed_text: str | None = None
    ) -> ValidationAuditFile:
        file.parse_status = parse_status
        if parsed_text is not None:
            file.parsed_text = parsed_text
        await self.session.flush()
        result = await self.session.execute(
            select(ValidationAuditFile).where(
                ValidationAuditFile.id == file.id,
            )
        )
        return result.scalar_one()


class ValidationAuditIssueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_by_task_id(
        self,
        task_id: UUID,
        *,
        issue_type: str | None = None,
    ) -> list[ValidationAuditIssue]:
        stmt = select(ValidationAuditIssue).where(
            ValidationAuditIssue.task_id == task_id,
            ValidationAuditIssue.is_deleted.is_(False),
        )
        if issue_type:
            stmt = stmt.where(ValidationAuditIssue.issue_type == issue_type)
        stmt = stmt.order_by(ValidationAuditIssue.issue_no)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_batch(self, issues: list[ValidationAuditIssue]) -> list[ValidationAuditIssue]:
        self.session.add_all(issues)
        await self.session.flush()
        if not issues:
            return []
        task_id = issues[0].task_id
        result = await self.session.execute(
            select(ValidationAuditIssue).where(
                ValidationAuditIssue.task_id == task_id,
                ValidationAuditIssue.is_deleted.is_(False),
            ).order_by(ValidationAuditIssue.issue_no)
        )
        return list(result.scalars().all())


class ValidationAuditReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_task_id(self, task_id: UUID) -> ValidationAuditReport | None:
        result = await self.session.execute(
            select(ValidationAuditReport).where(
                ValidationAuditReport.task_id == task_id,
                ValidationAuditReport.is_deleted.is_(False),
            ).order_by(ValidationAuditReport.version.desc())
        )
        return result.scalars().first()

    async def create(self, report: ValidationAuditReport) -> ValidationAuditReport:
        self.session.add(report)
        await self.session.flush()
        result = await self.session.execute(
            select(ValidationAuditReport).where(
                ValidationAuditReport.id == report.id,
            )
        )
        return result.scalar_one()


class ValidationAuditKnowledgeBaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[ValidationAuditKnowledgeBase]:
        result = await self.session.execute(
            select(ValidationAuditKnowledgeBase).where(
                ValidationAuditKnowledgeBase.is_deleted.is_(False),
            ).order_by(ValidationAuditKnowledgeBase.frequency.desc())
        )
        return list(result.scalars().all())

    async def create(self, entry: ValidationAuditKnowledgeBase) -> ValidationAuditKnowledgeBase:
        self.session.add(entry)
        await self.session.flush()
        result = await self.session.execute(
            select(ValidationAuditKnowledgeBase).where(
                ValidationAuditKnowledgeBase.id == entry.id,
            )
        )
        return result.scalar_one()
