from __future__ import annotations

import io
from typing import Any
from unittest.mock import AsyncMock

import pytest
from docx import Document
from httpx import AsyncClient

from app.modules.quality.api import quality_management as quality_api
from app.modules.quality.service import quality_feishu_pages as service


@pytest.mark.anyio
async def test_list_report_records_adds_record_id_alias(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service.quality_management_service,  # type: ignore[attr-defined]
        "get_deviation_report_record_list",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "id": "rec_report_001",
                        "deviation_code": "PC-2607001",
                        "feishu_base_record_id": "rec_report_001",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
            }
        ),
    )

    result = await service.list_report_records(db_session, page=1, page_size=20)

    assert result["items"][0]["id"] == "rec_report_001"
    assert result["items"][0]["record_id"] == "rec_report_001"


@pytest.mark.anyio
async def test_create_investigation_push_record_posts_feishu_fields_only(
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service.tracking_service,  # type: ignore[attr-defined]
        "_resolve_selected_submitter_contact",
        AsyncMock(
            return_value={
                "name": "张起智",
                "open_id": "ou_submitter_001",
                "department": "质量部",
                "department_head_name": "部门负责人甲",
            }
        ),
    )
    monkeypatch.setattr(
        service.feishu_sync_service,  # type: ignore[attr-defined]
        "_resolve_contact_bitable_user_value",
        AsyncMock(
            side_effect=[
                [{"id": "ou_submitter_001"}],
                [{"id": "ou_head_001"}],
                None,
                None,
            ]
        ),
    )
    create_mock: Any = AsyncMock(
        return_value={"record_id": "rec_push_001", "table_id": "tbl_push"}
    )
    monkeypatch.setattr(service, "_create_entity_record", create_mock)
    monkeypatch.setattr(
        service,
        "_get_investigation_push_record",
        AsyncMock(
            return_value={
                "id": "rec_push_001",
                "record_id": "rec_push_001",
                "deviation_code": "PC-2607001",
                "push_round": "第1次",
            }
        ),
    )

    result = await service.create_investigation_push_record(
        db_session,
        {
            "deviation_code": "PC-2607001",
            "push_round": "第1次",
            "investigation_report_url": "https://example.com/report.pdf",
            "submitter_open_id": "ou_submitter_001",
        },
    )

    assert result["record_id"] == "rec_push_001"
    create_mock.assert_awaited_once()
    call = create_mock.await_args
    assert call.args[0] is db_session
    assert call.args[1] == "deviation_investigation_push_record"
    assert call.kwargs["search_conditions"] == [
        ("偏差编号", "PC-2607001"),
        ("第N次推送", "第1次"),
    ]
    assert call.args[2]["偏差编号"] == "PC-2607001"
    assert call.args[2]["第N次推送"] == "第1次"
    assert call.args[2]["偏差调查报告"] == {
        "link": "https://example.com/report.pdf",
        "text": "https://example.com/report.pdf",
        "type": "url",
    }
    assert call.args[2]["提交人"] == [{"id": "ou_submitter_001"}]


@pytest.mark.anyio
async def test_report_records_api_returns_feishu_page_service_payload(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_mock: Any = AsyncMock(
        return_value={
            "items": [
                {
                    "id": "rec_report_001",
                    "record_id": "rec_report_001",
                    "deviation_code": "PC-2607001",
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
        }
    )
    monkeypatch.setattr(
        quality_api.quality_feishu_pages,  # type: ignore[attr-defined]
        "list_report_records",
        list_mock,
    )

    response = await client.get(
        "/api/v1/quality/deviation-report-records?page=1&page_size=20"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"][0]["record_id"] == "rec_report_001"
    assert payload["meta"]["total"] == 1
    list_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_investigation_push_create_api_posts_to_feishu_service(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_mock: Any = AsyncMock(
        return_value={"record_id": "rec_push_001", "id": "rec_push_001"}
    )
    monkeypatch.setattr(
        quality_api.quality_feishu_pages,  # type: ignore[attr-defined]
        "create_investigation_push_record",
        create_mock,
    )

    response = await client.post(
        "/api/v1/quality/deviation-investigation-push-records",
        json={"deviation_code": "PC-2607001", "push_round": "第1次"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["record_id"] == "rec_push_001"
    create_mock.assert_awaited_once()


