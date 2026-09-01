"""Default site target bootstrap for regulatory tracker sync."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.crawler.cde_crawler import CDE_GUIDELINE_LIST_URL
from app.modules.regulatory_tracker.crawler.site_registry import (
    SITE_REGISTRY,
    get_site_registry_entry,
)
from app.modules.regulatory_tracker.models import DataChannel, DataSource


@dataclass(frozen=True, slots=True)
class DefaultSiteTargetSpec:
    site_code: str
    source_code: str
    channel_code: str
    list_url: str


@dataclass(frozen=True, slots=True)
class EnsureDefaultSiteTargetsResult:
    site_targets: dict[str, tuple[DataSource, DataChannel]]
    created_sources: int
    created_channels: int


DEFAULT_SITE_TARGET_SPECS: dict[str, DefaultSiteTargetSpec] = {
    "nmpa": DefaultSiteTargetSpec(
        site_code="nmpa",
        source_code="NMPA",
        channel_code="nmpa",
        list_url="https://www.nmpa.gov.cn/directory/web/nmpa/xxgk/fgwj/gzwj/gzwjyp/index.html",
    ),
    "cde": DefaultSiteTargetSpec(
        site_code="cde",
        source_code="CDE",
        channel_code="cde_domestic_guideline",
        list_url=CDE_GUIDELINE_LIST_URL,
    ),
    "cfdi": DefaultSiteTargetSpec(
        site_code="cfdi",
        source_code="CFDI",
        channel_code="cfdi",
        list_url="https://cfdi.org.cn/cfdi/index?module=A001&m1=11&m2=&nty=C03&tcode=C03B014",
    ),
    "moa": DefaultSiteTargetSpec(
        site_code="moa",
        source_code="MOA",
        channel_code="moa",
        list_url="https://xmsyj.moa.gov.cn/zwfw/",
    ),
    "ivdc": DefaultSiteTargetSpec(
        site_code="ivdc",
        source_code="IVDC",
        channel_code="ivdc",
        list_url="http://www.ivdc.org.cn/pszx/ywgz/zdyz/sjk/hxy/index.htm",
    ),
    "fda": DefaultSiteTargetSpec(
        site_code="fda",
        source_code="FDA",
        channel_code="fda",
        list_url="https://www.fda.gov/drugs/guidance-compliance-regulatory-information",
    ),
    "ema": DefaultSiteTargetSpec(
        site_code="ema",
        source_code="EMA",
        channel_code="ema",
        list_url="https://www.ema.europa.eu/en/human-regulatory-overview/research-development/scientific-guidelines",
    ),
    "edqm": DefaultSiteTargetSpec(
        site_code="edqm",
        source_code="EDQM",
        channel_code="edqm",
        list_url="https://www.edqm.eu/en/pharmacopoeia",
    ),
    "eurlex": DefaultSiteTargetSpec(
        site_code="eurlex",
        source_code="EURLEX",
        channel_code="eurlex",
        list_url="https://eur-lex.europa.eu/browse/directories/legislation.html",
    ),
    "ich": DefaultSiteTargetSpec(
        site_code="ich",
        source_code="ICH",
        channel_code="ich",
        list_url="https://www.ich.org/page/quality-guidelines",
    ),
    "who": DefaultSiteTargetSpec(
        site_code="who",
        source_code="WHO",
        channel_code="who",
        list_url="https://www.who.int/teams/health-product-and-policy-standards/standards-and-specifications",
    ),
}


def _build_base_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


async def ensure_default_site_targets(
    db: AsyncSession,
) -> EnsureDefaultSiteTargetsResult:
    """Ensure the default registry site sources and channels exist."""
    site_targets: dict[str, tuple[DataSource, DataChannel]] = {}
    created_sources = 0
    created_channels = 0

    for site_code in SITE_REGISTRY:
        spec = DEFAULT_SITE_TARGET_SPECS[site_code]
        entry = get_site_registry_entry(site_code)

        source = await repo.get_data_source_by_code(db, spec.source_code)
        if source is None:
            source = await repo.create_data_source(
                db,
                {
                    "code": spec.source_code,
                    "name": entry.site_name,
                    "base_url": _build_base_url(spec.list_url),
                    "enabled": True,
                },
            )
            created_sources += 1

        channel = await repo.get_channel_by_code(db, source.id, spec.channel_code)
        if channel is None:
            channel = await repo.create_data_channel(
                db,
                {
                    "source_id": source.id,
                    "code": spec.channel_code,
                    "name": f"{entry.site_name}主栏目",
                    "list_url": spec.list_url,
                    "adapter_name": SITE_REGISTRY[site_code].adapter_class.__name__,
                    "enabled": True,
                },
            )
            created_channels += 1

        site_targets[site_code] = (source, channel)

    return EnsureDefaultSiteTargetsResult(
        site_targets=site_targets,
        created_sources=created_sources,
        created_channels=created_channels,
    )


def build_site_target_summary(result: EnsureDefaultSiteTargetsResult) -> dict[str, Any]:
    """Serialize ensure_default_site_targets result for API responses."""
    return {
        "created_sources": result.created_sources,
        "created_channels": result.created_channels,
        "site_count": len(result.site_targets),
        "sites": sorted(result.site_targets),
    }
