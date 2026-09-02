"""Domestic regulatory site adapters."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html  # type: ignore[import-untyped]
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from app.modules.regulatory_tracker.crawler.cde_crawler import (
    CRAWLER_HEADLESS,
    CdeDomesticGuidelineAdapter,
)
from app.modules.regulatory_tracker.crawler.types import (
    CrawledRegulationRecord,
    EmptyRegulationCrawlerAdapter,
)

logger = logging.getLogger(__name__)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
DEFAULT_HTTP_TIMEOUT = 20.0


class NmpaCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    site_code = "nmpa"
    site_name = "国家药品监督管理局"

    list_url = (
        "https://www.nmpa.gov.cn/directory/web/nmpa/xxgk/fgwj/gzwj/gzwjyp/index.html"
    )
    default_max_pages = 2
    max_supported_pages = 2

    def __init__(self, *, max_pages: int | None = None) -> None:
        configured_max_pages = (
            self.default_max_pages if max_pages is None else max_pages
        )
        self.max_pages = max(1, min(configured_max_pages, self.max_supported_pages))

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        seen_urls: set[str] = set()
        records: list[CrawledRegulationRecord] = []

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=DEFAULT_HTTP_HEADERS,
            timeout=DEFAULT_HTTP_TIMEOUT,
        ) as client:
            for page_url in self._iter_page_urls():
                page_html = await self._fetch_html(client, page_url)
                if not page_html:
                    continue

                page_records = self._parse_list_page(page_html, page_url)
                for record in page_records:
                    if record.original_url in seen_urls:
                        continue
                    seen_urls.add(record.original_url)
                    records.append(record)

            if records:
                records = await self._enrich_records(client, records)

        return records

    def _iter_page_urls(self) -> list[str]:
        page_urls = [self.list_url]
        for page_number in range(2, self.max_pages + 1):
            page_urls.append(
                urljoin(
                    self.list_url,
                    f"index_{page_number - 1}.html",
                )
            )
        return page_urls

    def _parse_list_page(
        self,
        page_html: str,
        page_url: str,
    ) -> list[CrawledRegulationRecord]:
        document = html.fromstring(page_html)
        records: list[CrawledRegulationRecord] = []

        for anchor in document.xpath("//a[@href]"):
            href = urljoin(page_url, anchor.get("href", ""))
            if not _is_nmpa_drug_document_url(href):
                continue

            list_text = _clean_text(anchor.text_content())
            if not list_text:
                continue

            title = list_text
            publish_date = None

            next_text = _clean_text(
                anchor.xpath("string(following-sibling::text()[1])")
            )
            if next_text:
                publish_date = _parse_date_text(next_text)

            if publish_date is None:
                parent_text = _clean_text(anchor.xpath("string(..)"))
                publish_date = _parse_date_text(parent_text)

            if not title:
                continue

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_build_document_id(self.site_code, href, title),
                    title=title,
                    original_url=href,
                    publish_date=publish_date,
                    effective_date=None,
                    version=None,
                    summary=None,
                    raw_data={
                        "list_page_url": page_url,
                        "list_text": list_text,
                        "detail_url": href,
                    },
                )
            )

        return records

    async def _enrich_records(
        self,
        client: httpx.AsyncClient,
        records: list[CrawledRegulationRecord],
    ) -> list[CrawledRegulationRecord]:
        enriched_records: list[CrawledRegulationRecord] = []
        for record in records:
            detail_html = await self._fetch_html(client, record.original_url)
            await asyncio.sleep(1)  # 1秒间隔避免限流
            if not detail_html:
                enriched_records.append(record)
                continue

            detail_data = _parse_detail_page(
                detail_html,
                publish_date_label="发布时间",
                fallback_title=record.title,
            )
            raw_data = dict(record.raw_data)
            raw_data.update(detail_data["raw_data"])

            enriched_records.append(
                _copy_record(
                    record,
                    title=str(detail_data["title"] or record.title),
                    publish_date=record.publish_date or detail_data["publish_date"],
                    raw_data=raw_data,
                )
            )

        return enriched_records

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str | None:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                if response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "429 Too Many Requests for %s page %s, "
                    "retrying in %ds (attempt %d/%d)",
                        self.site_code,
                        url,
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as exc:
                status_code = (
                    exc.response.status_code if exc.response is not None else None
                )
                if status_code == 412:
                    logger.info(
                        "Falling back to Playwright for %s page %s", self.site_code, url
                    )
                    return await _fetch_html_with_playwright(url)
                logger.warning(
                    "Failed to fetch %s page %s: %s", self.site_code, url, exc
                )
                return None
            except httpx.HTTPError as exc:
                if attempt < max_retries - 1:
                    logger.warning(
                        "HTTP error for %s page %s: %s, retrying (attempt %d/%d)",
                        self.site_code,
                        url,
                        exc,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(1)
                    continue
                logger.warning(
                    "Failed to fetch %s page %s: %s", self.site_code, url, exc
                )
                return None
        return None


class CdeCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    site_code = "cde"
    site_name = "国家药品监督管理局药品审评中心"

    def __init__(
        self,
        *,
        headless: bool | None = None,
        max_pages: int | None = None,
    ) -> None:
        self.headless = CRAWLER_HEADLESS if headless is None else headless
        self.max_pages = self._resolve_max_pages(max_pages)

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        records: list[CrawledRegulationRecord] = []

        async with CdeDomesticGuidelineAdapter(headless=self.headless) as adapter:
            page_results = await adapter.sync_pages(
                start_page=1, end_page=self.max_pages
            )

        for page_result in page_results:
            if not page_result.get("success"):
                continue

            for raw_record in page_result.get("records", []):
                normalized_record = CdeDomesticGuidelineAdapter.normalize_record(
                    raw_record
                )
                records.append(self._to_crawled_record(normalized_record, raw_record))

        return records

    @staticmethod
    def _resolve_max_pages(max_pages: int | None) -> int:
        configured_max_pages = max_pages
        if configured_max_pages is None:
            raw_value = os.getenv("REGULATORY_TRACKER_CDE_MAX_PAGES", "1")
            try:
                configured_max_pages = int(raw_value)
            except ValueError:
                configured_max_pages = 1

        return max(1, min(configured_max_pages, 3))

    def _to_crawled_record(
        self,
        normalized_record: dict[str, Any],
        raw_record: dict[str, Any],
    ) -> CrawledRegulationRecord:
        raw_data = dict(raw_record)
        raw_data.setdefault("normalized_record", normalized_record)

        return CrawledRegulationRecord(
            source_site=self.site_code,
            document_id=str(normalized_record.get("document_id") or ""),
            title=str(normalized_record.get("title") or ""),
            original_url=str(normalized_record.get("original_url") or ""),
            publish_date=normalized_record.get("publish_date"),
            effective_date=normalized_record.get("effective_date"),
            version=normalized_record.get("version"),
            summary=normalized_record.get("summary"),
            raw_data=raw_data,
        )


class _HtmlListCrawlerAdapter(EmptyRegulationCrawlerAdapter):
    default_max_pages = 1
    max_supported_pages = 2

    def __init__(self, *, max_pages: int | None = None) -> None:
        configured_max_pages = (
            self.default_max_pages if max_pages is None else max_pages
        )
        self.max_pages = max(1, min(configured_max_pages, self.max_supported_pages))

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        seen_urls: set[str] = set()
        records: list[CrawledRegulationRecord] = []

        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=DEFAULT_HTTP_HEADERS,
            timeout=DEFAULT_HTTP_TIMEOUT,
        ) as client:
            for page_url in self._iter_page_urls():
                page_html = await self._fetch_html(client, page_url)
                if not page_html:
                    continue

                page_records = self._parse_list_page(page_html, page_url)
                for record in page_records:
                    if record.original_url in seen_urls:
                        continue
                    seen_urls.add(record.original_url)
                    records.append(record)

            if records:
                records = await self._enrich_records(client, records)

        return records

    def _iter_page_urls(self) -> list[str]:
        raise NotImplementedError

    def _parse_list_page(
        self,
        page_html: str,
        page_url: str,
    ) -> list[CrawledRegulationRecord]:
        raise NotImplementedError

    async def _enrich_records(
        self,
        client: httpx.AsyncClient,
        records: list[CrawledRegulationRecord],
    ) -> list[CrawledRegulationRecord]:
        return records

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str | None:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                if response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "429 Too Many Requests for %s page %s, "
                    "retrying in %ds (attempt %d/%d)",
                        self.site_code,
                        url,
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Failed to fetch %s page %s: %s", self.site_code, url, exc
                )
                return None
            except httpx.HTTPError as exc:
                if attempt < max_retries - 1:
                    logger.warning(
                        "HTTP error for %s page %s: %s, retrying (attempt %d/%d)",
                        self.site_code,
                        url,
                        exc,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(1)
                    continue
                logger.warning(
                    "Failed to fetch %s page %s: %s", self.site_code, url, exc
                )
                return None
        return None


class CfdiCrawlerAdapter(_HtmlListCrawlerAdapter):
    site_code = "cfdi"
    site_name = "国家药品监督管理局食品药品审核查验中心"
    list_url = (
        "https://cfdi.org.cn/cfdi/index?module=A001&m1=11&m2=&nty=C03&tcode=C03B014"
    )
    default_max_pages = 1
    max_supported_pages = 1

    def _iter_page_urls(self) -> list[str]:
        return [self.list_url]

    def _parse_list_page(
        self,
        page_html: str,
        page_url: str,
    ) -> list[CrawledRegulationRecord]:
        document = html.fromstring(page_html)
        records: list[CrawledRegulationRecord] = []

        for anchor in document.xpath("//a[@href]"):
            href = urljoin(page_url, anchor.get("href", ""))
            if not _is_cfdi_article_url(href):
                continue

            list_text = _clean_text(anchor.text_content())
            if not list_text:
                continue

            publish_date = _parse_date_text(list_text)
            title = _strip_trailing_date(list_text)
            if not title:
                continue

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_build_document_id(self.site_code, href, title),
                    title=title,
                    original_url=href,
                    publish_date=publish_date,
                    effective_date=None,
                    version=None,
                    summary=None,
                    raw_data={
                        "list_page_url": page_url,
                        "list_text": list_text,
                        "detail_url": href,
                    },
                )
            )

        return records

    async def _enrich_records(
        self,
        client: httpx.AsyncClient,
        records: list[CrawledRegulationRecord],
    ) -> list[CrawledRegulationRecord]:
        enriched_records: list[CrawledRegulationRecord] = []
        for record in records:
            detail_html = await self._fetch_html(client, record.original_url)
            await asyncio.sleep(1)  # 1秒间隔避免限流
            if not detail_html:
                enriched_records.append(record)
                continue

            detail_data = _parse_detail_page(
                detail_html,
                publish_date_label="发布时间",
                fallback_title=record.title,
            )
            raw_data = dict(record.raw_data)
            raw_data.update(detail_data["raw_data"])

            enriched_records.append(
                _copy_record(
                    record,
                    title=str(detail_data["title"] or record.title),
                    publish_date=record.publish_date or detail_data["publish_date"],
                    raw_data=raw_data,
                )
            )

        return enriched_records


class MoaCrawlerAdapter(_HtmlListCrawlerAdapter):
    site_code = "moa"
    site_name = "农业农村部"
    list_url = "https://xmsyj.moa.gov.cn/zwfw/"
    default_max_pages = 2
    max_supported_pages = 2

    def _iter_page_urls(self) -> list[str]:
        page_urls = [self.list_url]
        for page_number in range(2, self.max_pages + 1):
            page_urls.append(urljoin(self.list_url, f"index_{page_number - 1}.htm"))
        return page_urls

    def _parse_list_page(
        self,
        page_html: str,
        page_url: str,
    ) -> list[CrawledRegulationRecord]:
        document = html.fromstring(page_html)
        records: list[CrawledRegulationRecord] = []

        for anchor in document.xpath("//a[@href]"):
            href = urljoin(page_url, anchor.get("href", ""))
            if not _is_moa_announcement_url(href):
                continue

            list_text = _clean_text(anchor.text_content())
            if not list_text:
                continue

            publish_date = _parse_date_text(list_text)
            title = _strip_trailing_date(list_text)
            if not title:
                continue

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_build_document_id(self.site_code, href, title),
                    title=title,
                    original_url=href,
                    publish_date=publish_date,
                    effective_date=None,
                    version=None,
                    summary=None,
                    raw_data={
                        "list_page_url": page_url,
                        "list_text": list_text,
                        "detail_url": href,
                    },
                )
            )

        return records

    async def _enrich_records(
        self,
        client: httpx.AsyncClient,
        records: list[CrawledRegulationRecord],
    ) -> list[CrawledRegulationRecord]:
        enriched_records: list[CrawledRegulationRecord] = []
        for record in records:
            detail_html = await self._fetch_html(client, record.original_url)
            await asyncio.sleep(0.3)  # 防限流间隔
            if not detail_html:
                enriched_records.append(record)
                continue

            detail_data = _parse_detail_page(
                detail_html,
                publish_date_label="日期",
                fallback_title=record.title,
            )
            raw_data = dict(record.raw_data)
            raw_data.update(detail_data["raw_data"])

            enriched_records.append(
                _copy_record(
                    record,
                    title=str(detail_data["title"] or record.title),
                    publish_date=record.publish_date or detail_data["publish_date"],
                    raw_data=raw_data,
                )
            )

        return enriched_records


class IvdcCrawlerAdapter(_HtmlListCrawlerAdapter):
    site_code = "ivdc"
    site_name = "中国兽药信息网"
    list_url = "http://www.ivdc.org.cn/pszx/ywgz/zdyz/sjk/hxy/index.htm"
    default_max_pages = 2
    max_supported_pages = 2

    def _iter_page_urls(self) -> list[str]:
        page_urls = [self.list_url]
        for page_number in range(2, self.max_pages + 1):
            page_urls.append(urljoin(self.list_url, f"index_{page_number - 1}.htm"))
        return page_urls

    def _parse_list_page(
        self,
        page_html: str,
        page_url: str,
    ) -> list[CrawledRegulationRecord]:
        document = html.fromstring(page_html)
        records: list[CrawledRegulationRecord] = []

        for row in document.xpath("//table//tr[td]"):
            cells = row.xpath("./td")
            if len(cells) < 4:
                continue

            links = cells[1].xpath(".//a[@href]")
            if not links:
                continue

            link = links[0]
            href = urljoin(page_url, link.get("href", ""))
            if not _is_ivdc_guideline_url(href):
                continue

            title = _clean_text(link.text_content())
            if not title:
                continue

            version = _clean_text(cells[2].text_content()) or None
            publish_date = _parse_date_text(
                cells[3].text_content()
            ) or _parse_date_text(cells[1].text_content())

            records.append(
                CrawledRegulationRecord(
                    source_site=self.site_code,
                    document_id=_build_document_id(self.site_code, href, title),
                    title=title,
                    original_url=href,
                    publish_date=publish_date,
                    effective_date=None,
                    version=version,
                    summary=None,
                    raw_data={
                        "list_page_url": page_url,
                        "row_values": [
                            _clean_text(cell.text_content()) for cell in cells
                        ],
                        "detail_url": href,
                    },
                )
            )

        return records


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _strip_trailing_date(text: str) -> str:
    normalized = _clean_text(text)
    return _clean_text(
        re.sub(
            r"(?:\s*| )*(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日)$",
            "",
            normalized,
        )
    )


def _parse_date_text(text: str | None) -> date | None:
    normalized = _clean_text(text)
    if not normalized:
        return None

    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", normalized)
    if not match:
        match = re.search(r"(\d{4})(\d{2})(\d{2})", normalized)
    if not match:
        return None

    try:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return date(year, month, day)
    except ValueError:
        return None


def _build_document_id(site_code: str, url: str, title: str) -> str:
    parsed_url = urlparse(url)
    url_path = parsed_url.path or ""

    for pattern in (
        r"/news/(\d+)\.html$",
        r"/(\d+)\.html$",
        r"/t\d+_(\d+)\.htm$",
        r"/(P\d+)\.(?:doc|docx)$",
    ):
        match = re.search(pattern, url_path, flags=re.IGNORECASE)
        if match:
            return f"{site_code}:{match.group(1)}"

    digest = hashlib.sha1(f"{url}|{title}".encode()).hexdigest()[:16]
    return f"{site_code}:{digest}"


def _parse_detail_page(
    detail_html: str,
    *,
    publish_date_label: str,
    fallback_title: str,
) -> dict[str, Any]:
    document = html.fromstring(detail_html)
    full_text = _clean_text(" ".join(document.xpath("//body//text()")))
    detail_paragraphs = _extract_detail_paragraphs(document)
    title = _extract_detail_title(document) or fallback_title
    publish_date = _extract_labeled_date(
        full_text, publish_date_label
    ) or _parse_date_text(full_text)
    detail_content = " ".join(detail_paragraphs) if detail_paragraphs else full_text
    excerpt_source = detail_content or full_text
    excerpt = excerpt_source[:1000] if excerpt_source else None

    return {
        "title": title,
        "publish_date": publish_date,
        "raw_data": {
            "detail_title": title,
            "detail_excerpt": excerpt,
            "detail_content": detail_content[:4000] if detail_content else None,
            "detail_paragraphs": detail_paragraphs[:20],
        },
    }


def _extract_labeled_date(text: str, label: str) -> date | None:
    match = re.search(
        rf"{re.escape(label)}[:：]?\s*(\d{{4}}[-/年]\d{{1,2}}[-/月]\d{{1,2}}日?)",
        text,
    )
    if not match:
        return None
    return _parse_date_text(match.group(1))


def _extract_detail_paragraphs(document: html.HtmlElement) -> list[str]:
    paragraphs: list[str] = []
    seen: set[str] = set()

    for node in document.xpath(
        "//body//*[self::p or self::li or self::td or self::div]"
    ):
        text = _clean_text(node.text_content())
        if not text or text in seen:
            continue
        if text.startswith(("当前位置", "发布时间", "日期", "附件下载", "版权所有")):
            continue
        if len(text) < 12:
            continue
        paragraphs.append(text)
        seen.add(text)

    return paragraphs


def _extract_detail_title(document: html.HtmlElement) -> str:
    heading_title = (
        _clean_text(document.xpath("string(//h1[1])"))
        or _clean_text(document.xpath("string(//h2[1])"))
        or _clean_text(document.xpath("string(//h3[1])"))
        or _clean_text(document.xpath("string(//*[contains(@class, 'news-title')][1])"))
    )
    if heading_title:
        return heading_title

    for text_node in document.xpath("//body//text()"):
        candidate = _clean_text(text_node)
        if not candidate:
            continue
        if candidate in {"您的位置：", ">>"}:
            continue
        if candidate.startswith("当前位置"):
            continue
        if candidate.startswith("发布时间") or candidate.startswith("日期"):
            continue
        if candidate.startswith("版权所有") or candidate.startswith("附件下载"):
            continue
        if len(candidate) < 6:
            continue
        if not re.search(r"[\u4e00-\u9fff]", candidate):
            continue
        return candidate

    return ""


def _copy_record(
    record: CrawledRegulationRecord,
    *,
    title: str | None = None,
    publish_date: date | None = None,
    raw_data: dict[str, Any] | None = None,
) -> CrawledRegulationRecord:
    return CrawledRegulationRecord(
        source_site=record.source_site,
        document_id=record.document_id,
        title=title if title is not None else record.title,
        original_url=record.original_url,
        publish_date=publish_date if publish_date is not None else record.publish_date,
        effective_date=record.effective_date,
        version=record.version,
        summary=record.summary,
        raw_data=raw_data if raw_data is not None else dict(record.raw_data),
    )


async def _fetch_html_with_playwright(url: str) -> str | None:
    browser = None
    context = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=DEFAULT_HTTP_HEADERS["User-Agent"],
                locale="zh-CN",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
            content = await page.content()
            return content
    except PlaywrightError as exc:
        logger.warning("Playwright fallback fetch failed for %s: %s", url, exc)
        return None
    except Exception as exc:  # noqa: BLE001 - 浏览器启动失败等非 PlaywrightError 异常
        logger.warning("Playwright unexpected error for %s: %s", url, exc)
        return None
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:  # noqa: BLE001
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass


def _is_cfdi_article_url(url: str) -> bool:
    parsed_url = urlparse(url)
    host = (parsed_url.hostname or "").lower()
    if host != "cfdi.org.cn":
        return False
    return bool(re.search(r"/cfdi/resource/news/\d+\.html$", parsed_url.path))


def _is_nmpa_drug_document_url(url: str) -> bool:
    parsed_url = urlparse(url)
    host = (parsed_url.hostname or "").lower()
    if host != "www.nmpa.gov.cn":
        return False
    return bool(
        re.search(
            r"/directory/web/nmpa/xxgk/fgwj/gzwj/gzwjyp/\d+\.html$",
            parsed_url.path,
        )
    )


def _is_moa_announcement_url(url: str) -> bool:
    parsed_url = urlparse(url)
    host = (parsed_url.hostname or "").lower()
    if host != "xmsyj.moa.gov.cn":
        return False
    return bool(re.search(r"/zwfw/\d{6}/t\d{8}_\d+\.htm$", parsed_url.path))


def _is_ivdc_guideline_url(url: str) -> bool:
    parsed_url = urlparse(url)
    host = (parsed_url.hostname or "").lower()
    if host != "www.ivdc.org.cn":
        return False
    return bool(
        re.search(
            r"/pszx/ywgz/zdyz/sjk/hxy/\d{6}/P\d+\.(?:doc|docx)$",
            parsed_url.path,
            flags=re.IGNORECASE,
        )
    )


DOMESTIC_SITE_ADAPTERS = (
    NmpaCrawlerAdapter,
    CdeCrawlerAdapter,
    CfdiCrawlerAdapter,
    MoaCrawlerAdapter,
    IvdcCrawlerAdapter,
)
