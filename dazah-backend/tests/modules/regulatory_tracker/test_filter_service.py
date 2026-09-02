from __future__ import annotations

from datetime import date

from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord
from app.modules.regulatory_tracker.services.filter_service import filter_record

REFERENCE_DATE = date(2026, 7, 14)


def _build_record(
    *,
    title: str,
    original_url: str,
    publish_date: date,
    source_site: str = "cde",
    summary: str | None = None,
) -> CrawledRegulationRecord:
    return CrawledRegulationRecord(
        source_site=source_site,
        document_id="doc-001",
        title=title,
        original_url=original_url,
        publish_date=publish_date,
        summary=summary,
    )


def test_filter_record_rejects_excluded_topic() -> None:
    record = _build_record(
        title="化学药儿童用药指导原则",
        original_url="https://www.cde.org.cn/main/news/viewInfoCommon/123",
        publish_date=date(2026, 7, 14),
    )

    accepted, reason = filter_record(
        record,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason == "excluded_keyword:儿童用药"


def test_filter_record_accepts_recent_target_topic() -> None:
    record = _build_record(
        title="化学原料药质量控制指导原则",
        original_url="https://www.cde.org.cn/main/news/viewInfoCommon/456",
        publish_date=date(2026, 7, 13),
    )

    accepted, reason = filter_record(
        record,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is True
    assert reason == "accepted"


def test_filter_record_rejects_unofficial_url() -> None:
    record = _build_record(
        title="化学原料药质量控制指导原则",
        original_url="https://news.example.com/cde/456",
        publish_date=date(2026, 7, 14),
    )

    accepted, reason = filter_record(
        record,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason == "unofficial_url"


def test_filter_record_rejects_outdated_publish_date() -> None:
    record = _build_record(
        title="化学原料药质量控制指导原则",
        original_url="https://www.cde.org.cn/main/news/viewInfoCommon/789",
        publish_date=date(2026, 7, 11),
    )

    accepted, reason = filter_record(
        record,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason == "not_recent"


def test_filter_record_rejects_non_target_scope_when_no_target_keyword() -> None:
    record = _build_record(
        title="药品注册一般事项公告",
        original_url="https://www.cde.org.cn/main/news/viewInfoCommon/999",
        publish_date=date(2026, 7, 14),
    )

    accepted, reason = filter_record(
        record,
        recent_days=2,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason == "not_target_scope"


def test_filter_record_accepts_recent_english_guidance_topic() -> None:
    record = _build_record(
        title="API manufacturing quality guidance for drug substance",
        original_url="https://www.fda.gov/drugs/guidance-compliance-regulatory-information/api-guidance",
        publish_date=date(2026, 7, 14),
        source_site="fda",
    )

    accepted, reason = filter_record(
        record,
        recent_days=7,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is True
    assert reason == "accepted"


def test_filter_record_rejects_recent_english_excluded_topic() -> None:
    record = _build_record(
        title="Guidance for pediatric vaccine clinical trial design",
        original_url="https://www.fda.gov/vaccines-blood-biologics/guidance-compliance-regulatory-information/guidance",
        publish_date=date(2026, 7, 14),
        source_site="fda",
    )

    accepted, reason = filter_record(
        record,
        recent_days=7,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason in {
        "excluded_keyword:pediatric",
        "excluded_keyword:vaccine",
        "excluded_keyword:clinical trial",
    }


def test_filter_record_rejects_new_drug_topic_from_summary_content() -> None:
    record = _build_record(
        title="化学药品技术指导原则",
        original_url="https://www.cde.org.cn/main/news/viewInfoCommon/1001",
        publish_date=date(2026, 7, 14),
        summary="本文件适用于新药注册申报资料撰写要求。",
    )

    accepted, reason = filter_record(
        record,
        recent_days=7,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason == "excluded_keyword:新药"


def test_filter_record_rejects_excluded_topic_from_nested_raw_data_content() -> None:
    record = {
        "source_site": "ema",
        "title": "Guideline on active substance quality",
        "original_url": "https://www.ema.europa.eu/en/documents/scientific-guideline/test-guideline_en.pdf",
        "publish_date": REFERENCE_DATE,
        "summary": "Quality guidance for active substances.",
        "raw_data": {
            "classification": "Scientific guideline",
            "detail_sections": [
                {
                    "heading": "Scope",
                    "content": "This revision does not apply to biosimilar medicinal products.",  # noqa: E501
                }
            ],
        },
    }

    accepted, reason = filter_record(
        record,
        recent_days=7,
        reference_date=REFERENCE_DATE,
    )

    assert accepted is False
    assert reason == "excluded_keyword:biosimilar"
