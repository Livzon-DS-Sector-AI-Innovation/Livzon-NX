"""法规雷达来源站点配置。

站点清单以「你们飞书表格里的法规链接」为出发点派生：先做覆盖度最高、
栏目页稳定可解析的国家级站点；其余来源通过 standard_search 通道按标准号核查。

新增站点只需在此追加一条 SiteSpec（或在飞书设置页维护 list_url），
不改动抓取与比对逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SiteSpec:
    """一个来源站点的抓取配置。"""

    site_code: str
    site_name: str
    domain: str
    channel: str  # column | standard_search
    list_urls: tuple[str, ...] = ()
    # 文章 URL 模式（正则，匹配 path）；留空则不做模式过滤
    article_pattern: str = ""
    # 分页模板：{n} 为页码，从 1 开始
    page_template: str = "index_{n}.shtml"
    min_title_len: int = 8
    # 允许链接指向外站（如应急管理部法规页指向国家法律法规数据库）
    allow_external_links: bool = False
    # 栏目页由 JS 渲染，需用 Playwright 抓取
    render_js: bool = False
    # 栏目页所示日期的语义：publish=发布日期 / implement=实施日期
    # 标准库栏目通常展示实施日期，不能直接与表里的「颁布修订日期」比较
    date_semantics: str = "publish"
    # 是否启用（安全知识库仅跟踪安全类法规；环保类来源停用）
    enabled: bool = True
    # 部分站点证书链不全或需额外请求头
    ssl_verify: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)

    def paginate(self, base: str, n: int) -> str:
        return base.rstrip("/") + "/" + self.page_template.format(n=n)


# 常见政务站文章页形态：
#   /xxx/202411/t20241129_1097688.shtml   （多数部委站）
#   /art/2026/art_4d42101809834b6f.html   （市场监管总局等）
#   /gzk/gz/202112/t20211210_963767.shtml （生态环境部规章库）
DEFAULT_ARTICLE_PATTERN = r"(?:/t\d{8}_\d+\.s?html?|/art/\d{4}/art_[0-9a-f]+\.html?)"


SITE_SPECS: tuple[SiteSpec, ...] = (
    SiteSpec(
        site_code="mee_gzk",
        site_name="生态环境部·规章库",
        domain="www.mee.gov.cn",
        channel="column",
        list_urls=("https://www.mee.gov.cn/gzk/",),
        article_pattern=r"/gzk/[a-z]+/\d{6}/t\d{8}_\d+\.s?html?",
        # 安全知识库仅跟踪安全类法规，环保法规归环保模块（需要时改回 True）
        enabled=False,
    ),
    SiteSpec(
        site_code="mee_bz",
        site_name="生态环境部·标准库",
        domain="www.mee.gov.cn",
        channel="column",
        list_urls=("https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/",),
        article_pattern=r"/ywgz/fgbz/bz/\S*/t\d{8}_\d+\.s?html?",
        # 标准库栏目展示的是实施日期，不参与「已修订」日期比较
        date_semantics="implement",
        # 环保行业标准（HJ）归环保模块
        enabled=False,
    ),
    SiteSpec(
        site_code="mem_fg",
        site_name="应急管理部·法律法规",
        domain="www.mem.gov.cn",
        channel="column",
        list_urls=("https://www.mem.gov.cn/fw/flfgbz/fg/",),
        # 该栏目直接链向国家法律法规数据库（权威源），需放行跨站链接；
        # article_pattern 匹配的是 URL 的 path，故此处写 /detail
        article_pattern=r"(?:^/detail$|/t\d{8}_\d+\.s?html?)",
        allow_external_links=True,
    ),
    SiteSpec(
        site_code="mem_tzgg",
        site_name="应急管理部·通知公告",
        domain="www.mem.gov.cn",
        channel="column",
        list_urls=("https://www.mem.gov.cn/gk/tzgg/",),
        article_pattern=DEFAULT_ARTICLE_PATTERN,
    ),
    SiteSpec(
        site_code="samr_flfg",
        site_name="市场监管总局·法律法规",
        domain="www.samr.gov.cn",
        channel="column",
        list_urls=("https://www.samr.gov.cn/zw/flfg/",),
        article_pattern=DEFAULT_ARTICLE_PATTERN,
        render_js=True,
    ),
)

# 标准号核查通道（Playwright 渲染国标全文公开检索页）
STANDARD_SEARCH_SITE = SiteSpec(
    site_code="openstd_gb",
    site_name="国家标准全文公开系统",
    domain="openstd.samr.gov.cn",
    channel="standard_search",
)

SPECS_BY_CODE: dict[str, SiteSpec] = {s.site_code: s for s in SITE_SPECS}
SPECS_BY_CODE[STANDARD_SEARCH_SITE.site_code] = STANDARD_SEARCH_SITE


def get_spec(site_code: str) -> SiteSpec | None:
    return SPECS_BY_CODE.get(site_code)


def column_specs() -> tuple[SiteSpec, ...]:
    return tuple(
        s for s in SITE_SPECS if s.channel == "column" and s.enabled
    )
