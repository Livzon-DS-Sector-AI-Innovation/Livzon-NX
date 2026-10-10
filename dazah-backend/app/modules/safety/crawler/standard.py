"""国家标准全文公开系统：按标准号检索，返回现行/废止状态与日期。

这是「名称稳定、版本变化」的核心检测器：给定标准号（如 GB 30871-2022），
返回该标准的全部版本及状态（现行/废止）、发布日期。

该站检索结果由内层接口 ``/bzgk/std/std_list`` 提供（纯 HTML，httpx 可直接
抓取，无需浏览器）。检索不到的标准（如住建部管理的工程建设标准）返回空，
不影响其他通道。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from urllib.parse import urljoin

import httpx
from lxml import html  # type: ignore[import-untyped]

from app.modules.safety.crawler.specs import STANDARD_SEARCH_SITE
from app.modules.safety.crawler.types import CrawledRegulation

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
BASE_URL = "https://openstd.samr.gov.cn"
SEARCH_URL = f"{BASE_URL}/bzgk/std/std_list"
REQUEST_TIMEOUT = 30.0
DATE_RE = re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})")
STATUS_MAP = {"现行": "current", "即将实施": "current", "废止": "obsolete"}


def _decode(resp: httpx.Response) -> str:
    for enc in (resp.encoding, "utf-8", "gb18030"):
        if not enc:
            continue
        try:
            text = resp.content.decode(enc, errors="strict")
            if "\ufffd" not in text:
                return text
        except (LookupError, UnicodeDecodeError):
            continue
    return resp.content.decode("utf-8", errors="ignore")


def _parse_date(text: str | None) -> date | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_standard_rows(html_text: str) -> list[CrawledRegulation]:
    """解析检索结果表格（标准号/名称/状态/发布日期/详情链接）。"""
    doc = html.fromstring(html_text)
    items: list[CrawledRegulation] = []
    for tr in doc.xpath("//table//tr"):
        cells = [" ".join(td.text_content().split()) for td in tr.xpath("./td")]
        if len(cells) < 6:
            continue
        joined = " ".join(cells)
        no_m = re.search(
            r"\b(GB\s*/?\s*T?\s*\d{3,5}(?:\.\d+)?\s*-\s*\d{4})\b", joined, re.I
        )
        if not no_m:
            continue
        standard_no = re.sub(r"\s+", " ", no_m.group(1)).upper()
        status_raw = next((s for s in ("现行", "即将实施", "废止") if s in cells), "")
        # 标准名称：状态列之前最后一段含较长中文的单元格
        name = ""
        for cell in cells:
            if len(re.findall(r"[\u4e00-\u9fff]", cell)) >= 5 and cell not in (
                status_raw,
                "强标",
                "推荐",
            ):
                name = cell
        detail = ""
        for a in tr.xpath(".//a[@href]"):
            href = a.get("href") or ""
            if "newGbInfo" in href:
                detail = urljoin(BASE_URL, href) if href.startswith("/") else href
                break
        items.append(
            CrawledRegulation(
                site_code=STANDARD_SEARCH_SITE.site_code,
                site_name=STANDARD_SEARCH_SITE.site_name,
                title=f"{name or standard_no} {standard_no}".strip(),
                url=detail or f"https://openstd.samr.gov.cn/bzgk/gb/std_list?p.p2={standard_no}",
                publish_date=_parse_date(joined),
                standard_no=standard_no,
                version_status=STATUS_MAP.get(status_raw),
                raw={"status_raw": status_raw},
            )
        )
    return items


async def search_standard(standard_no: str) -> list[CrawledRegulation]:
    """按标准号检索国家标准（纯 httpx，无需浏览器）。失败返回空列表。"""
    keyword = re.sub(r"\s+", " ", standard_no).strip()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://openstd.samr.gov.cn/bzgk/gb/",
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, verify=False) as client:
            resp = await client.get(
                SEARCH_URL, params={"p.p1": "0", "p.p2": keyword}, headers=headers
            )
    except Exception as exc:  # noqa: BLE001 —— 检索失败不影响其他通道
        logger.warning("标准号检索失败 %s: %s", standard_no, exc)
        return []
    if resp.status_code != 200:
        logger.warning("标准号检索 HTTP %s: %s", resp.status_code, keyword)
        return []
    try:
        return parse_standard_rows(_decode(resp))
    except Exception as exc:  # noqa: BLE001
        logger.warning("标准号检索解析失败 %s: %s", standard_no, exc)
        return []
