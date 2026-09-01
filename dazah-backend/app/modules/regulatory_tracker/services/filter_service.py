"""Centralized filter rules for regulatory tracker crawler records."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord

EXCLUDED_KEYWORDS: tuple[str, ...] = (
    "医疗器械",
    "medical device",
    "medical devices",
    "中药",
    "traditional chinese medicine",
    "生物制品",
    "biologic",
    "biological",
    "抗肿瘤",
    "oncology",
    "anti-tumor",
    "儿童用药",
    "pediatric",
    "paediatric",
    "罕见病",
    "rare disease",
    "新药",
    "new drug",
    "创新药",
    "innovative drug",
    "novel drug",
    "生物类似药",
    "biosimilar",
    "临床试验",
    "clinical trial",
    "疫苗",
    "vaccine",
)

TARGET_KEYWORDS: tuple[str, ...] = (
    "化学",
    "原料药",
    "api",
    "active pharmaceutical ingredient",
    "兽药",
    "veterinary",
    "药典",
    "pharmacopoeia",
    "pharmacopeia",
    "指导原则",
    "guideline",
    "guidance",
    "drug master file",
    "drug substance",
    "excipient",
    "packaging material",
    "container closure",
    "quality",
    "chemistry manufacturing and controls",
)

OFFICIAL_SITE_DOMAINS: dict[str, tuple[str, ...]] = {
    "nmpa": ("nmpa.gov.cn",),
    "cde": ("cde.org.cn",),
    "cfdi": ("cfdi.org.cn", "cfdi.nmpa.gov.cn"),
    "moa": ("moa.gov.cn",),
    "ivdc": ("ivdc.org.cn",),
    "fda": ("fda.gov",),
    "ema": ("ema.europa.eu",),
    "edqm": ("edqm.eu",),
    "eurlex": ("eur-lex.europa.eu",),
    "ich": ("ich.org",),
    "who": ("who.int",),
}


def is_official_site_url(url: str | None, site_code: str | None = None) -> bool:
    """Return whether the given URL belongs to an official regulatory site."""
    if not url:
        return False

    try:
        host = urlparse(url).hostname
    except ValueError:
        return False

    if not host:
        return False

    normalized_host = host.lower()
    expected_domains = OFFICIAL_SITE_DOMAINS.get((site_code or "").lower())
    if expected_domains:
        return _host_matches_domains(normalized_host, expected_domains)

    return any(
        _host_matches_domains(normalized_host, domains)
        for domains in OFFICIAL_SITE_DOMAINS.values()
    )


def is_recent_publish_date(
    publish_date: date | None,
    recent_days: int,
    reference_date: date | None = None,
) -> bool:
    """Return whether the publish date falls within the recent-day window."""
    if publish_date is None or recent_days < 1:
        return False

    today = reference_date or date.today()
    earliest_date = today - timedelta(days=recent_days - 1)
    return earliest_date <= publish_date <= today


def filter_record(
    record: CrawledRegulationRecord | Mapping[str, Any],
    recent_days: int,
    reference_date: date | None = None,
) -> tuple[bool, str]:
    """Apply centralized filter rules to a crawled regulation record."""
    site_code = _get_record_value(record, "source_site") or _get_record_value(
        record, "source_site_code"
    )
    original_url = _get_record_value(record, "original_url") or _get_record_value(
        record, "source_url"
    )
    publish_date = _get_record_value(record, "publish_date")
    search_text = _build_search_text(record)

    if not is_official_site_url(original_url, site_code):
        return False, "unofficial_url"

    if not is_recent_publish_date(publish_date, recent_days, reference_date):
        return False, "not_recent"

    excluded_keyword = _find_keyword(search_text, EXCLUDED_KEYWORDS)
    if excluded_keyword is not None:
        return False, f"excluded_keyword:{excluded_keyword}"

    if _find_keyword(search_text, TARGET_KEYWORDS) is None:
        return False, "not_target_scope"

    return True, "accepted"


def _host_matches_domains(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _get_record_value(
    record: CrawledRegulationRecord | Mapping[str, Any],
    field_name: str,
) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _build_search_text(record: CrawledRegulationRecord | Mapping[str, Any]) -> str:
    values: list[str] = []
    for field_name in ("title", "classification", "summary"):
        value = _get_record_value(record, field_name)
        if isinstance(value, str) and value:
            values.append(value)

    raw_data = _get_record_value(record, "raw_data")
    if raw_data is not None:
        values.extend(_flatten_text_values(raw_data))

    return "\n".join(values).lower()


def _flatten_text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_text_values(item))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_text_values(item))
        return flattened
    return []


def _find_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if keyword.lower() in text:
            return keyword
    return None
