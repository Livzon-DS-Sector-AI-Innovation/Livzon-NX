from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer
from sqlalchemy.sql.elements import ColumnElement

from app.platform.system.feedback_models import FeedbackScreenshot, UserFeedback
from app.platform.system.feedback_schemas import FeedbackStatus


class FeedbackRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(
        self, feedback_id: UUID, owner_id: UUID | None = None, *, lock: bool = False
    ) -> UserFeedback | None:
        stmt = select(UserFeedback).where(
            UserFeedback.id == feedback_id, UserFeedback.is_deleted.is_(False)
        )
        if owner_id is not None:
            stmt = stmt.where(UserFeedback.created_by == owner_id)
        if lock:
            stmt = stmt.with_for_update()
        result = await self.db.execute(
            stmt.options(selectinload(UserFeedback.screenshots)).execution_options(
                populate_existing=True
            )
        )
        return result.scalar_one_or_none()

    async def insert(
        self, record: UserFeedback, images: list[tuple[bytes, str]]
    ) -> None:
        self.db.add(record)
        await self.db.flush()
        for content, content_type in images:
            self.db.add(
                FeedbackScreenshot(
                    feedback_id=record.id,
                    content_type=content_type,
                    content=content,
                    created_by=record.created_by,
                    updated_by=record.updated_by,
                )
            )
        await self.db.flush()

    async def list(
        self,
        owner_id: UUID | None,
        status: FeedbackStatus | None,
        page: int,
        page_size: int,
    ) -> tuple[list[UserFeedback], int, int]:
        conditions: list[ColumnElement[bool]] = [UserFeedback.is_deleted.is_(False)]
        if owner_id is not None:
            conditions.append(UserFeedback.created_by == owner_id)
        pending = await self.db.scalar(
            select(func.count())
            .select_from(UserFeedback)
            .where(*conditions, UserFeedback.status == "pending")
        )
        if status:
            conditions.append(UserFeedback.status == status)
        total = await self.db.scalar(
            select(func.count()).select_from(UserFeedback).where(*conditions)
        )
        result = await self.db.execute(
            select(UserFeedback)
            .where(*conditions)
            .options(selectinload(UserFeedback.screenshots))
            .order_by(UserFeedback.created_at.desc(), UserFeedback.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars()), total or 0, pending or 0

    async def screenshot(
        self, feedback_id: UUID, screenshot_id: UUID
    ) -> FeedbackScreenshot | None:
        result = await self.db.execute(
            select(FeedbackScreenshot)
            .where(
                FeedbackScreenshot.id == screenshot_id,
                FeedbackScreenshot.feedback_id == feedback_id,
                FeedbackScreenshot.is_deleted.is_(False),
            )
            .options(undefer(FeedbackScreenshot.content))
        )
        return result.scalar_one_or_none()
