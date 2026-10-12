"""抓取层的统一数据契约。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# 标准号模式：GB/GB-T/AQ/AQ-T/HJ/HJ-T/TSG/WS/GBZ 等
STANDARD_NO_RE = re.compile(
    r"\b(GB\s*/?\s*T?\s*\d{3,5}(?:\.\d+)?\s*[-—]\s*\d{4}"
    r"|AQ\s*/?\s*T?\s*\d{3,5}(?:\.\d+)?\s*[-—]\s*\d{4}"
    r"|HJ\s*/?\s*T?\s*\d{3,5}(?:\.\d+)?\s*[-—]\s*\d{4}"
    r"|TSG\s*[A-Z]?\s*\d{2,4}(?:\s*[-—]\s*\d{4})?"
    r"|WS\s*/?\s*T?\s*\d{3,5}(?:\.\d+)?\s*[-—]\s*\d{4}"
    r"|GBZ\s*\d{2,4}(?:\.\d+)?\s*[-—]\s*\d{4}"
    r"|GB\s*\d{4,5}(?:\.\d+)?\s*[-—]\s*\d{4})\b",
    re.IGNORECASE,
)


def normalize_standard_no(text: str | None) -> str | None:
    """从标题中提取并规范化标准号（如 'GB/T 30871-2022' → 'GB/T 30871-2022'）。"""
    if not text:
        return None
    m = STANDARD_NO_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    raw = re.sub(r"\s*[-—]\s*", "-", raw)
    raw = re.sub(r"\s+", " ", raw).strip().upper()
    return raw or None


def core_name(title: str) -> str:
    """去掉标准号、书名号、版本年份等，得到用于名称匹配的核心串。"""
    s = STANDARD_NO_RE.sub("", title or "")
    s = re.sub(r"（\s*\d{4}\s*年?版?\s*）|\(\s*\d{4}\s*\)", "", s)
    s = re.sub(r"【.*?】", "", s)
    s = re.sub(r"[\s《》（）()〔〕\[\]、,，.。\-—_/·“”\"'　]", "", s)
    s = re.sub(r"^中华人民共和国|^国家|^中国|^国务院", "", s)
    return s


@dataclass(frozen=True, slots=True)
class CrawledRegulation:
    """抓取到的一条法规/标准条目。"""

    site_code: str
    site_name: str
    title: str
    url: str
    publish_date: date | None = None
    standard_no: str | None = None
    version_status: str | None = None
    # publish=日期为发布日期 / implement=为实施日期（后者不参与版本比较）
    date_semantics: str = "publish"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def core_name(self) -> str:
        return core_name(self.title)


@dataclass(frozen=True, slots=True)
class CrawlResult:
    """单个站点/栏目的抓取结果。"""

    site_code: str
    site_name: str
    items: tuple[CrawledRegulation, ...]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
