"""International regulatory site adapters."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import html  # type: ignore[import-untyped]

from app.modules.regulatory_tracker.crawler.types import (
    CrawledRegulationRecord,
    EmptyRegulationCrawlerAdapter,
)
from app.modules.regulatory_tracker.services.content_summary_service import (
    fetch_detail_payload,
)

logger = logging.getLogger(__name__)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
DEFAULT_HTTP_TIMEOUT = 20.0


async def _fetch_with_retry(
    url: str, *, max_retries: int = 3, delay: float = 1.0
) -> httpx.Response | None:
    """带429重试的HTTP GET请求。"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                headers=DEFAULT_HTTP_HEADERS,
                timeout=DEFAULT_HTTP_TIMEOUT,
            ) as client:
                response = await client.get(url)
                if response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "429 Too Many Requests for %s, retry in %ds (attempt %d/%d)",
                        url,
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                return response
        except httpx.HTTPError as exc:
            if attempt < max_retries - 1:
                logger.warning(
                    "HTTP error for %s: %s, retrying (attempt %d/%d)",
                    url,
                    exc,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)
                continue
            logger.warning("HTTP error for %s: %s", url, exc)
            return None
    return None


class _JsonCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    async def _fetch_json(self, url: str, *, max_retries: int = 3) -> Any:
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    headers=DEFAULT_HTTP_HEADERS,
                    timeout=DEFAULT_HTTP_TIMEOUT,
                ) as client:
                    response = await client.get(url)
                    if response.status_code == 429:
                        wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                        logger.warning(
                            "429 Too Many Requests for %s, "
                "retrying in %ds (attempt %d/%d)",
                            url,
                            wait,
                            attempt + 1,
                            max_retries,
                        )
                        await asyncio.sleep(wait)
                        continue
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                if attempt < max_retries - 1:
                    logger.warning(
                        "HTTP error for %s: %s, retrying (attempt %d/%d)",
                        url,
                        exc,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(1)
                    continue
                raise
        return None


class FdaCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    site_code = "fda"
    site_name = "U.S. Food and Drug Administration"
    search_url = (
        "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"
    )

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        response = await _fetch_with_retry(self.search_url)
        if response is None or response.status_code >= 400:
            logger.warning("Failed to fetch %s guidance search page", self.site_code)
            return []

        return self._parse_search_page(response.text)

    def _parse_search_page(self, page_html: str) -> list[CrawledRegulationRecord]:
        document = html.fromstring(page_html)
        records: list[CrawledRegulationRecord] = []

        for row in document.xpath(
            "//table[.//th[contains(., 'Issue Date')]]//tbody/tr"
        ):
            cells = row.xpath("./td")
            if len(cells) < 6:
                continue

            summary_link = cells[0].xpath(".//a[@href][1]")
            summary_anchor = summary_link[0] if summary_link else None
            source_url = (
                urljoin(f"{self.search_url}/", summary_anchor.get("href", ""))
                if summary_anchor is not None
                else ""
            )
            title = _clean_text(
                summary_anchor.text_content() if summary_anchor is not None else ""
            )
            summary = _clean_text(cells[0].text_content()) or None
            publish_date = _parse_us_date_text(cells[2].text_content())
            organization = _clean_text(cells[3].text_content()) or None
            topic = _clean_text(cells[4].text_content()) or None
            status = _clean_text(cells[5].text_content()) or None
            if not title or not source_url or publish_date is None:
                continue

            if not self._is_relevant_item(title, summary, organization, topic):
                continue

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_build_document_id(self.site_code, source_url, title),
                    title=title,
                    original_url=source_url,
                    publish_date=publish_date,
                    effective_date=None,
                    version=_extract_revision(title),
                    summary=summary,
                    raw_data={
                        "classification": topic,
                        "detail_excerpt": summary,
                        "issuing_office": organization,
                        "topic": topic,
                        "status_text": status,
                    },
                )
            )

        return records

    @staticmethod
    def _is_relevant_item(
        title: str,
        summary: str | None,
        organization: str | None,
        topic: str | None,
    ) -> bool:
        combined_text = " ".join(
            part
            for part in (title, summary or "", organization or "", topic or "")
            if part
        ).lower()
        if not combined_text:
            return False

        if any(
            keyword in combined_text
            for keyword in (
                "medical device",
                "device",
                "tobacco",
                "food",
                "cosmetic",
                "radiation",
                "biologic",
                "pediatric",
                "oncology",
            )
        ):
            return False

        return any(
            keyword in combined_text
            for keyword in (
                "drug",
                "generic",
                "chemistry",
                "manufacturing",
                "bioequivalence",
                "guidance",
                "veterinary",
                "vich",
                "pharmacology",
                "quality",
                "anthelmintics",
            )
        )


class EmaCrawlerAdapter(_JsonCrawlerAdapter):
    site_code = "ema"
    site_name = "European Medicines Agency"
    general_report_url = (
        "https://www.ema.europa.eu/en/documents/report/general-json-report_en.json"
    )
    # 报告 JSON 含全部历史条目（实测 2000+），逐篇抓详情会拖垮整站抓取；
    # 只处理最近窗口内的条目，窗口外不再抓取
    candidate_window_days = 30

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        payload = await self._fetch_json(self.general_report_url)
        if not payload:
            return []
        records: list[CrawledRegulationRecord] = []

        cutoff = date.today() - timedelta(days=self.candidate_window_days)
        for item in payload.get("data", []):
            if not isinstance(item, dict):
                continue
            if not self._is_relevant_item(item):
                continue

            title = _clean_text(item.get("title"))
            source_url = _clean_text(item.get("general_url"))
            publish_date = _parse_date_text(
                item.get("last_updated_date")
            ) or _parse_date_text(item.get("first_published_date"))
            if publish_date is None or publish_date < cutoff:
                continue
            if not title or not source_url:
                continue

            summary = _clean_text(item.get("summary")) or None
            categories = _clean_text(item.get("categories")) or None
            first_published_date = _parse_date_text(item.get("first_published_date"))
            last_updated_date = _parse_date_text(item.get("last_updated_date"))
            # 列表接口自带摘要时不再抓详情页（详情仅用于补全内容，避免逐篇等待）
            if summary:
                detail_payload = {"detail_excerpt": summary}
            else:
                detail_payload = await fetch_detail_payload(
                    source_url, fallback_title=title
                )
            await asyncio.sleep(0.3)  # 防限流间隔

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_build_document_id(self.site_code, source_url, title),
                    title=title,
                    original_url=source_url,
                    publish_date=publish_date,
                    effective_date=None,
                    version=_extract_revision(title),
                    summary=summary,
                    raw_data={
                        "classification": categories,
                        "categories": categories,
                        "detail_excerpt": summary,
                        "first_published_date": (
                            first_published_date.isoformat()
                            if first_published_date
                            else None
                        ),
                        "last_updated_date": (
                            last_updated_date.isoformat() if last_updated_date else None
                        ),
                        "general_url": source_url,
                        **detail_payload,
                    },
                )
            )

        return records

    @classmethod
    def _is_relevant_item(cls, item: dict[str, Any]) -> bool:
        combined_text = " ".join(
            [
                _clean_text(item.get("title")),
                _clean_text(item.get("summary")),
                _clean_text(item.get("categories")),
                _clean_text(item.get("general_url")),
            ]
        ).lower()

        if not combined_text:
            return False

        if any(
            keyword in combined_text
            for keyword in ("medical-device", "device", "corporate")
        ):
            return False

        return any(
            keyword in combined_text
            for keyword in (
                "guideline",
                "guidance",
                "good manufacturing practice",
                "good distribution practice",
                "regulatory",
                "quality",
                "variation",
                "plasma master file",
                "active substance",
                "veterinary",
                "pharmacopoeia",
            )
        )


class EdqmCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    site_code = "edqm"
    site_name = "European Directorate for the Quality of Medicines & HealthCare"


class EurlexCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    site_code = "eurlex"
    site_name = "EUR-Lex"


class IchCrawlerAdapter(_JsonCrawlerAdapter):
    site_code = "ich"
    site_name = "International Council for Harmonisation"
    news_api_url = "https://admin.ich.org/api/v1/nodes?bundle=news&limit=100&sort=date:DESC,created:desc"
    public_base_url = "https://www.ich.org"

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        payload = await self._fetch_json(self.news_api_url)
        if not payload:
            return []
        records: list[CrawledRegulationRecord] = []

        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue

            bundle_info = item.get("bundleInfo")
            if not isinstance(bundle_info, dict):
                continue

            title = _clean_text(bundle_info.get("title"))
            alias = _clean_text(bundle_info.get("alias"))
            source_url = (
                urljoin(f"{self.public_base_url}/", alias.lstrip("/")) if alias else ""
            )
            summary = _clean_text(item.get("summary")) or None
            publish_date = _parse_iso_datetime(item.get("date")) or _parse_iso_datetime(
                bundle_info.get("updated")
            )
            if not title or not source_url or publish_date is None:
                continue

            if not self._is_relevant_item(title, summary):
                continue

            # 列表接口自带摘要时不再抓详情页（详情仅用于补全内容，避免逐篇等待）
            if summary:
                detail_payload = {"detail_excerpt": summary}
            else:
                detail_payload = await fetch_detail_payload(
                    source_url, fallback_title=title
                )
            await asyncio.sleep(0.3)  # 防限流间隔

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_clean_text(item.get("entityInfo", {}).get("id"))
                    or _build_document_id(self.site_code, source_url, title),
                    title=title,
                    original_url=source_url,
                    publish_date=publish_date,
                    effective_date=None,
                    version=_extract_ich_version(title),
                    summary=summary,
                    raw_data={
                        "classification": "ICH guideline news",
                        "detail_excerpt": summary,
                        "alias": alias,
                        "created_at": _clean_text(bundle_info.get("created")) or None,
                        "updated_at": _clean_text(bundle_info.get("updated")) or None,
                        "entity_uuid": _clean_text(
                            item.get("entityInfo", {}).get("uuid")
                        )
                        or None,
                        **detail_payload,
                    },
                )
            )

        return records

    @staticmethod
    def _is_relevant_item(title: str, summary: str | None) -> bool:
        combined_text = " ".join(
            part for part in (title, summary or "") if part
        ).lower()
        if not combined_text:
            return False

        if any(
            keyword in combined_text
            for keyword in ("assembly meeting", "management committee")
        ):
            return False

        return any(
            keyword in combined_text
            for keyword in (
                "guideline",
                "good clinical practice",
                "quality",
                "drug",
                "manufacturing",
                "harmonisation",
                "step 4",
                "revision",
                "briefing pack",
                "training module",
            )
        )


class WhoCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    site_code = "who"
    site_name = "World Health Organization"


INTERNATIONAL_SITE_ADAPTERS = (
    FdaCrawlerAdapter,
    EmaCrawlerAdapter,
    EdqmCrawlerAdapter,
    EurlexCrawlerAdapter,
    IchCrawlerAdapter,
    WhoCrawlerAdapter,
)


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _parse_date_text(value: Any) -> date | None:
    text = _clean_text(value)
    if not text:
        return None

    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_us_date_text(value: Any) -> date | None:
    text = _clean_text(value)
    if not text:
        return None

    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        return None


def _parse_iso_datetime(value: Any) -> date | None:
    text = _clean_text(value)
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


def _build_document_id(site_code: str, url: str, title: str) -> str:
    digest = hashlib.sha1(f"{url}|{title}".encode()).hexdigest()[:16]
    return f"{site_code}:{digest}"


def _extract_revision(title: str) -> str | None:
    match = re.search(r"\b(?:rev\.?\s*\d+|version\s*\d+)\b", title, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    return None


def _extract_ich_version(title: str) -> str | None:
    match = re.search(r"([A-Z]\d+(?:\([A-Z]?\d+\))?)", title)
    if match:
        return match.group(1)
    return _extract_revision(title)
