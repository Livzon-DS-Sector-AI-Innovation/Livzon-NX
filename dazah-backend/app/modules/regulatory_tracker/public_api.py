"""Read-only regulatory document contract for consuming business modules."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository
from app.modules.regulatory_tracker.schemas.tracker_page import (
    TrackerLedgerItemRead,
    TrackerLedgerPageRead,
)


class RegulatoryDocumentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: str | None = Field(default=None, max_length=200)
    source_site: str | None = Field(default=None, max_length=100)
    publish_date_from: date | None = None
    publish_date_to: date | None = None
    capture_date_from: date | None = None
    capture_date_to: date | None = None
    status_text: str | None = Field(default=None, max_length=100)
    classification: str | None = Field(default=None, max_length=100)
    is_new: bool | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_date_ranges(self) -> Self:
        for start, end in (
            (self.publish_date_from, self.publish_date_to),
            (self.capture_date_from, self.capture_date_to),
        ):
            if start is not None and end is not None and start > end:
                raise ValueError("日期起始不能晚于结束")
        return self


async def list_regulatory_documents(
    db: AsyncSession, query: RegulatoryDocumentQuery
) -> TrackerLedgerPageRead:
    """Return stored ledger fields without crawling or generating AI analysis."""
    documents, total = await repository.get_documents_with_filters(
        db=db, **query.model_dump()
    )
    return TrackerLedgerPageRead(
        items=[TrackerLedgerItemRead.model_validate(doc) for doc in documents],
        total=total,
        page=query.page,
        page_size=query.page_size,
        total_pages=(total + query.page_size - 1) // query.page_size,
    )
