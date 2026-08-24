"""附件审阅业务逻辑（Q1 拆分自 quality_management.py）。"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.modules.quality.models import (
    AttachmentReview,
)
from app.modules.quality.schemas import (
    AttachmentReviewOut,
)

logger = logging.getLogger(__name__)


async def list_attachment_reviews(
    db: AsyncSession,
    deviation_id: uuid.UUID | None = None,
    capa_id: uuid.UUID | None = None,
    attachment_url: str | None = None,
) -> list[dict[str, Any]]:
    """List attachment reviews with optional filters."""
    query = select(AttachmentReview).where(AttachmentReview.is_deleted.is_(False))
    if deviation_id:
        query = query.where(AttachmentReview.deviation_id == deviation_id)
    if capa_id:
        query = query.where(AttachmentReview.capa_id == capa_id)
    if attachment_url:
        query = query.where(AttachmentReview.attachment_url == attachment_url)
    query = query.order_by(AttachmentReview.review_time.desc())

    result = await db.execute(query)
    items = result.scalars().all()
    return [AttachmentReviewOut.model_validate(item).model_dump() for item in items]


async def create_attachment_review(
    db: AsyncSession,
    data: Any,
    reviewer_id: str,
) -> dict[str, Any]:
    """Create a new attachment review."""
    review = AttachmentReview(
        deviation_id=data.deviation_id,
        capa_id=data.capa_id,
        attachment_url=data.attachment_url,
        content=data.content,
        reviewer_id=reviewer_id,
        review_time=datetime.now(UTC),
    )
    db.add(review)
    await db.flush()
    result = await db.execute(
        select(AttachmentReview).where(AttachmentReview.id == review.id)
    )
    review = result.scalar_one()
    return AttachmentReviewOut.model_validate(review).model_dump()


async def delete_attachment_review(db: AsyncSession, review_id: uuid.UUID) -> None:
    """Soft-delete an attachment review."""
    review = await db.get(AttachmentReview, review_id)
    if not review:
        raise NotFoundException(resource="附件审核")
    review.is_deleted = True
    await db.flush()
