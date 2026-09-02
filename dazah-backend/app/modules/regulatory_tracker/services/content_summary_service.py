"""Detail-content extraction and short summary generation for regulatory tracker."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx
from lxml import html  # type: ignore[import-untyped]

from app.core.llm import llm_client

logger = logging.getLogger(__name__)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}
DEFAULT_HTTP_TIMEOUT = 20.0
PLACEHOLDER_SUMMARY_MARKERS = (
    "系统已完成抓取整理",
    "概述gmp实施要求",
    "检查重点及生产企业质量体系要求",
    "inspection focus and quality system expectations",
    "this guideline explains gmp implementation",
)


def contains_cjk(text: str | None) -> bool:
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def normalize_summary_length(text: str, *, max_length: int = 100) -> str:
    normalized = re.sub(r"\s+", " ", text).strip(" ，,。；;：:")
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].rstrip(" ，,。；;：:") + "。"


def looks_like_placeholder_summary(text: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in PLACEHOLDER_SUMMARY_MARKERS)


def extract_detail_payload_from_html(
    page_html: str, *, fallback_title: str = ""
) -> dict[str, Any]:
    document = html.fromstring(page_html)
    meta_description = _extract_meta_description(document)
    detail_title = (
        _clean_text(document.xpath("string(//h1[1])"))
        or _clean_text(document.xpath("string(//title[1])"))
        or fallback_title
    )
    detail_paragraphs = _extract_detail_paragraphs(document)
    detail_content = " ".join(detail_paragraphs[:8]).strip()
    if _looks_like_invalid_detail_page(detail_title, meta_description, detail_content):
        return {}
    excerpt_source = detail_content or meta_description
    detail_excerpt = (
        normalize_summary_length(excerpt_source, max_length=300)
        if excerpt_source
        else None
    )

    payload: dict[str, Any] = {
        "detail_title": detail_title or None,
        "detail_excerpt": detail_excerpt,
        "detail_content": detail_content or None,
        "detail_paragraphs": detail_paragraphs[:12],
    }
    if meta_description:
        payload["meta_description"] = meta_description
    return payload


async def fetch_detail_payload(url: str, *, fallback_title: str = "") -> dict[str, Any]:
    max_retries = 3
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
                        "429 Too Many Requests for %s, retrying in %ds (attempt %d/%d)",
                        url,
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return extract_detail_payload_from_html(
                    response.text, fallback_title=fallback_title
                )
        except httpx.HTTPStatusError as exc:
            logger.warning("Failed to fetch detail page %s: %s", url, exc)
            return {}
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
            logger.warning("Failed to fetch detail page %s: %s", url, exc)
            return {}
    logger.warning(
        "Failed to fetch detail page %s: 429 after %d retries", url, max_retries
    )
    return {}


async def generate_short_summary(
    *,
    title: str,
    raw_data: dict[str, Any],
    existing_summary: str | None = None,
) -> str | None:
    source_text = _build_source_text(raw_data, existing_summary)
    if not source_text:
        return None

    if contains_cjk(source_text):
        summary = summarize_cjk_text(source_text, title=title, max_length=100)
        return None if looks_like_placeholder_summary(summary) else summary

    messages = [
        {
            "role": "system",
            "content": "你是制药法规信息摘要助手，负责把网页正文概括成简明中文。",
        },
        {
            "role": "user",
            "content": (
                "请根据下面的网页正文内容，输出一条中文内容总结。\n"
                "要求：\n"
                "1. 必须基于正文内容本身，不要写“某机构发布”“系统抓取整理”等套话；\n"
                "2. 直接概括该文件讲了什么、适用于什么、重点要求什么；\n"
                "3. 不超过100个中文字符；\n"
                '4. 只返回 JSON，格式为 {"summary": "..."}。\n\n'
                f"标题：{title}\n"
                f"正文：{source_text[:2400]}"
            ),
        },
    ]

    try:
        result = await llm_client.chat_json(
            messages, expected_keys=["summary"], temperature=0.2
        )
    except Exception as exc:
        logger.warning("Failed to generate summary via LLM for %s: %s", title, exc)
        summary = summarize_english_text(source_text, title=title, max_length=100)
        return None if looks_like_placeholder_summary(summary) else summary

    summary = result.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        fallback_summary = summarize_english_text(
            source_text, title=title, max_length=100
        )
        return (
            None
            if looks_like_placeholder_summary(fallback_summary)
            else fallback_summary
        )
    if not contains_cjk(summary):
        fallback_summary = summarize_english_text(
            source_text, title=title, max_length=100
        )
        return (
            None
            if looks_like_placeholder_summary(fallback_summary)
            else fallback_summary
        )

    normalized_summary = normalize_summary_length(summary, max_length=100)
    return (
        None
        if looks_like_placeholder_summary(normalized_summary)
        else normalized_summary
    )


def summarize_cjk_text(
    text: str, *, title: str = "", max_length: int = 100
) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None

    if title and title in normalized:
        normalized = normalized.replace(title, "", 1).strip(" ：:，,。")

    normalized = re.sub(r"^发布时间[:：]?\s*\S+\s*", "", normalized)
    normalized = re.sub(r"^本文件(主要)?(?:用于|适用于)", "适用于", normalized)
    normalized = re.sub(r"^本指导原则(主要)?(?:用于|适用于)", "适用于", normalized)
    normalized = re.sub(r"^该指导原则(主要)?(?:用于|适用于)", "适用于", normalized)

    sentences = re.split(r"[。；!！?？]", normalized)
    parts = [item.strip(" ，,;；") for item in sentences if item.strip(" ，,;；")]
    if not parts:
        return None

    candidate = "；".join(parts[:2])
    return normalize_summary_length(candidate, max_length=max_length)


def summarize_english_text(
    text: str, *, title: str = "", max_length: int = 100
) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None

    topic = _localize_english_title(title or normalized[:120])
    lowered = normalized.lower()
    key_points: list[str] = []
    keyword_rules = (
        (("gmp", "good manufacturing practice"), "明确GMP实施要求"),
        (("gdp", "good distribution practice"), "涵盖流通环节管理要求"),
        (("quality system", "quality management"), "提出质量体系要求"),
        (("inspection", "inspector"), "说明检查重点"),
        (("manufacturer", "manufacturers"), "适用于生产企业"),
        (("distributor", "distribution"), "涉及经营配送环节"),
        (
            ("pre-authorisation", "pre-authorisation guidance"),
            "概述上市前申报准备与资料提交要求",
        ),
        (("decentralised", "decentralized"), "涉及分散式试验要求"),
        (("pragmatic",), "涉及务实型试验要求"),
        (("real-world", "real world"), "纳入真实世界数据场景"),
        (("sponsor", "investigator"), "细化申办方与研究者职责"),
        (("annex 2",), "聚焦附件2新增要求"),
        (("antimicrobial resistance",), "聚焦抗菌药物耐药性管理"),
        (("veterinary",), "适用于兽药领域"),
        (("questions and answers", "q&a"), "以问答形式说明执行口径"),
    )
    for keywords, phrase in keyword_rules:
        if any(keyword in lowered for keyword in keywords) and phrase not in key_points:
            key_points.append(phrase)

    if not key_points:
        first_sentence = re.split(r"(?<=[.;])\s+", normalized)[0].strip()
        localized_sentence = _localize_english_title(first_sentence)
        if localized_sentence and localized_sentence != first_sentence:
            return normalize_summary_length(localized_sentence, max_length=max_length)
        return normalize_summary_length(topic, max_length=max_length)

    return normalize_summary_length(
        f"{topic}；{'；'.join(key_points[:3])}", max_length=max_length
    )


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _extract_meta_description(document: html.HtmlElement) -> str:
    for xpath in (
        "//meta[@name='description']/@content",
        "//meta[@property='og:description']/@content",
    ):
        values = document.xpath(xpath)
        if values:
            text = _clean_text(values[0])
            if text:
                return text
    return ""


def _extract_detail_paragraphs(document: html.HtmlElement) -> list[str]:
    paragraphs: list[str] = []
    seen: set[str] = set()
    selectors = (
        "//main//p",
        "//article//p",
        "//*[contains(@class, 'body')]//p",
        "//*[contains(@class, 'content')]//p",
        "//*[contains(@class, 'field--name-body')]//p",
        "//main//li",
        "//article//li",
    )

    for xpath in selectors:
        for node in document.xpath(xpath):
            text = _clean_text(node.text_content())
            if not text or text in seen:
                continue
            if len(text) < 30:
                continue
            if text.lower().startswith(("cookie", "copyright")):
                continue
            paragraphs.append(text)
            seen.add(text)

    if paragraphs:
        return paragraphs

    body_text = _clean_text(document.xpath("string(//body)"))
    if not body_text:
        return []

    fallback_parts = [
        item.strip()
        for item in re.split(r"(?<=[.;])\s+|\s{2,}", body_text)
        if item.strip() and len(item.strip()) >= 40
    ]
    deduped: list[str] = []
    for item in fallback_parts:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def _build_source_text(raw_data: dict[str, Any], existing_summary: str | None) -> str:
    parts: list[str] = []
    for key in (
        "detail_content",
        "detail_excerpt",
        "meta_description",
        "summary",
        "contentSummary",
    ):
        value = raw_data.get(key)
        if (
            isinstance(value, str)
            and value.strip()
            and not _looks_like_placeholder_text(value)
        ):
            parts.append(value.strip())

    detail_paragraphs = raw_data.get("detail_paragraphs")
    if isinstance(detail_paragraphs, list):
        parts.extend(
            item.strip()
            for item in detail_paragraphs
            if isinstance(item, str) and item.strip()
        )

    if (
        existing_summary
        and existing_summary.strip()
        and not looks_like_placeholder_summary(existing_summary)
    ):
        parts.append(existing_summary.strip())

    normalized_parts: list[str] = []
    seen: set[str] = set()
    for item in parts:
        if item not in seen:
            normalized_parts.append(item)
            seen.add(item)
    return " ".join(normalized_parts).strip()


def _localize_english_title(text: str) -> str:
    localized = text
    replacements = (
        ("Guidance on ", ""),
        ("guidance on ", ""),
        ("Questions and answers", "问答说明"),
        ("questions and answers", "问答说明"),
        ("Good manufacturing practice", "药品生产质量管理规范"),
        ("good manufacturing practice", "药品生产质量管理规范"),
        ("Good distribution practice", "药品经营质量管理规范"),
        ("good distribution practice", "药品经营质量管理规范"),
        (" and ", "及"),
        ("Pre-authorisation guidance", "上市前申报指导"),
        ("pre-authorisation guidance", "上市前申报指导"),
        ("Antimicrobial resistance in veterinary medicine", "兽药抗菌药物耐药性"),
        ("antimicrobial resistance in veterinary medicine", "兽药抗菌药物耐药性"),
        ("Good Clinical Practice", "药物临床试验质量管理规范"),
        ("good clinical practice", "药物临床试验质量管理规范"),
        ("Adopted and Published", "已发布"),
        ("adopted and published", "已发布"),
        ("Annex", "附件"),
        ("annex", "附件"),
    )
    for source, target in replacements:
        localized = localized.replace(source, target)

    localized = re.sub(r"\s+", " ", localized).strip(" ：:-")
    return localized


def _looks_like_invalid_detail_page(
    title: str, meta_description: str, detail_content: str
) -> bool:
    combined = " ".join(
        part for part in (title, meta_description, detail_content) if part
    ).lower()
    if not combined:
        return True
    return any(
        marker in combined
        for marker in (
            "server inaccessibility",
            "please try again later",
            "we apologise for any inconvenience",
            "we apologize for any inconvenience",
        )
    )


def _looks_like_placeholder_text(text: str) -> bool:
    return looks_like_placeholder_summary(text)
