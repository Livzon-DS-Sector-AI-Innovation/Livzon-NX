"""Quality 共享分页/过滤辅助函数（Q1 拆分自 quality_management.py）。"""

from datetime import date, datetime, timedelta
from typing import Any


def _parse_date_filter(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _parse_datetime_filter(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_datetime_filter_end_exclusive(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value) + timedelta(days=1)


def _build_page_result(
    items: list[dict[str, Any]], total: int, page: int, page_size: int
) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
