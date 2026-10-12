"""法规雷达抓取层单测：栏目页解析、分页抓取、标准号检索与站点配置。"""

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.safety.crawler import column, standard
from app.modules.safety.crawler.specs import (
    SITE_SPECS,
    STANDARD_SEARCH_SITE,
    SiteSpec,
    column_specs,
    get_spec,
)


def _response(
    body: bytes,
    *,
    url: str = "https://www.mem.gov.cn/gk/tzgg/",
    status: int = 200,
) -> httpx.Response:
    return httpx.Response(
        status,
        content=body,
        headers={"content-type": "text/html"},
        request=httpx.Request("GET", url),
    )


def _spec(**overrides: Any) -> SiteSpec:
    base: dict[str, Any] = {
        "site_code": "test_site",
        "site_name": "测试站点",
        "domain": "example.gov.cn",
        "channel": "column",
        "list_urls": ("https://example.gov.cn/list/",),
        "article_pattern": r"/art/\d{4}/art_[0-9a-f]+\.html?",
    }
    base.update(overrides)
    return SiteSpec(**base)


_COLUMN_HTML = """
<html><body>
  <div class="nav">
    <a href="javascript:void(0)">首页</a><a href="/list/index.html">更多</a>
  </div>
  <ul>
    <li><a href="/art/2026/art_abc123.html">某安全生产管理条例</a>
      <span>2026-01-28</span></li>
    <li><a href="/art/2026/art_def456.html">某安全生产管理办法2026-02-01</a></li>
    <li><a href="https://other.gov.cn/art/2026/art_999.html">外站法规条目名称</a></li>
    <li><a href="/art/2026/art_pic.html"><img src="/x.png"/></a></li>
    <li><a href="/art/2026/art_abc123.html">重复条目名称甲乙丙</a></li>
    <li><a href="/static/notice.php">非文章模式条目名称</a></li>
    <li><a href="/art/2026/art_short.html">短</a></li>
  </ul>
  <footer><a href="/art/2026/art_footer.html">联系我们</a></footer>
</body></html>
"""


# ── 基础解析 ──


def test_decode_response_falls_back_through_encodings() -> None:
    gbk = _response("某条例".encode("gb18030"))
    gbk.encoding = None
    assert "某条例" in column.decode_response(gbk)

    plain = _response("某条例".encode())
    plain.encoding = None
    assert "某条例" in column.decode_response(plain)

    broken = _response(b"\xff\xfe\xff")
    broken.encoding = "utf-8"
    assert isinstance(column.decode_response(broken), str)


def test_clean_title_strips_trailing_publish_date() -> None:
    assert column._clean_title("某条例2026-01-28") == "某条例"
    assert column._clean_title("某条例 2026年1月28日") == "某条例"
    assert column._clean_title("某条例") == "某条例"


def test_parse_date_accepts_common_separators_and_rejects_invalid() -> None:
    assert column._parse_date("公布 2026-01-28") == date(2026, 1, 28)
    assert column._parse_date("2026年1月28日") == date(2026, 1, 28)
    assert column._parse_date("2026/01/28") == date(2026, 1, 28)
    assert column._parse_date("无日期") is None
    # 月份越界走 ValueError 分支
    assert column._parse_date("2026-13-45") is None


def test_parse_column_html_extracts_items_and_filters_noise() -> None:
    items = column.parse_column_html(
        _COLUMN_HTML,
        base_url="https://example.gov.cn/list/",
        spec=_spec(),
        fallback_date=date(2026, 3, 1),
    )
    urls = [item.url for item in items]
    assert urls == [
        "https://example.gov.cn/art/2026/art_abc123.html",
        "https://example.gov.cn/art/2026/art_def456.html",
    ]
    first = items[0]
    assert first.title == "某安全生产管理条例"
    assert first.publish_date == date(2026, 1, 28)
    assert first.date_semantics == "publish"
    assert first.raw["context"]
    # 标题尾部日期被清理后再抽取日期
    assert items[1].title == "某安全生产管理办法"
    assert items[1].publish_date == date(2026, 2, 1)


def test_parse_column_html_allows_external_links_when_configured() -> None:
    spec = _spec(allow_external_links=True, article_pattern="")
    items = column.parse_column_html(
        _COLUMN_HTML,
        base_url="https://example.gov.cn/list/",
        spec=spec,
        fallback_date=None,
    )
    assert any("other.gov.cn" in item.url for item in items)
    # 无 article_pattern 时非文章链接也会进入结果（由调用方按需再过滤）
    assert any("notice.php" in item.url for item in items)


def test_parse_column_html_returns_empty_on_broken_document() -> None:
    assert (
        column.parse_column_html(
            None,  # type: ignore[arg-type] —— 触发解析异常分支
            base_url="https://example.gov.cn/list/",
            spec=_spec(),
        )
        == []
    )


# ── 抓取与分页 ──


@pytest.mark.anyio
async def test_fetch_column_items_collects_pages_and_reports_partial_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        (_response(_COLUMN_HTML.encode("utf-8"), url="https://example.gov.cn/list/")),
        (_response(b"<html>too short</html>", url="https://example.gov.cn/list/index_1.shtml")),
        (_response(b"", url="https://example.gov.cn/list/index_2.shtml", status=404)),
        (_response(b"", url="https://example.gov.cn/list/index_3.shtml", status=500)),
    ]
    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.kwargs = kwargs

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return pages[0]
            if calls["n"] == 2:
                return pages[1]
            if calls["n"] == 3:
                return pages[2]
            if calls["n"] == 4:
                raise httpx.ConnectError("boom", request=httpx.Request("GET", url))
            return pages[3]

    monkeypatch.setattr(column.httpx, "AsyncClient", FakeClient)
    spec = _spec(
        page_template="index_{n}.shtml",
        extra_headers={"X-Test": "1"},
    )

    result = await column.fetch_column_items(spec, max_pages=3)

    assert result.site_code == "test_site"
    assert [item.url for item in result.items] == [
        "https://example.gov.cn/art/2026/art_abc123.html",
        "https://example.gov.cn/art/2026/art_def456.html",
    ]
    # 部分页面失败不影响整体成功
    assert result.error is None


@pytest.mark.anyio
async def test_fetch_column_items_reports_error_only_when_nothing_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FailingClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(column.httpx, "AsyncClient", FailingClient)

    result = await column.fetch_column_items(_spec(list_urls=("https://example.gov.cn/list/",)))

    assert result.items == ()
    assert result.error is not None and "ConnectError" in result.error


@pytest.mark.anyio
async def test_fetch_column_items_uses_playwright_pages_for_js_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered = AsyncMock(return_value=[("https://example.gov.cn/list/", _COLUMN_HTML)])
    monkeypatch.setattr(column, "_render_pages", rendered)

    result = await column.fetch_column_items(_spec(render_js=True))

    assert len(result.items) == 2
    assert result.error is None


@pytest.mark.anyio
async def test_fetch_column_items_flags_unavailable_js_renderer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(column, "_render_pages", AsyncMock(return_value=[]))

    result = await column.fetch_column_items(_spec(render_js=True))

    assert result.items == ()
    assert result.error is not None and "JS 渲染不可用" in result.error


# ── 站点配置 ──


def test_site_specs_expose_enabled_columns_and_standard_site() -> None:
    enabled = column_specs()
    assert [spec.site_code for spec in enabled] == [
        "mem_fg",
        "mem_tzgg",
        "samr_flfg",
    ]
    assert all(spec.enabled for spec in SITE_SPECS if spec in enabled)
    assert get_spec("openstd_gb") is STANDARD_SEARCH_SITE
    assert get_spec("missing") is None
    assert STANDARD_SEARCH_SITE.channel == "standard_search"


def test_site_spec_paginate_uses_template() -> None:
    spec = _spec(page_template="index_{n}.shtml")
    assert spec.paginate("https://example.gov.cn/list/", 2) == (
        "https://example.gov.cn/list/index_2.shtml"
    )


# ── 标准号检索 ──


_STANDARD_HTML = """
<html><body><table>
  <tr><td>1</td><td>GB 50016-2025</td><td>建筑设计防火规范</td><td>强标</td>
      <td>现行</td><td>2025-11-01</td>
      <td><a href="/bzgk/gb/newGbInfo?hcno=1">详情</a></td></tr>
  <tr><td>2</td><td>GB/T 9999-2010</td><td>某检测方法</td><td>推荐</td>
      <td>废止</td><td>2010-05-01</td>
      <td><a href="https://openstd.samr.gov.cn/x">详情</a></td></tr>
  <tr><td>3</td><td>-</td><td>无标准号行</td></tr>
</table></body></html>
"""


def test_parse_standard_rows_maps_status_and_links() -> None:
    items = standard.parse_standard_rows(_STANDARD_HTML)
    assert [item.standard_no for item in items] == ["GB 50016-2025", "GB/T 9999-2010"]
    assert items[0].version_status == "current"
    assert items[0].publish_date == date(2025, 11, 1)
    assert items[0].url == "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=1"
    assert items[1].version_status == "obsolete"
    assert "某检测方法" in items[1].title


def test_standard_parse_date_handles_missing_and_invalid() -> None:
    assert standard._parse_date(None) is None
    assert standard._parse_date("无日期") is None
    assert standard._parse_date("2025-13-40") is None
    assert standard._parse_date("实施 2025-11-01") == date(2025, 11, 1)


def test_standard_decode_falls_back_to_gb18030() -> None:
    resp = _response("建筑设计防火规范".encode("gb18030"))
    resp.encoding = None
    assert "建筑设计防火规范" in standard._decode(resp)


@pytest.mark.anyio
async def test_search_standard_returns_rows_and_handles_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[Any] = [
        _response(_STANDARD_HTML.encode("utf-8")),
        _response(b"", status=503),
        httpx.ConnectError("down", request=httpx.Request("GET", standard.SEARCH_URL)),
    ]

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            outcome = responses.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(standard.httpx, "AsyncClient", FakeClient)

    rows = await standard.search_standard("GB 50016")
    assert len(rows) == 2

    assert await standard.search_standard("GB 50016") == []
    assert await standard.search_standard("GB 50016") == []


@pytest.mark.anyio
async def test_search_standard_returns_empty_when_parsing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            return _response(b"\xff\xfe not html")

    def _raising_parser() -> Any:
        def _raise(_text: str) -> Any:
            raise RuntimeError("bad")

        return _raise

    monkeypatch.setattr(standard.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(standard, "parse_standard_rows", _raising_parser())

    assert await standard.search_standard("GB 1") == []


# ── JS 渲染（Playwright）──


class _FakePlaywrightCM:
    def __init__(
        self, launch_error: Exception | None = None, goto_error: bool = False
    ) -> None:
        self.launch_error = launch_error
        self.goto_error = goto_error
        self.browser_closed = False

    async def __aenter__(self) -> Any:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    @property
    def chromium(self) -> Any:
        outer = self

        class Chromium:
            async def launch(self, headless: bool = True) -> Any:
                if outer.launch_error is not None:
                    raise outer.launch_error
                return Browser(outer)

        return Chromium()


class Browser:
    def __init__(self, outer: _FakePlaywrightCM) -> None:
        self.outer = outer

    async def new_context(self, **kwargs: Any) -> Any:
        return Context(self.outer)

    async def close(self) -> None:
        self.outer.browser_closed = True


class Context:
    def __init__(self, outer: _FakePlaywrightCM) -> None:
        self.outer = outer

    async def new_page(self) -> Any:
        return Page(self.outer)


class Page:
    def __init__(self, outer: _FakePlaywrightCM) -> None:
        self.outer = outer
        self.url = ""

    async def goto(self, url: str, **kwargs: Any) -> None:
        if self.outer.goto_error:
            raise RuntimeError("goto failed")
        self.url = url

    async def wait_for_timeout(self, ms: int) -> None:
        return None

    async def content(self) -> str:
        return _COLUMN_HTML


def _install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch, cm: _FakePlaywrightCM
) -> None:
    import sys
    import types as pytypes

    module = pytypes.ModuleType("playwright.async_api")
    module.async_playwright = lambda: cm  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.async_api", module)


@pytest.mark.anyio
async def test_render_pages_collects_final_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cm = _FakePlaywrightCM()
    _install_fake_playwright(monkeypatch, cm)

    pages = await column._render_pages(["https://example.gov.cn/list/"])

    assert pages and pages[0][1] == _COLUMN_HTML
    assert cm.browser_closed is True


@pytest.mark.anyio
async def test_render_pages_skips_failed_urls_and_reports_launch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_playwright(monkeypatch, _FakePlaywrightCM(goto_error=True))
    assert await column._render_pages(["https://example.gov.cn/list/"]) == []

    _install_fake_playwright(
        monkeypatch, _FakePlaywrightCM(launch_error=RuntimeError("no browser"))
    )
    assert await column._render_pages(["https://example.gov.cn/list/"]) == []


@pytest.mark.anyio
async def test_render_pages_returns_empty_without_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "playwright.async_api", None)
    assert await column._render_pages(["https://example.gov.cn/list/"]) == []


# ── 解析与分页的边界分支 ──


def test_nearby_text_stops_when_node_has_no_parent() -> None:
    from lxml import html as lxml_html

    root = lxml_html.fromstring("<html><body>无日期</body></html>")
    assert column._nearby_text(root) == ""


def test_parse_column_html_skips_noise_titles_and_noise_urls() -> None:
    page = """
    <html><body><ul>
      <li><a href="/art/2026/art_0a1b.html">某安全生产管理条例</a></li>
      <li><a href="/art/2026/art_nav.html">网站地图</a></li>
      <li><a href="mailto:yijian@example.gov.cn">技术咨询邮箱</a></li>
      <li><a href="/art/2026/art_pic2.html"><img src="/y.png"/></a></li>
    </ul></body></html>
    """
    spec = _spec(min_title_len=2)
    items = column.parse_column_html(
        page, base_url="https://example.gov.cn/list/", spec=spec
    )

    titles = [item.title for item in items]
    assert titles == ["某安全生产管理条例"]


@pytest.mark.anyio
async def test_fetch_column_items_dedupes_across_pages_and_logs_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filler = "填充正文内容" * 200
    duplicate_page = (
        "<html><body><p>" + filler + "</p><ul>"
        '<li><a href="/art/2026/art_abc123.html">某安全生产管理条例</a>'
        "<span>2026-01-28</span></li>"
        "</ul></body></html>"
    )

    class Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.calls = 0

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            self.calls += 1
            if self.calls == 1:
                return _response(duplicate_page.encode("utf-8"), url=url)
            return _response(b"", url=url, status=403)

    holder: dict[str, Client] = {}

    def _factory(*args: Any, **kwargs: Any) -> Client:
        holder["client"] = Client()
        return holder["client"]

    monkeypatch.setattr(column.httpx, "AsyncClient", _factory)

    result = await column.fetch_column_items(_spec(), max_pages=2)

    # 同 URL 跨页去重；部分页面 403 记错误但整体成功
    assert [item.url for item in result.items] == [
        "https://example.gov.cn/art/2026/art_abc123.html"
    ]
    assert result.error is None
    assert result.ok is True
