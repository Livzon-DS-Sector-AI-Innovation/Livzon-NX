"""Shared crawler contracts for regulatory tracker adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar


@dataclass(slots=True, frozen=True)
class CrawledRegulationRecord:
    """Normalized crawler output for downstream ingestion."""

    source_site: str
    document_id: str
    title: str
    original_url: str
    publish_date: date | None = None
    effective_date: date | None = None
    version: str | None = None
    summary: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


class BaseRegulationCrawlerAdapter(ABC):
    """Base contract for all regulatory tracker crawler adapters."""

    site_code: ClassVar[str]
    site_name: ClassVar[str]

    @abstractmethod
    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        """Fetch recently published documents for a site."""


class EmptyRegulationCrawlerAdapter(BaseRegulationCrawlerAdapter):
    """Task 2 skeleton adapter that intentionally returns no records."""

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        return []
