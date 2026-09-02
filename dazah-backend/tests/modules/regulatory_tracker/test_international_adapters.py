from __future__ import annotations

from datetime import date

import pytest

from app.modules.regulatory_tracker.crawler.adapters.international import (
    EmaCrawlerAdapter,
    FdaCrawlerAdapter,
    IchCrawlerAdapter,
)
from app.modules.regulatory_tracker.crawler.types import CrawledRegulationRecord


@pytest.mark.anyio
async def test_ema_adapter_maps_relevant_json_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "meta": {"total_records": 2},
        "data": [
            {
                "title": "Guidance on good manufacturing practice and good distribution practice: Questions and answers",
                "summary": "This page provides guidance on GMP and GDP expectations for human and veterinary medicines.",
                "categories": "Human;Veterinary",
                "first_published_date": "31/12/2009",
                "last_updated_date": "15/08/2026",
                "general_url": (
                    "https://www.ema.europa.eu/en/human-regulatory-overview/research-development/"
                    "compliance-research-development/good-manufacturing-practice/"
                    "guidance-good-manufacturing-practice-good-distribution-practice-questions-answers"
                ),
            },
            {
                "title": "Remote connection to EMA IT Systems",
                "summary": "Teleworking support.",
                "categories": "Corporate",
                "first_published_date": "24/09/2018",
                "last_updated_date": "13/07/2026",
                "general_url": "https://www.ema.europa.eu/en/remote-connection-ema-it-systems",
            },
        ],
    }

    async def _fake_fetch_json(self: EmaCrawlerAdapter, url: str) -> dict[str, object]:
        assert url == self.general_report_url
        return payload

    async def _fake_fetch_detail_payload(
        url: str, fallback_title: str = ""
    ) -> dict[str, object]:
        return {
            "detail_title": fallback_title,
            "detail_excerpt": "The guideline explains GMP and GDP implementation requirements.",
            "detail_content": (
                "The guideline explains GMP and GDP implementation requirements for manufacturers "
                "and distributors, including quality system expectations and inspection focus."
            ),
            "detail_paragraphs": [
                "The guideline explains GMP and GDP implementation requirements for manufacturers and distributors.",
                "It outlines quality system expectations and inspection focus.",
            ],
        }

    monkeypatch.setattr(EmaCrawlerAdapter, "_fetch_json", _fake_fetch_json)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.crawler.adapters.international.fetch_detail_payload",
        _fake_fetch_detail_payload,
    )

    adapter = EmaCrawlerAdapter()
    records = await adapter.fetch_recent_documents()

    assert records == [
        CrawledRegulationRecord(
            source_site="ema",
            document_id=records[0].document_id,
            title="Guidance on good manufacturing practice and good distribution practice: Questions and answers",
            original_url=(
                "https://www.ema.europa.eu/en/human-regulatory-overview/research-development/"
                "compliance-research-development/good-manufacturing-practice/"
                "guidance-good-manufacturing-practice-good-distribution-practice-questions-answers"
            ),
            publish_date=date(2026, 8, 15),
            effective_date=None,
            version=None,
            summary="This page provides guidance on GMP and GDP expectations for human and veterinary medicines.",
            raw_data={
                "classification": "Human;Veterinary",
                "categories": "Human;Veterinary",
                "detail_excerpt": (
                    "This page provides guidance on GMP and GDP expectations for human "
                    "and veterinary medicines."
                ),
                "first_published_date": "2009-12-31",
                "last_updated_date": "2026-08-15",
                "general_url": (
                    "https://www.ema.europa.eu/en/human-regulatory-overview/research-development/"
                    "compliance-research-development/good-manufacturing-practice/"
                    "guidance-good-manufacturing-practice-good-distribution-practice-questions-answers"
                ),
            },
        )
    ]


def test_fda_adapter_parses_recent_guidance_rows() -> None:
    adapter = FdaCrawlerAdapter()
    page_html = """
    <html>
      <body>
        <table>
          <thead>
            <tr>
              <th>Summary</th>
              <th>Document</th>
              <th>Issue Date</th>
              <th>FDA Organization</th>
              <th>Topic</th>
              <th>Guidance Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <a href="/regulatory-information/search-fda-guidance-documents/topical-dermatologic-corticosteroids-in-vivo-bioequivalence-0">
                  Topical Dermatologic Corticosteroids: In Vivo Bioequivalence
                </a>
                Recommendations for demonstrating bioequivalence of topical corticosteroids.
              </td>
              <td><a href="/media/162457/download">PDF</a></td>
              <td>07/14/2026</td>
              <td>Center for Drug Evaluation and Research</td>
              <td>Generic Drugs</td>
              <td>Final</td>
            </tr>
            <tr>
              <td>
                <a href="/regulatory-information/search-fda-guidance-documents/cybersecurity-medical-devices-quality-management-system-considerations-and-content-premarket">
                  Cybersecurity in Medical Devices
                </a>
                Device cybersecurity guidance.
              </td>
              <td><a href="/media/190742/download">PDF</a></td>
              <td>07/14/2026</td>
              <td>Center for Devices and Radiological Health</td>
              <td>Medical Devices</td>
              <td>Final</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    records = adapter._parse_search_page(page_html)

    assert records == [
        CrawledRegulationRecord(
            source_site="fda",
            document_id=records[0].document_id,
            title="Topical Dermatologic Corticosteroids: In Vivo Bioequivalence",
            original_url=(
                "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/"
                "topical-dermatologic-corticosteroids-in-vivo-bioequivalence-0"
            ),
            publish_date=date(2026, 7, 14),
            effective_date=None,
            version=None,
            summary=(
                "Topical Dermatologic Corticosteroids: In Vivo Bioequivalence "
                "Recommendations for demonstrating bioequivalence of topical corticosteroids."
            ),
            raw_data={
                "classification": "Generic Drugs",
                "detail_excerpt": (
                    "Topical Dermatologic Corticosteroids: In Vivo Bioequivalence "
                    "Recommendations for demonstrating bioequivalence of topical corticosteroids."
                ),
                "issuing_office": "Center for Drug Evaluation and Research",
                "topic": "Generic Drugs",
                "status_text": "Final",
            },
        )
    ]


@pytest.mark.anyio
async def test_ich_adapter_maps_guideline_news_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "items": [
            {
                "entityInfo": {
                    "id": "633",
                    "uuid": "d2a41978-f6a9-4281-ba61-90ef238b6fcd",
                },
                "bundleInfo": {
                    "title": "ICH E6(R3): Good Clinical Practice Annex 2 Adopted and Published",
                    "alias": "/news/ich-e6r3-good-clinical-practice-annex-2-adopted-and-published",
                    "created": "2026-07-10T14:16:12+0200",
                    "updated": "2026-07-10T14:22:08+0200",
                },
                "summary": "",
                "date": "2026-07-10T12:15:00+0200",
            },
            {
                "entityInfo": {
                    "id": "629",
                    "uuid": "0f59fefd-b281-40ff-97fc-873b372d1d50",
                },
                "bundleInfo": {
                    "title": "Key Outcomes of Biannual ICH Assembly Meeting",
                    "alias": "/news/key-outcomes-biannual-ich-assembly-meeting",
                    "created": "2026-06-04T20:24:22+0200",
                    "updated": "2026-06-04T21:13:28+0200",
                },
                "summary": "Administrative meeting summary.",
                "date": "2026-06-04T18:30:00+0200",
            },
        ]
    }

    async def _fake_fetch_json(self: IchCrawlerAdapter, url: str) -> dict[str, object]:
        assert url == self.news_api_url
        return payload

    async def _fake_fetch_detail_payload(
        url: str, fallback_title: str = ""
    ) -> dict[str, object]:
        return {
            "detail_title": fallback_title,
            "detail_excerpt": "Annex 2 adds proportionate GCP expectations for decentralised and pragmatic trials.",
            "detail_content": (
                "Annex 2 adds proportionate GCP expectations for decentralised, pragmatic and "
                "real-world-data trials, clarifying sponsor and investigator responsibilities."
            ),
            "detail_paragraphs": [
                "Annex 2 adds proportionate GCP expectations for decentralised, pragmatic and real-world-data trials.",
                "It clarifies sponsor and investigator responsibilities.",
            ],
        }

    monkeypatch.setattr(IchCrawlerAdapter, "_fetch_json", _fake_fetch_json)
    monkeypatch.setattr(
        "app.modules.regulatory_tracker.crawler.adapters.international.fetch_detail_payload",
        _fake_fetch_detail_payload,
    )

    adapter = IchCrawlerAdapter()
    records = await adapter.fetch_recent_documents()

    assert records == [
        CrawledRegulationRecord(
            source_site="ich",
            document_id="633",
            title="ICH E6(R3): Good Clinical Practice Annex 2 Adopted and Published",
            original_url=(
                "https://www.ich.org/news/ich-e6r3-good-clinical-practice-annex-2-adopted-and-published"
            ),
            publish_date=date(2026, 7, 10),
            effective_date=None,
            version="E6(R3)",
            summary=None,
            raw_data={
                "classification": "ICH guideline news",
                "detail_excerpt": (
                    "Annex 2 adds proportionate GCP expectations for decentralised and pragmatic trials."
                ),
                "alias": "/news/ich-e6r3-good-clinical-practice-annex-2-adopted-and-published",
                "created_at": "2026-07-10T14:16:12+0200",
                "updated_at": "2026-07-10T14:22:08+0200",
                "entity_uuid": "d2a41978-f6a9-4281-ba61-90ef238b6fcd",
                "detail_title": "ICH E6(R3): Good Clinical Practice Annex 2 Adopted and Published",
                "detail_content": (
                    "Annex 2 adds proportionate GCP expectations for decentralised, pragmatic and "
                    "real-world-data trials, clarifying sponsor and investigator responsibilities."
                ),
                "detail_paragraphs": [
                    "Annex 2 adds proportionate GCP expectations for decentralised, pragmatic and real-world-data trials.",
                    "It clarifies sponsor and investigator responsibilities.",
                ],
            },
        )
    ]
