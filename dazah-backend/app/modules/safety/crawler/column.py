"""栏目页通用解析器。

政府网站栏目列表页结构各异，这里用「文章 URL 模式 + 标题长度 + 邻近日期」
三个启发式规则抽取条目，站点差异通过 SiteSpec 配置表达，不写死到解析逻辑里。
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html  # type: ignore[import-untyped]

from app.modules.safety.crawler.specs import SiteSpec
from app.modules.safety.crawler.types import (
    CrawledRegulation,
    CrawlResult,
    normalize_standard_no,
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = 30.0

# 日期：2026-01-28 / 2026年1月28日 / 2026/01/28
DATE_RE = re.compile(r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")
# 明显不是法规条目的标题（导航/页脚/功能入口）
NOISE_TITLE_RE = re.compile(
    r"^(更多|首页|上一页|下一页|返回|登录|注册|English|网站地图|联系我们"
    r"|版权声明|免责声明|京ICP|京公网|主办|承办|技术支持|关于我们"
    r"|政府网站找错|政务咨询|智能问答|无障碍|简体|繁體|邮箱)$"
)
NOISE_URL_RE = re.compile(
    r"(javascript:|mailto:|/index\.s?html?$|\.(?:jpg|jpeg|png|gif|css|js|ico)$)",
    re.IGNORECASE,
)


def decode_response(resp: httpx.Response) -> str:
    """按声明编码 → UTF-8 → GB18030 依次尝试解码（政府站常见 GBK）。"""
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


TRAILING_DATE_RE = re.compile(
    r"\s*20\d{2}\s*[-/年.]\s*\d{1,2}\s*[-/月.]\s*\d{1,2}\s*日?\s*$"
)


def _clean_title(title: str) -> str:
    """去掉标题尾部被一并抓进来的发布日期（如「…条例2025-11-21」）。"""
    return TRAILING_DATE_RE.sub("", title).strip()


def _parse_date(text: str) -> date | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _nearby_text(node: Any, levels: int = 3) -> str:
    """向上取若干层父节点的文本，用于抓取与链接同行的日期。"""
    parts: list[str] = []
    cur = node
    for _ in range(levels):
        cur = cur.getparent() if cur is not None else None
        if cur is None:
            break
        parts.append(" ".join(cur.text_content().split()))
        if DATE_RE.search(parts[-1]):
            break
    return " ".join(parts)


def parse_column_html(
    html_text: str,
    *,
    base_url: str,
    spec: SiteSpec,
    fallback_date: date | None = None,
) -> list[CrawledRegulation]:
    """从单个栏目页 HTML 中抽取法规条目。"""
    try:
        doc = html.fromstring(html_text)
    except Exception:  # noqa: BLE001 —— 页面结构异常时返回空而非中断整批
        logger.warning("栏目页解析失败: %s", base_url)
        return []

    article_re = re.compile(spec.article_pattern) if spec.article_pattern else None
    base_host = urlparse(base_url).netloc.lower()
    items: list[CrawledRegulation] = []
    seen: set[str] = set()

    for a in doc.xpath("//a[@href]"):
        title = _clean_title(" ".join((a.text_content() or "").split()))
        if len(title) < spec.min_title_len or not re.search(r"[\u4e00-\u9fff]", title):
            continue
        if NOISE_TITLE_RE.match(title):
            continue

        href = (a.get("href") or "").strip()
        if not href or NOISE_URL_RE.search(href):
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if url in seen:
            continue
        # 默认只收本站链接；允许跨站的栏目（如链向国家法律法规数据库）放行
        if parsed.netloc.lower() != base_host and not spec.allow_external_links:
            continue
        # 文章 URL 模式过滤：命中则视为条目
        if article_re and not article_re.search(parsed.path):
            continue

        seen.add(url)
        ctx = _nearby_text(a)
        pub = _parse_date(ctx) or fallback_date
        items.append(
            CrawledRegulation(
                site_code=spec.site_code,
                site_name=spec.site_name,
                title=title,
                url=url,
                publish_date=pub,
                standard_no=normalize_standard_no(title),
                date_semantics=spec.date_semantics,
                raw={"context": ctx[:200]},
            )
        )
    return items


async def _render_pages(urls: list[str]) -> list[tuple[str, str]]:
    """用 Playwright 渲染 JS 栏目页，返回 [(最终URL, HTML)]。

    浏览器不可用时返回空列表（调用方会记为抓取失败），不影响其他站点。
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright 未安装，无法渲染 JS 栏目页")
        return []

    out: list[tuple[str, str]] = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(
                    locale="zh-CN", user_agent=USER_AGENT
                )
                page = await ctx.new_page()
                for url in urls:
                    try:
                        await page.goto(
                            url, wait_until="domcontentloaded", timeout=45_000
                        )
                        await page.wait_for_timeout(2_500)
                        out.append((str(page.url), await page.content()))
                    except Exception as exc:  # noqa: BLE001
                        logger.info("渲染失败 %s: %s", url, exc)
            finally:
                await browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Playwright 启动失败: %s", exc)
    return out


async def fetch_column_items(
    spec: SiteSpec,
    *,
    max_pages: int = 3,
) -> CrawlResult:
    """抓取一个站点的栏目页（含分页），返回条目集合。

    单站失败不影响其他站点：异常被捕获并写入 CrawlResult.error。
    """
    collected: list[CrawledRegulation] = []
    seen: set[str] = set()
    errors: list[str] = []

    urls: list[str] = list(spec.list_urls)
    for base in spec.list_urls:
        for n in range(1, max_pages):
            urls.append(spec.paginate(base, n))

    pages: list[tuple[str, str]] = []
    if spec.render_js:
        pages = await _render_pages(urls)
        if not pages:
            errors.append("JS 渲染不可用（Playwright 缺失或启动失败）")
    else:
        headers = {**BASE_HEADERS, **(spec.extra_headers or {})}
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, verify=spec.ssl_verify, follow_redirects=True
        ) as client:
            for url in urls:
                try:
                    resp = await client.get(url, headers=headers)
                except Exception as exc:  # noqa: BLE001 —— 单页失败继续下一页
                    errors.append(f"{url}: {type(exc).__name__}")
                    continue
                if resp.status_code != 200:
                    if resp.status_code != 404:  # 分页越界常见 404，不算错误
                        errors.append(f"{url}: HTTP {resp.status_code}")
                    continue
                text = decode_response(resp)
                if len(text) < 500:
                    continue
                pages.append((str(resp.url), text))

    for final_url, text in pages:
        for item in parse_column_html(text, base_url=final_url, spec=spec):
            if item.url in seen:
                continue
            seen.add(item.url)
            collected.append(item)

    # 全部页面都失败才算失败；部分成功仍返回已抓到的条目
    error = None
    if not collected and errors:
        error = "; ".join(errors[:3])
    elif errors:
        logger.info("%s 部分页面抓取失败: %s", spec.site_name, errors[:2])

    return CrawlResult(
        site_code=spec.site_code,
        site_name=spec.site_name,
        items=tuple(collected),
        error=error,
    )
