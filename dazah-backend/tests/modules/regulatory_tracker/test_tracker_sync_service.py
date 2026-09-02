"""Tests for regulatory tracker site registry and sync service."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.regulatory_tracker import repository as repo
from app.modules.regulatory_tracker.crawler.adapters.domestic import CdeCrawlerAdapter
from app.modules.regulatory_tracker.crawler.site_registry import (
    SITE_REGISTRY,
    create_site_adapter,
    get_site_registry_entry,
)
from app.modules.regulatory_tracker.crawler.types import (
    BaseRegulationCrawlerAdapter,
    CrawledRegulationRecord,
)
from app.modules.regulatory_tracker.models import (
    DataChannel,
    DataSource,
    RegulatoryDocument,
)
from app.modules.regulatory_tracker.services.site_target_service import (
    DEFAULT_SITE_TARGET_SPECS,
    ensure_default_site_targets,
)
from app.modules.regulatory_tracker.services.summary_backfill_service import (
    backfill_document_summaries,
)
from app.modules.regulatory_tracker.services.tracker_sync_service import (
    TrackerSyncService,
)

EXPECTED_SITE_CODES = {
    "nmpa",
    "cde",
    "cfdi",
    "moa",
    "ivdc",
    "fda",
    "ema",
    "edqm",
    "eurlex",
    "ich",
    "who",
}

REFERENCE_DATE = date(2026, 7, 14)


class StaticAdapter(BaseRegulationCrawlerAdapter):
    site_code = "test"
    site_name = "Test Adapter"

    def __init__(self, records: list[CrawledRegulationRecord]) -> None:
        self._records = records

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        return self._records


def test_site_registry_contains_all_expected_sites() -> None:
    assert set(SITE_REGISTRY) == EXPECTED_SITE_CODES


@pytest.mark.parametrize("site_code", sorted(EXPECTED_SITE_CODES))
def test_site_registry_entries_match_adapter_contract(site_code: str) -> None:
    entry = get_site_registry_entry(site_code)
    adapter = create_site_adapter(site_code)

    assert entry.site_code == site_code
    assert entry.site_name
    assert isinstance(adapter, BaseRegulationCrawlerAdapter)
    assert adapter.site_code == site_code
    assert adapter.site_name == entry.site_name


@pytest.mark.parametrize(
    "site_code",
    sorted(EXPECTED_SITE_CODES - {"cde", "cfdi", "ema", "fda", "ich", "moa", "ivdc"}),
)
def test_site_registry_placeholder_adapters_return_empty_list(site_code: str) -> None:
    adapter = create_site_adapter(site_code)

    assert asyncio.run(adapter.fetch_recent_documents()) == []


def test_site_registry_unknown_site_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_site_registry_entry("unknown")


@pytest.mark.anyio
async def test_cde_crawler_adapter_maps_normalized_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_record = {
        "zdyzIdCODE": "abc123",
        "title": "化学原料药质量控制指导原则",
        "issueDate": "20260714",
        "fclass": "化学药品",
        "nowstate": "现行有效",
    }
    normalized_record = {
        "document_id": "abc123",
        "title": "化学原料药质量控制指导原则",
        "publish_date": date(2026, 7, 14),
        "original_url": "https://www.cde.org.cn/zdyz/domesticinfopage?zdyzIdCODE=abc123",
        "status_text": "现行有效",
        "classification": "化学药品",
        "raw_data": raw_record,
    }

    class FakeCdeDomesticGuidelineAdapter:
        def __init__(self, *, headless: bool) -> None:
            self.headless = headless

        async def __aenter__(self) -> FakeCdeDomesticGuidelineAdapter:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def sync_pages(
            self, start_page: int = 1, end_page: int = 1
        ) -> list[dict[str, object]]:
            assert start_page == 1
            assert end_page == 1
            return [
                {
                    "page_num": 1,
                    "records": [raw_record],
                    "success": True,
                    "error": None,
                }
            ]

        @staticmethod
        def normalize_record(record: dict[str, object]) -> dict[str, object]:
            assert record == raw_record
            return normalized_record

    monkeypatch.setattr(
        "app.modules.regulatory_tracker.crawler.adapters.domestic.CdeDomesticGuidelineAdapter",
        FakeCdeDomesticGuidelineAdapter,
    )

    adapter = CdeCrawlerAdapter(headless=False, max_pages=1)
    records = await adapter.fetch_recent_documents()

    assert records == [
        CrawledRegulationRecord(
            source_site="cde",
            document_id="abc123",
            title="化学原料药质量控制指导原则",
            original_url="https://www.cde.org.cn/zdyz/domesticinfopage?zdyzIdCODE=abc123",
            publish_date=date(2026, 7, 14),
            effective_date=None,
            version=None,
            summary=None,
            raw_data={
                "zdyzIdCODE": "abc123",
                "title": "化学原料药质量控制指导原则",
                "issueDate": "20260714",
                "fclass": "化学药品",
                "nowstate": "现行有效",
                "normalized_record": normalized_record,
            },
        )
    ]


@pytest.mark.anyio
async def test_run_site_upsert_counts_inserted_then_unchanged(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unique_suffix = uuid.uuid4().hex
    source = DataSource(
        id=uuid.uuid4(),
        code=f"TEST_CDE_{unique_suffix}",
        name="Test CDE Source",
        enabled=True,
    )
    channel = DataChannel(
        id=uuid.uuid4(),
        source_id=source.id,
        code=f"test_channel_{unique_suffix}",
        name="Test Channel",
        enabled=True,
    )

    record = CrawledRegulationRecord(
        source_site="cde",
        document_id=f"doc-{unique_suffix}",
        title=f"化学原料药质量控制指导原则-{unique_suffix}",
        original_url=f"https://www.cde.org.cn/main/news/viewInfoCommon/{unique_suffix}",
        publish_date=REFERENCE_DATE,
        summary="化学原料药近期法规要求",
        raw_data={"classification": "化学药品", "status_text": "发布"},
    )

    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.tracker_sync_service.create_site_adapter",
        lambda _site_code: StaticAdapter([record]),
    )
    seen_keys: set[tuple[str | None, str, date | None, str | None]] = set()
    upsert_calls: list[dict[str, object]] = []

    async def _fake_upsert(
        _db_session: AsyncSession,
        data: dict[str, object],
    ) -> repo.DocumentUpsertResult:
        key = (
            data.get("source_site_code"),
            data.get("title"),
            data.get("publish_date"),
            data.get("source_url"),
        )
        upsert_calls.append(data)
        if key in seen_keys:
            return repo.DocumentUpsertResult(
                document=SimpleNamespace(id=uuid.uuid4(), is_new=False),
                action="unchanged",
            )

        seen_keys.add(key)
        return repo.DocumentUpsertResult(
            document=SimpleNamespace(id=uuid.uuid4(), is_new=True),
            action="inserted",
        )

    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.tracker_sync_service.repo.upsert_document_by_unique_fields",
        _fake_upsert,
    )

    service = TrackerSyncService(
        db_session,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    first_result = await service.run_site("cde", source=source, channel=channel)
    assert first_result["totals"] == {
        "checked": 1,
        "accepted": 1,
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }
    assert len(first_result["changed_document_ids"]) == 1

    second_result = await service.run_site("cde", source=source, channel=channel)
    assert second_result["totals"] == {
        "checked": 1,
        "accepted": 1,
        "inserted": 0,
        "updated": 0,
        "unchanged": 1,
        "rejected": 0,
    }
    assert second_result["changed_document_ids"] == []
    assert len(upsert_calls) == 2
    assert upsert_calls[0]["source_site_code"] == "cde"
    assert upsert_calls[0]["source_url"] == record.original_url


@pytest.mark.anyio
async def test_run_all_sites_returns_zero_totals_for_empty_adapters(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.tracker_sync_service.create_site_adapter",
        lambda _site_code: StaticAdapter([]),
    )

    service = TrackerSyncService(
        db_session,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    result = await service.run_all_sites()

    assert result["totals"] == {
        "checked": 0,
        "accepted": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }
    assert len(result["sites"]) == len(SITE_REGISTRY)
    assert all(site_result["error"] is None for site_result in result["sites"])
    assert result["changed_document_ids"] == []


def test_derive_summary_text_falls_back_to_detail_content() -> None:
    record = CrawledRegulationRecord(
        source_site="cfdi",
        document_id="doc-summary",
        title="制药用水检查指南",
        original_url="https://cfdi.org.cn/cfdi/resource/news/16700.html",
        publish_date=REFERENCE_DATE,
        summary=None,
        raw_data={},
    )

    summary = TrackerSyncService._derive_summary_text(
        record,
        {
            "detail_content": (
                "制药用水检查指南。 为进一步规范制药用水系统检查要求，明确纯化水、注射用水"  # noqa: E501
                "和灭菌用水的设施设计、运行维护及偏差管理要点。"
            ),
        },
        "国家药品监督管理局食品药品审核查验中心",
    )

    assert summary == (
        "为进一步规范制药用水系统检查要求，明确纯化水、注射用水和灭菌用水的设施设计、运行维护及偏差管理要点"
    )


def test_derive_summary_text_returns_chinese_fallback_for_english_content() -> None:
    record = CrawledRegulationRecord(
        source_site="ema",
        document_id="doc-ema",
        title="Guidance on good manufacturing practice",
        original_url="https://www.ema.europa.eu/en/documents/guidance/test_en.pdf",
        publish_date=REFERENCE_DATE,
        summary="This guidance describes manufacturing expectations for active substances.",  # noqa: E501
        raw_data={},
    )

    summary = TrackerSyncService._derive_summary_text(
        record,
        {"classification": "Scientific guideline"},
        "European Medicines Agency",
    )

    assert summary == (
        "欧洲药品管理局发布的技术指导原则相关文件《Guidance on good manufacturing practice》"  # noqa: E501
        "，发布日期为2026-07-14，系统已完成抓取整理。"
    )


@pytest.mark.anyio
async def test_backfill_document_summaries_updates_english_international_summary(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unique_suffix = uuid.uuid4().hex
    source = DataSource(
        id=uuid.uuid4(),
        code=f"TEST_EMA_{unique_suffix}",
        name="Test EMA Source",
        enabled=True,
    )
    channel = DataChannel(
        id=uuid.uuid4(),
        source_id=source.id,
        code=f"test_ema_channel_{unique_suffix}",
        name="Test EMA Channel",
        enabled=True,
    )
    db_session.add(source)
    db_session.add(channel)
    await db_session.flush()

    document = await repo.create_document(
        db_session,
        {
            "source_id": source.id,
            "channel_id": channel.id,
            "document_id": f"ema-doc-{unique_suffix}",
            "title": "Guidance on good manufacturing practice",
            "publish_date": REFERENCE_DATE,
            "source_site_code": "ema",
            "source_site_name": "European Medicines Agency",
            "source_url": f"https://www.ema.europa.eu/en/documents/{unique_suffix}",
            "original_url": f"https://www.ema.europa.eu/en/documents/{unique_suffix}",
            "summary_text": "This page provides guidance on GMP expectations.",
            "raw_data": {"classification": "Scientific guideline"},
            "filter_status": "accepted",
            "filter_reason": "accepted",
        },
    )

    async def _fake_fetch_detail_payload(
        url: str, fallback_title: str = ""
    ) -> dict[str, object]:
        return {
            "detail_title": fallback_title,
            "detail_excerpt": "This guideline explains GMP implementation and inspection expectations.",  # noqa: E501
            "detail_content": (
                "This guideline explains GMP implementation requirements, inspection focus and "  # noqa: E501
                "quality system expectations for manufacturers."
            ),
            "detail_paragraphs": [
                "This guideline explains GMP implementation requirements and inspection focus.",  # noqa: E501
                "It also outlines quality system expectations for manufacturers.",
            ],
        }

    async def _fake_generate_short_summary(
        *,
        title: str,
        raw_data: dict[str, object],
        existing_summary: str | None = None,
    ) -> str:
        assert raw_data.get("detail_content")
        return "概述GMP实施要求、检查重点及生产企业质量体系要求。"

    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.summary_backfill_service.fetch_detail_payload",
        _fake_fetch_detail_payload,
    )
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.summary_backfill_service.generate_short_summary",
        _fake_generate_short_summary,
    )

    stats = await backfill_document_summaries(db_session, limit=50)
    refreshed = await repo.get_document_by_id(db_session, document.id)

    assert stats["updated"] >= 1
    assert refreshed is not None
    assert refreshed.summary_text == "概述GMP实施要求、检查重点及生产企业质量体系要求。"
    assert refreshed.raw_data["detail_content"] == (
        "This guideline explains GMP implementation requirements, inspection focus and "
        "quality system expectations for manufacturers."
    )


@pytest.mark.anyio
async def test_ensure_default_site_targets_bootstraps_all_sites_idempotently(
    db_session: AsyncSession,
) -> None:
    first_result = await ensure_default_site_targets(db_session)
    second_result = await ensure_default_site_targets(db_session)

    assert set(first_result.site_targets) == EXPECTED_SITE_CODES
    assert first_result.created_sources == len(EXPECTED_SITE_CODES)
    assert first_result.created_channels == len(EXPECTED_SITE_CODES)
    assert second_result.created_sources == 0
    assert second_result.created_channels == 0

    expected_source_codes = [
        spec.source_code for spec in DEFAULT_SITE_TARGET_SPECS.values()
    ]
    expected_channel_codes = [
        spec.channel_code for spec in DEFAULT_SITE_TARGET_SPECS.values()
    ]
    data_source_count = await db_session.scalar(
        select(func.count(DataSource.id)).where(
            DataSource.code.in_(expected_source_codes)
        )
    )
    data_channel_count = await db_session.scalar(
        select(func.count(DataChannel.id)).where(
            DataChannel.code.in_(expected_channel_codes)
        )
    )
    assert data_source_count == len(EXPECTED_SITE_CODES)
    assert data_channel_count == len(EXPECTED_SITE_CODES)

    cde_source, cde_channel = second_result.site_targets["cde"]
    assert cde_source.code == DEFAULT_SITE_TARGET_SPECS["cde"].source_code
    assert cde_channel.code == DEFAULT_SITE_TARGET_SPECS["cde"].channel_code


class HangAdapter(BaseRegulationCrawlerAdapter):
    """模拟外部站点挂起（永远不返回）。"""

    site_code = "hang"
    site_name = "Hang Adapter"

    async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
        await asyncio.sleep(3600)
        return []


@pytest.mark.anyio
async def test_run_all_sites_concurrent_timeout_isolates_hanging_site(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单站超时只影响自己：挂起站返回 error，其余站正常汇总。"""
    # 缩短单站硬超时，避免测试真实等待 180s
    import app.modules.regulatory_tracker.services.tracker_sync_service as tss

    monkeypatch.setattr(tss, "SITE_SYNC_TIMEOUT_SECONDS", 1)

    def _adapter_factory(site_code: str) -> BaseRegulationCrawlerAdapter:
        if site_code == "moa":
            return HangAdapter()
        return StaticAdapter([])

    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.tracker_sync_service.create_site_adapter",
        _adapter_factory,
    )

    service = TrackerSyncService(db_session, recent_days=2)
    result = await service.run_all_sites()

    assert len(result["sites"]) == len(SITE_REGISTRY)
    by_code = {site["site_code"]: site for site in result["sites"]}
    assert "超时" in (by_code["moa"]["error"] or "")
    others = {code: site for code, site in by_code.items() if code != "moa"}
    assert all(site["error"] is None for site in others.values())
    # 挂起站未产生任何计数，其他空站也不产生；totals 全零但结构完整
    assert result["totals"] == {
        "checked": 0,
        "accepted": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }
    assert result["changed_document_ids"] == []


@pytest.mark.anyio
async def test_run_all_sites_runs_sites_concurrently(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """所有站点可并行完成（gather 聚合），且每站结果结构完整。"""
    started: list[str] = []

    class TrackingAdapter(BaseRegulationCrawlerAdapter):
        site_code = "track"
        site_name = "Tracking Adapter"

        async def fetch_recent_documents(self) -> list[CrawledRegulationRecord]:
            started.append(self.site_code)
            await asyncio.sleep(0.05)
            return []

    def _make_tracking_adapter(site_code: str) -> BaseRegulationCrawlerAdapter:
        return TrackingAdapter()

    monkeypatch.setattr(
        "app.modules.regulatory_tracker.services.tracker_sync_service.create_site_adapter",
        _make_tracking_adapter,
    )

    service = TrackerSyncService(db_session, recent_days=2)
    result = await service.run_all_sites()

    assert len(result["sites"]) == len(SITE_REGISTRY)
    assert len(started) == len(SITE_REGISTRY)
    assert all(site["error"] is None for site in result["sites"])
    # 0.05s/站 × 11 站串行需 0.55s，并发下明显更快；这里只断言全部站点完成
    assert result["changed_document_ids"] == []


def _build_upsert_payload(
    *,
    source: DataSource,
    channel: DataChannel,
    document_id: str,
    title: str,
    publish_date: date,
    url: str,
    site_code: str = "ema",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": source.id,
        "channel_id": channel.id,
        "document_id": document_id,
        "title": title,
        "publish_date": publish_date,
        "source_site_code": site_code,
        "source_site_name": "European Medicines Agency",
        "source_url": url,
        "original_url": url,
        "filter_status": "accepted",
        "filter_reason": "window",
        "status_text": None,
        "classification": None,
        "version_text": None,
        "effective_date": None,
        "summary_text": "summary",
        "capture_date": REFERENCE_DATE,
        "is_new": True,
        "raw_data": {},
    }
    payload["content_hash"] = repo.build_document_content_hash(payload)
    return payload


@pytest.mark.anyio
async def test_upsert_business_key_miss_falls_back_to_unique_key(
    db_session: AsyncSession,
) -> None:
    """EMA 更新型记录：publish_date 变化导致业务键 miss 时，按唯一键兜底更新而非重复插入。"""  # noqa: E501
    unique_suffix = uuid.uuid4().hex
    source = DataSource(
        id=uuid.uuid4(),
        code=f"TEST_EMA_{unique_suffix}",
        name="Test EMA Source",
        enabled=True,
    )
    channel = DataChannel(
        id=uuid.uuid4(),
        source_id=source.id,
        code=f"test_ema_channel_{unique_suffix}",
        name="Test EMA Channel",
        enabled=True,
    )
    db_session.add_all([source, channel])
    await db_session.flush()

    document_id = f"ema:{unique_suffix}"
    title = f"Guidance on GMP questions and answers {unique_suffix}"
    url = f"https://www.ema.europa.eu/en/documents/{unique_suffix}"

    first = await repo.upsert_document_by_unique_fields(
        db_session,
        _build_upsert_payload(
            source=source,
            channel=channel,
            document_id=document_id,
            title=title,
            publish_date=date(2026, 7, 10),
            url=url,
        ),
    )
    assert first.action == "inserted"

    # 同 document_id/标题/URL，但 last_updated_date 更新（publish_date 变化）
    second = await repo.upsert_document_by_unique_fields(
        db_session,
        _build_upsert_payload(
            source=source,
            channel=channel,
            document_id=document_id,
            title=title,
            publish_date=date(2026, 8, 1),
            url=url,
        ),
    )
    assert second.action == "updated"

    count = (
        await db_session.execute(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.source_id == source.id,
                RegulatoryDocument.channel_id == channel.id,
            )
        )
    ).scalar() or 0
    assert count == 1  # 未产生重复行


@pytest.mark.anyio
async def test_upsert_revives_soft_deleted_row_holding_unique_key(
    db_session: AsyncSession,
) -> None:
    """软删行仍占用唯一约束：upsert 应复活它而不是重复插入。"""
    unique_suffix = uuid.uuid4().hex
    source = DataSource(
        id=uuid.uuid4(),
        code=f"TEST_EMA2_{unique_suffix}",
        name="Test EMA Source 2",
        enabled=True,
    )
    channel = DataChannel(
        id=uuid.uuid4(),
        source_id=source.id,
        code=f"test_ema2_channel_{unique_suffix}",
        name="Test EMA Channel 2",
        enabled=True,
    )
    db_session.add_all([source, channel])
    await db_session.flush()

    document_id = f"ema2:{unique_suffix}"
    title = f"EMA guideline update {unique_suffix}"
    url = f"https://www.ema.europa.eu/en/documents/{unique_suffix}"

    first = await repo.upsert_document_by_unique_fields(
        db_session,
        _build_upsert_payload(
            source=source,
            channel=channel,
            document_id=document_id,
            title=title,
            publish_date=date(2026, 7, 10),
            url=url,
        ),
    )
    assert first.action == "inserted"

    # 模拟历史清理：软删该行，但唯一约束仍被占用
    stored = await repo.get_document_by_source_channel_document_id(
        db_session,
        source_id=source.id,
        channel_id=channel.id,
        document_id=document_id,
    )
    assert stored is not None
    stored.is_deleted = True
    await db_session.flush()

    # publish_date 变化（业务键 miss）+ 软删占用唯一键 → 应复活并更新
    revived = await repo.upsert_document_by_unique_fields(
        db_session,
        _build_upsert_payload(
            source=source,
            channel=channel,
            document_id=document_id,
            title=title,
            publish_date=date(2026, 8, 1),
            url=url,
        ),
    )
    assert revived.action in {"updated", "unchanged"}

    count = (
        await db_session.execute(
            select(func.count(RegulatoryDocument.id)).where(
                RegulatoryDocument.source_id == source.id,
                RegulatoryDocument.channel_id == channel.id,
            )
        )
    ).scalar() or 0
    assert count == 1
    refreshed = await repo.get_document_by_source_channel_document_id(
        db_session,
        source_id=source.id,
        channel_id=channel.id,
        document_id=document_id,
    )
    assert refreshed is not None
    assert refreshed.is_deleted is False
    assert refreshed.publish_date == date(2026, 8, 1)
