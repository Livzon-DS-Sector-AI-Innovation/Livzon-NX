"""Adapter exports for regulatory tracker crawler registry."""

from app.modules.regulatory_tracker.crawler.adapters.domestic import (
    DOMESTIC_SITE_ADAPTERS,
    CdeCrawlerAdapter,
    CfdiCrawlerAdapter,
    IvdcCrawlerAdapter,
    MoaCrawlerAdapter,
    NmpaCrawlerAdapter,
)
from app.modules.regulatory_tracker.crawler.adapters.international import (
    INTERNATIONAL_SITE_ADAPTERS,
    EdqmCrawlerAdapter,
    EmaCrawlerAdapter,
    EurlexCrawlerAdapter,
    FdaCrawlerAdapter,
    IchCrawlerAdapter,
    WhoCrawlerAdapter,
)

__all__ = [
    "CdeCrawlerAdapter",
    "CfdiCrawlerAdapter",
    "DOMESTIC_SITE_ADAPTERS",
    "EdqmCrawlerAdapter",
    "EmaCrawlerAdapter",
    "EurlexCrawlerAdapter",
    "FdaCrawlerAdapter",
    "INTERNATIONAL_SITE_ADAPTERS",
    "IchCrawlerAdapter",
    "IvdcCrawlerAdapter",
    "MoaCrawlerAdapter",
    "NmpaCrawlerAdapter",
    "WhoCrawlerAdapter",
]
