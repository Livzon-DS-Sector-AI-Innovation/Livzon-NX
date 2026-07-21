"""Feishu Bitable field extraction utilities.

Standardizes reading of common Feishu field types across all datasources
and service modules.  Eliminates the copy-pasted private helpers that
were scattered across employee_datasource.py, candidate_datasource.py,
onboarding_datasource.py, departure_datasource.py, hr/service.py,
product/service.py, and scripts.
"""

from datetime import date, datetime, timezone
from typing import Any


def extract_text(value: Any) -> str:
    """Extract plain text from Feishu text-field array or object format."""
    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
        return value[0].get("text", "")
    if isinstance(value, dict):
        if "text" in value:
            return value.get("text", "")
        if "value" in value and isinstance(value["value"], list) and len(value["value"]) > 0:
            inner = value["value"][0]
            if isinstance(inner, dict) and "text" in inner:
                return inner.get("text", "")
            return str(inner)
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""


def extract_text_or_none(value: Any) -> str | None:
    """Extract text, returning None for empty/blank values."""
    text = extract_text(value)
    return text if text else None


def extract_number(value: Any) -> int | float | None:
    """Extract number from Feishu number/array format."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict) and "value" in value:
        v = value["value"]
        if isinstance(v, list) and len(v) > 0:
            return v[0]
    if isinstance(value, list) and len(value) > 0:
        return value[0]
    return None


def extract_single_select(value: Any) -> str:
    """Extract single-select option (plain string in Feishu)."""
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""


def extract_multi_select(value: Any) -> list[str]:
    """Extract multi-select options."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def extract_attachments(value: Any) -> list[dict]:
    """Extract attachment array from Feishu attachment field."""
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def extract_person_name(value: Any) -> str:
    """Extract person name from Feishu person field."""
    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
        names = [item.get("name", "") for item in value if isinstance(item, dict)]
        return ", ".join(n for n in names if n)
    return extract_text(value)


def extract_email(value: Any) -> str:
    """Extract email from Feishu URL/mailto format."""
    if isinstance(value, dict):
        if "text" in value:
            return value["text"]
        if "link" in value:
            link = value["link"]
            if isinstance(link, str) and link.startswith("mailto:"):
                return link[7:]
    return extract_text(value)


def ms_to_date(value: Any) -> date | None:
    """Convert Feishu millisecond timestamp to UTC-aware Python date."""
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()
    return None


def ms_to_datetime(value: Any) -> datetime | None:
    """Convert Feishu millisecond timestamp to UTC-aware Python datetime."""
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return None
