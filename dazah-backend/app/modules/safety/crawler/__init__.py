"""EHS 法规雷达抓取层。

按来源站点抓取法规栏目页/标准库，产出统一的法规条目，供比对层使用。
"""

from app.modules.safety.crawler.column import fetch_column_items
from app.modules.safety.crawler.specs import (
    SITE_SPECS,
    SiteSpec,
    column_specs,
    get_spec,
)
from app.modules.safety.crawler.standard import search_standard
from app.modules.safety.crawler.types import CrawledRegulation

__all__ = [
    "CrawledRegulation",
    "SITE_SPECS",
    "SiteSpec",
    "column_specs",
    "fetch_column_items",
    "get_spec",
    "search_standard",
]
