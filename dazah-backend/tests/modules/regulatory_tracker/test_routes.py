from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.modules.regulatory_tracker.models.regulatory_document import RegulatoryDocument


@pytest.fixture(autouse=True)
async def _authenticate_regulatory(client: AsyncClient):
    """本项目 API 需认证：注入稳定的测试用户（与 hr 模块测试同模式）。"""
    from uuid import UUID

    from app.main import app
    from app.platform.identity.deps import get_current_user
    from app.platform.identity.models import User

    user = User(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        name="法规跟踪测试管理员",
        username="regulatory-migration-admin",
        role="admin",
        status="active",
        auth_source="local",
        feishu_open_id="regulatory-source-migration-open-id",
        department="SPEC质量管理部",
    )

    async def _override_current_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_regulatory_document_ledger_fields_exist() -> None:
    table = RegulatoryDocument.__table__

    assert table.schema == "regulatory_tracker"

    expected_columns = {
        "source_site_code": (sa.String, 100),
        "source_site_name": (sa.String, 255),
        "source_url": (sa.String, 1000),
        "version_text": (sa.String, 200),
        "effective_date": (sa.Date, None),
        "summary_text": (sa.Text, None),
        "capture_date": (sa.Date, None),
        "content_hash": (sa.String, 128),
        "filter_status": (sa.String, 50),
        "filter_reason": (sa.Text, None),
    }

    for column_name, (expected_type, expected_length) in expected_columns.items():
        assert column_name in table.c
        column = table.c[column_name]
        assert isinstance(column.type, expected_type)
        if expected_length is not None:
            assert column.type.length == expected_length


def test_regulatory_document_ledger_fields_indexes_exist() -> None:
    index_names = {index.name for index in RegulatoryDocument.__table__.indexes}

    assert "ix_regulatory_documents_source_site_code" in index_names
    assert "ix_regulatory_documents_capture_date" in index_names
    assert "ix_regulatory_documents_filter_status" in index_names
    assert "ix_regulatory_documents_content_hash" in index_names


@pytest.mark.anyio
async def test_list_documents_returns_ledger_fields(
    client: AsyncClient,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    document_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        capture_date=date(2026, 7, 14),
        title=f"化学药品监管台账测试-{suffix}",
        version_text="2026年第1版",
        publish_date=date(2026, 7, 14),
        effective_date=date(2026, 8, 1),
        summary_text="用于校验法规台账列表字段口径。",
        source_url="https://www.cde.org.cn/test-ledger",
        source_site_name="国家药监局药审中心",
        is_new=True,
        ai_summary=None,
    )

    with patch(
        "app.modules.regulatory_tracker.api.routes.repo.get_documents_with_filters",
        new=AsyncMock(return_value=([document], 1)),
    ):
        response = await client.get(
            "/api/v1/regulatory-documents",
            params={"keyword": suffix, "page": 1, "pageSize": 20},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["total"] == 1

    item = body["data"]["items"][0]
    assert item == {
        "id": str(document_id),
        "capture_date": "2026-07-14",
        "title": f"化学药品监管台账测试-{suffix}",
        "version_text": "2026年第1版",
        "publish_date": "2026-07-14",
        "effective_date": "2026-08-01",
        "summary_text": "用于校验法规台账列表字段口径。",
        "source_url": "https://www.cde.org.cn/test-ledger",
        "source_site_name": "国家药监局药审中心",
        "is_new": True,
        "ai_summary": None,
        "ai_analysis_status": None,
        "ai_analyzed_at": None,
    }


@pytest.mark.anyio
async def test_list_documents_forwards_source_and_capture_filters(
    client: AsyncClient,
) -> None:
    with patch(
        "app.modules.regulatory_tracker.api.routes.repo.get_documents_with_filters",
        new=AsyncMock(return_value=([], 0)),
    ) as mocked_get_documents:
        response = await client.get(
            "/api/v1/regulatory-documents",
            params={
                "sourceSite": "国家药品监督管理局食品药品审核查验中心",
                "captureDateFrom": "2026-01-01",
                "captureDateTo": "2026-07-14",
                "page": 1,
                "pageSize": 20,
            },
        )

    assert response.status_code == 200
    mocked_get_documents.assert_awaited_once()
    kwargs = mocked_get_documents.await_args.kwargs
    assert kwargs["source_site"] == "国家药品监督管理局食品药品审核查验中心"
    assert kwargs["capture_date_from"] == date(2026, 1, 1)
    assert kwargs["capture_date_to"] == date(2026, 7, 14)


@pytest.mark.anyio
async def test_get_document_detail_returns_ai_fields(
    client: AsyncClient,
) -> None:
    document_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        capture_date=date(2026, 7, 14),
        title="法规详情测试",
        version_text="V1",
        publish_date=date(2026, 7, 13),
        effective_date=date(2026, 8, 1),
        summary_text="法规摘要",
        source_url="https://www.cde.org.cn/detail",
        source_site_name="国家药监局药审中心",
        is_new=True,
        ai_summary="AI 摘要",
        ai_key_points=["要点1", "要点2"],
        ai_relevance_score=0.82,
        ai_analysis_status="completed",
        ai_analyzed_at=datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
    )

    with patch(
        "app.modules.regulatory_tracker.api.routes.repo.get_document_by_id",
        new=AsyncMock(return_value=document),
    ):
        response = await client.get(f"/api/v1/regulatory-documents/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["ai_summary"] == "AI 摘要"
    assert body["data"]["ai_key_points"] == ["要点1", "要点2"]
    assert body["data"]["ai_relevance_score"] == 0.82
    assert body["data"]["ai_analysis_status"] == "completed"
    assert body["data"]["summary_text"] == "AI 摘要"


@pytest.mark.anyio
async def test_list_documents_prefers_ai_summary_for_display_summary(
    client: AsyncClient,
) -> None:
    document_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        capture_date=date(2026, 7, 14),
        title="EMA GMP 指导原则",
        version_text=None,
        publish_date=date(2026, 7, 14),
        effective_date=None,
        summary_text="This page provides guidance on GMP expectations.",
        ai_summary="该文件重点说明 GMP 执行要求和适用范围。",
        source_url="https://www.ema.europa.eu/en/test",
        source_site_name="欧洲药品管理局",
        is_new=False,
    )

    with patch(
        "app.modules.regulatory_tracker.api.routes.repo.get_documents_with_filters",
        new=AsyncMock(return_value=([document], 1)),
    ):
        response = await client.get(
            "/api/v1/regulatory-documents", params={"page": 1, "pageSize": 20}
        )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["data"]["items"][0]["summary_text"]
        == "该文件重点说明 GMP 执行要求和适用范围。"
    )


@pytest.mark.anyio
async def test_list_documents_prefers_chinese_summary_text_over_english_ai_summary(
    client: AsyncClient,
) -> None:
    document_id = uuid.uuid4()
    document = SimpleNamespace(
        id=document_id,
        capture_date=date(2026, 7, 14),
        title="EMA GMP 指导原则",
        version_text=None,
        publish_date=date(2026, 7, 14),
        effective_date=None,
        summary_text="该文件说明 GMP 执行要求及适用范围。",
        ai_summary="This document explains GMP requirements.",
        source_url="https://www.ema.europa.eu/en/test",
        source_site_name="欧洲药品管理局",
        is_new=False,
    )

    with patch(
        "app.modules.regulatory_tracker.api.routes.repo.get_documents_with_filters",
        new=AsyncMock(return_value=([document], 1)),
    ):
        response = await client.get(
            "/api/v1/regulatory-documents", params={"page": 1, "pageSize": 20}
        )

    assert response.status_code == 200
    body = response.json()
    assert (
        body["data"]["items"][0]["summary_text"]
        == "该文件说明 GMP 执行要求及适用范围。"
    )


@pytest.mark.anyio
async def test_trigger_summary_backfill_returns_stats(
    client: AsyncClient,
) -> None:
    with patch(
        "app.modules.regulatory_tracker.api.routes.backfill_document_summaries",
        new=AsyncMock(
            return_value={"checked": 10, "updated": 6, "unchanged": 3, "skipped": 1}
        ),
    ) as mocked_backfill:
        response = await client.post(
            "/api/v1/regulatory-documents/backfill-summaries",
            params={"limit": 50},
        )

    assert response.status_code == 200
    mocked_backfill.assert_awaited_once()
    assert mocked_backfill.await_args.kwargs["limit"] == 50
    body = response.json()
    assert body["code"] == 200
    assert body["data"] == {"checked": 10, "updated": 6, "unchanged": 3, "skipped": 1}


@pytest.mark.anyio
async def test_trigger_manual_sync_returns_summary(
    client: AsyncClient,
) -> None:
    with patch(
        "app.modules.regulatory_tracker.api.routes.run_all_sites",
        new=AsyncMock(
            return_value={
                "bootstrap": {
                    "created_sources": 11,
                    "created_channels": 11,
                    "site_count": 11,
                    "sites": ["cde", "cfdi", "edqm"],
                },
                "totals": {
                    "checked": 3,
                    "accepted": 1,
                    "inserted": 1,
                    "updated": 0,
                    "unchanged": 0,
                    "rejected": 2,
                },
                "sites": [
                    {
                        "site_code": "cde",
                        "site_name": "国家药品监督管理局药品审评中心",
                        "totals": {
                            "checked": 1,
                            "accepted": 1,
                            "inserted": 1,
                            "updated": 0,
                            "unchanged": 0,
                            "rejected": 0,
                        },
                        "rejection_reasons": {},
                        "error": None,
                    }
                ],
                "analysis": {
                    "analyzed": 1,
                    "failed": 0,
                    "skipped": 0,
                },
            }
        ),
    ):
        response = await client.post("/api/v1/regulatory-documents/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    # 端点已异步化：立即返回任务启动状态，轮询 sync/status 获取结果
    assert body["data"]["status"] == "started"


@pytest.mark.anyio
async def test_get_notification_settings_returns_setting_payload(
    client: AsyncClient,
) -> None:
    payload = {
        "is_enabled": True,
        "recent_days": 7,
        "recipient_open_id": "ou_test",
        "recipient_name": "武巧玲",
        "recipient_department": "注册管理",
        "schedule_time": "10:00",
        "pending_count": 3,
    }

    with patch(
        "app.modules.regulatory_tracker.api.routes.RegulatoryTrackerNotificationService.get_notification_settings",
        new=AsyncMock(
            return_value=SimpleNamespace(model_dump=lambda mode="json": payload)
        ),
    ):
        response = await client.get(
            "/api/v1/regulatory-documents/notification-settings"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"] == payload


@pytest.mark.anyio
async def test_update_notification_settings_returns_saved_payload(
    client: AsyncClient,
) -> None:
    payload = {
        "is_enabled": True,
        "recent_days": 7,
        "recipient_open_id": "ou_test",
        "recipient_name": "武巧玲",
        "recipient_department": "注册管理",
        "schedule_time": "10:00",
        "pending_count": 1,
    }

    with patch(
        "app.modules.regulatory_tracker.api.routes.RegulatoryTrackerNotificationService.update_notification_settings",
        new=AsyncMock(
            return_value=SimpleNamespace(model_dump=lambda mode="json": payload)
        ),
    ) as mocked_update:
        response = await client.put(
            "/api/v1/regulatory-documents/notification-settings",
            json={
                "is_enabled": True,
                "recent_days": 7,
                "recipient_open_id": "ou_test",
            },
        )

    assert response.status_code == 200
    mocked_update.assert_awaited_once()
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "推送配置已保存"
    assert body["data"] == payload
