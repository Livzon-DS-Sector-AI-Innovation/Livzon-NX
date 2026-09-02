"""Registry of supported regulatory crawler adapters."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.regulatory_tracker.crawler.adapters import (
    CdeCrawlerAdapter,
    CfdiCrawlerAdapter,
    EdqmCrawlerAdapter,
    EmaCrawlerAdapter,
    EurlexCrawlerAdapter,
    FdaCrawlerAdapter,
    IchCrawlerAdapter,
    IvdcCrawlerAdapter,
    MoaCrawlerAdapter,
    NmpaCrawlerAdapter,
    WhoCrawlerAdapter,
)
from app.modules.regulatory_tracker.crawler.types import BaseRegulationCrawlerAdapter


@dataclass(frozen=True, slots=True)
class SiteRegistryEntry:
    site_code: str
    site_name: str
    adapter_class: type[BaseRegulationCrawlerAdapter]


SITE_REGISTRY: dict[str, SiteRegistryEntry] = {
    "nmpa": SiteRegistryEntry("nmpa", NmpaCrawlerAdapter.site_name, NmpaCrawlerAdapter),
    "cde": SiteRegistryEntry("cde", CdeCrawlerAdapter.site_name, CdeCrawlerAdapter),
    "cfdi": SiteRegistryEntry("cfdi", CfdiCrawlerAdapter.site_name, CfdiCrawlerAdapter),
    "moa": SiteRegistryEntry("moa", MoaCrawlerAdapter.site_name, MoaCrawlerAdapter),
    "ivdc": SiteRegistryEntry("ivdc", IvdcCrawlerAdapter.site_name, IvdcCrawlerAdapter),
    "fda": SiteRegistryEntry("fda", FdaCrawlerAdapter.site_name, FdaCrawlerAdapter),
    "ema": SiteRegistryEntry("ema", EmaCrawlerAdapter.site_name, EmaCrawlerAdapter),
    "edqm": SiteRegistryEntry("edqm", EdqmCrawlerAdapter.site_name, EdqmCrawlerAdapter),
    "eurlex": SiteRegistryEntry(
        "eurlex", EurlexCrawlerAdapter.site_name, EurlexCrawlerAdapter
    ),
    "ich": SiteRegistryEntry("ich", IchCrawlerAdapter.site_name, IchCrawlerAdapter),
    "who": SiteRegistryEntry("who", WhoCrawlerAdapter.site_name, WhoCrawlerAdapter),
}


def get_site_registry_entry(site_code: str) -> SiteRegistryEntry:
    """Return site registry metadata for the given site code."""
    return SITE_REGISTRY[site_code]


def create_site_adapter(site_code: str) -> BaseRegulationCrawlerAdapter:
    """Instantiate the adapter registered for the given site code."""
    entry = get_site_registry_entry(site_code)
    return entry.adapter_class()
