from __future__ import annotations

import uuid
import urllib.request
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.deviations import Deviation
from app.modules.quality.api import quality_management as quality_api
from app.modules.quality.schemas.tracking_records import (
    CreateCapaPlanTrackRequest,
    CreateDeviationInvestigationPushRecordRequest,
    UpdateCapaPlanTrackRequest,
    UpdateDeviationInvestigationPushRecordRequest,
)
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service import tracking_records as tracking_service


@pytest.fixture(autouse=True)
async def _clean_tracking_tables(db_session: AsyncSession) -> None:
    await db_session.execute(text("CREATE SCHEMA IF NOT EXISTS quality"))
    await db_session.execute(
        text(
            """
            ALTER TABLE quality.deviations
            ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
            ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
            ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
            """
        )
    )
    await db_session.execute(
        text(
            """
            ALTER TABLE quality.capas
            ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
            ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
            ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
            """
        )
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.deviation_investigation_push_records (
                deviation_id UUID NOT NULL,
                deviation_code VARCHAR(255) NOT NULL,
                push_round VARCHAR(50) NOT NULL,
                investigation_report_url TEXT NULL,
                submitted_at TIMESTAMPTZ NULL,
                submitter VARCHAR(255) NULL,
                department_head VARCHAR(255) NULL,
                department_head_result VARCHAR(50) NULL,
                department_head_reviewed_at TIMESTAMPTZ NULL,
                qa_name VARCHAR(255) NULL,
                qa_result VARCHAR(50) NULL,
                qa_reviewed_at TIMESTAMPTZ NULL,
                qa_head_name VARCHAR(255) NULL,
                qa_head_result VARCHAR(50) NULL,
                qa_head_reviewed_at TIMESTAMPTZ NULL,
                feishu_base_table_id VARCHAR(100) NULL,
                feishu_base_record_id VARCHAR(100) NULL,
                feishu_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                feishu_last_sync_error TEXT NULL,
                feishu_last_sync_direction VARCHAR(20) NULL,
                feishu_synced_at TIMESTAMPTZ NULL,
                feishu_source_updated_at TIMESTAMPTZ NULL,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            ALTER TABLE quality.deviation_investigation_push_records
            ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
            ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
            ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
            """
        )
    )
    await db_session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS quality.capa_plan_tracks (
                capa_id UUID NOT NULL,
                capa_code VARCHAR(255) NOT NULL,
                plan_content TEXT NOT NULL,
                due_date DATE NULL,
                owner_name VARCHAR(255) NULL,
                owner_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                department_head VARCHAR(255) NULL,
                department_head_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                progress VARCHAR(50) NULL,
                reminder_status VARCHAR(50) NOT NULL DEFAULT 'pending',
                feishu_base_table_id VARCHAR(100) NULL,
                feishu_base_record_id VARCHAR(100) NULL,
                feishu_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                feishu_last_sync_error TEXT NULL,
                feishu_last_sync_direction VARCHAR(20) NULL,
                feishu_synced_at TIMESTAMPTZ NULL,
                feishu_source_updated_at TIMESTAMPTZ NULL,
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by UUID NULL,
                updated_by UUID NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
    )
    await db_session.execute(
        text(
            """
            ALTER TABLE quality.capa_plan_tracks
            ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
            ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
            ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
            ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
            """
        )
    )
    await db_session.execute(text("DELETE FROM quality.deviation_investigation_push_records"))
    await db_session.execute(text("DELETE FROM quality.capa_plan_tracks"))
    await db_session.execute(CAPA.__table__.delete())
    await db_session.execute(Deviation.__table__.delete())
    await db_session.commit()
    yield
    await db_session.execute(text("DELETE FROM quality.deviation_investigation_push_records"))
    await db_session.execute(text("DELETE FROM quality.capa_plan_tracks"))
    await db_session.execute(CAPA.__table__.delete())
    await db_session.execute(Deviation.__table__.delete())
    await db_session.commit()


@pytest.fixture(autouse=True)
def _stub_debug_server(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyResponse:
        def read(self) -> bytes:
            return b""

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: _DummyResponse(),
    )


@pytest.mark.anyio
async def test_deviation_investigation_push_record_service_roundtrip(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_deviation_investigation_push_record_after_write",
        AsyncMock(),
    )
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-TRACK-001",
        title="偏差调查推送测试",
        status="pending_investigation",
    )
    db_session.add(deviation)
    await db_session.commit()
    monkeypatch.setattr(
        tracking_service.repository,
        "get_deviation_by_id",
        AsyncMock(return_value=deviation),
    )
    monkeypatch.setattr(
        tracking_service,
        "_resolve_selected_submitter_contact",
        AsyncMock(
            return_value={
                "name": "张起智",
                "open_id": "ou_submitter_001",
                "department": "QC",
                "department_head_name": "车间主任",
            }
        ),
    )
    create_result = await tracking_service.create_deviation_investigation_push_record(
        db_session,
        CreateDeviationInvestigationPushRecordRequest(
            deviation_id=deviation.id,
            push_round="第1次",
            investigation_report_url="https://example.com/report-1.pdf",
            submitted_at=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
            submitter_open_id="ou_submitter_001",
            department_head_result="approved",
        ),
        "system",
    )
    record_id = create_result["id"]
    assert create_result["deviation_code"] == "DEV-TRACK-001"

    detail = await tracking_service.get_deviation_investigation_push_record_detail(
        db_session,
        uuid.UUID(record_id),
    )
    assert str(detail.id) == record_id
    assert detail.deviation_code == "DEV-TRACK-001"
    assert detail.submitter == "张起智"
    assert detail.department_head == "车间主任"

    update_result = await tracking_service.update_deviation_investigation_push_record(
        db_session,
        uuid.UUID(record_id),
        UpdateDeviationInvestigationPushRecordRequest(
            qa_name="QA小王",
            qa_result="approved",
            qa_reviewed_at=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        ),
        "system",
    )
    assert update_result["qa_name"] == "QA小王"
    assert update_result["qa_result"] == "approved"


@pytest.mark.anyio
async def test_get_deviation_investigation_push_record_list_reads_feishu_single_source(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_investigation_push_record": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_push",
                table_id="tbl_push_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
        },
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="PC-2602001",
        title="本地偏差仅用于操作映射",
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db_session.add(deviation)
    await db_session.commit()

    async def fake_search_records(
        _db: AsyncSession,
        entity_code: str,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
    ) -> list[dict]:
        assert entity_code == "deviation_investigation_push_record"
        return [
            {
                "record_id": "rec_push_001",
                "created_time": int(now.timestamp() * 1000),
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "PC-2602001",
                    "第N次推送": "第2次",
                    "偏差调查报告": "https://example.com/investigation.pdf",
                    "提交日期": int(now.timestamp() * 1000),
                    "提交人": "张起智",
                    "部门负责人": "张起智",
                    "部门负责人审核结果": "通过",
                    "QA": "杨小芹",
                    "QA审核结果": "不通过",
                    "QA负责人": "张积军",
                    "QA负责人审核结果": "通过",
                },
            }
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )

    result = await tracking_service.get_deviation_investigation_push_record_list(
        db_session,
        page=1,
        page_size=20,
    )

    assert result["total"] == 1
    assert result["items"][0]["id"] == "rec_push_001"
    assert result["items"][0]["deviation_code"] == "PC-2602001"
    assert result["items"][0]["deviation_id"] == deviation.id
    assert result["items"][0]["push_round"] == "第2次"
    assert result["items"][0]["submitter"] == "张起智"
    assert result["items"][0]["department_head_result"] == "approved"
    assert result["items"][0]["qa_result"] == "rejected"
    assert result["items"][0]["qa_head_result"] == "approved"
    assert result["items"][0]["feishu_base_record_id"] == "rec_push_001"
    assert result["items"][0]["feishu_sync_status"] == "synced"


@pytest.mark.anyio
async def test_update_deviation_investigation_push_record_by_feishu_record_ref(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_investigation_push_record": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_push",
                table_id="tbl_push_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
        },
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    async def fake_search_records(
        _db: AsyncSession,
        entity_code: str,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
    ) -> list[dict]:
        assert entity_code == "deviation_investigation_push_record"
        return [
            {
                "record_id": "rec_push_remote_001",
                "created_time": int(now.timestamp() * 1000),
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "PC-2602001",
                    "第N次推送": "第1次",
                    "偏差调查报告": "https://example.com/old.pdf",
                    "提交日期": int(now.timestamp() * 1000),
                    "提交人": [{"name": "张起智"}],
                    "部门负责人": [{"name": "部门负责人甲"}],
                    "部门负责人审核结果": "通过",
                    "QA": [{"name": "QA甲"}],
                    "QA审核结果": "不通过",
                    "QA负责人": [{"name": "QA负责人甲"}],
                    "QA负责人审核结果": "通过",
                },
            }
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )
    monkeypatch.setattr(
        feishu_sync_service,
        "_get_department_contacts_from_feishu",
        AsyncMock(
            return_value=[
                {"name": "张起智", "department": "质量部", "bitable_user_id": "ou_submitter_001"},
                {"name": "部门负责人甲", "department": "质量部", "bitable_user_id": "ou_dept_head_001"},
                {"name": "QA甲", "department": "质量管理部", "bitable_user_id": "ou_qa_001"},
                {"name": "QA负责人甲", "department": "质量管理部", "bitable_user_id": "ou_qa_head_001"},
            ]
        ),
    )
    upsert_mock = AsyncMock(return_value=("rec_push_remote_001", "tbl_push_real"))
    monkeypatch.setattr(feishu_sync_service.feishu_sync, "_upsert_record", upsert_mock)

    result = await tracking_service.update_deviation_investigation_push_record_by_ref(
        db_session,
        "rec_push_remote_001",
        UpdateDeviationInvestigationPushRecordRequest(
            investigation_report_url="https://example.com/new.pdf",
            qa_result="approved",
        ),
        "system",
    )

    assert result["id"] == "rec_push_remote_001"
    assert result["investigation_report_url"] == "https://example.com/new.pdf"
    assert result["qa_result"] == "approved"
    assert upsert_mock.await_args.args[3] == "rec_push_remote_001"
    assert upsert_mock.await_args.args[4]["偏差调查报告"] == {
        "link": "https://example.com/new.pdf",
        "text": "https://example.com/new.pdf",
        "type": "url",
    }
    assert upsert_mock.await_args.args[4]["提交人"] == [{"id": "ou_submitter_001"}]
    assert upsert_mock.await_args.args[4]["QA审核结果"] == "通过"


@pytest.mark.anyio
async def test_update_deviation_investigation_push_record_by_feishu_record_ref_preserves_url_link(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_investigation_push_record": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_push",
                table_id="tbl_push_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
        },
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    async def fake_search_records(
        _db: AsyncSession,
        entity_code: str,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
    ) -> list[dict]:
        assert entity_code == "deviation_investigation_push_record"
        return [
            {
                "record_id": "rec_push_remote_002",
                "created_time": int(now.timestamp() * 1000),
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "PC-2602002",
                    "第N次推送": "第2次",
                    "偏差调查报告": {
                        "text": "偏差CAPA管理 - 飞书云文档",
                        "link": "https://example.com/docx/abc",
                    },
                    "QA审核结果": "不通过",
                },
            }
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )
    monkeypatch.setattr(
        feishu_sync_service,
        "_get_department_contacts_from_feishu",
        AsyncMock(return_value=[]),
    )
    upsert_mock = AsyncMock(return_value=("rec_push_remote_002", "tbl_push_real"))
    monkeypatch.setattr(feishu_sync_service.feishu_sync, "_upsert_record", upsert_mock)

    result = await tracking_service.update_deviation_investigation_push_record_by_ref(
        db_session,
        "rec_push_remote_002",
        UpdateDeviationInvestigationPushRecordRequest(qa_result="approved"),
        "system",
    )

    assert result["investigation_report_url"] == "https://example.com/docx/abc"
    assert upsert_mock.await_args.args[4]["偏差调查报告"] == {
        "link": "https://example.com/docx/abc",
        "text": "https://example.com/docx/abc",
        "type": "url",
    }


@pytest.mark.anyio
async def test_update_deviation_investigation_push_record_by_feishu_record_ref_rejects_invalid_url(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_investigation_push_record": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_push",
                table_id="tbl_push_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
        },
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    async def fake_search_records(
        _db: AsyncSession,
        entity_code: str,
        table_id: str | None = None,
        *,
        filter_str: str | None = None,
    ) -> list[dict]:
        assert entity_code == "deviation_investigation_push_record"
        return [
            {
                "record_id": "rec_push_remote_003",
                "created_time": int(now.timestamp() * 1000),
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "PC-2602003",
                    "第N次推送": "第3次",
                    "偏差调查报告": "报告标题不是链接",
                },
            }
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )

    with pytest.raises(ValueError, match="偏差调查报告必须填写有效链接"):
        await tracking_service.update_deviation_investigation_push_record_by_ref(
            db_session,
            "rec_push_remote_003",
            UpdateDeviationInvestigationPushRecordRequest(qa_result="approved"),
            "system",
        )


@pytest.mark.anyio
async def test_capa_plan_track_api_roundtrip(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
 ) -> None:
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_capa_plan_track_after_write",
        AsyncMock(),
    )
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-TRACK-001",
        status="draft",
        title="CAPA计划跟踪测试",
    )
    db_session.add(capa)
    await db_session.commit()

    create_response = await client.post(
        "/api/v1/quality/capa-plan-tracks",
        json={
            "capa_id": str(capa.id),
            "plan_content": "完成偏差复盘并关闭CAPA",
            "due_date": "2026-07-15",
            "owner_name": "李四",
            "progress": "in_progress",
            "reminder_status": "pending",
        },
    )
    assert create_response.status_code == 200
    track_id = create_response.json()["data"]["id"]
    assert create_response.json()["data"]["capa_code"] == "CAPA-TRACK-001"

    list_response = await client.get(
        "/api/v1/quality/capa-plan-tracks",
        params={"capa_code": "CAPA-TRACK-001"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1
    assert list_response.json()["data"][0]["id"] == track_id

    update_response = await client.put(
        f"/api/v1/quality/capa-plan-tracks/{track_id}",
        json={
            "owner_confirmed": True,
            "department_head_confirmed": True,
            "progress": "completed",
            "reminder_status": "confirmed",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["data"]["owner_confirmed"] is True
    assert update_response.json()["data"]["department_head_confirmed"] is True
    assert update_response.json()["data"]["progress"] == "completed"


@pytest.mark.anyio
async def test_deviation_report_records_api_uses_static_route(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-REPORT-001",
        title="报告记录静态路由测试",
        description="验证报告记录静态接口",
        status="pending_investigation",
    )
    db_session.add(deviation)
    await db_session.commit()

    response = await client.get(
        "/api/v1/quality/deviation-report-records",
        params={"page": 1, "page_size": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["page_size"] == 10
    assert payload["meta"]["total"] >= 1
    assert any(item["deviation_code"] == "DEV-REPORT-001" for item in payload["data"])


@pytest.mark.anyio
async def test_quality_sync_conflicts_api_returns_conflict_records(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc)
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-API-CONFLICT-001",
        title="API偏差冲突",
        status="pending_investigation",
        feishu_sync_status="conflict",
        feishu_last_sync_error="检测到系统与飞书 Base 均已更新",
        feishu_last_sync_direction="base_to_system",
        feishu_base_table_id="tbl_deviation",
        feishu_base_record_id="rec_deviation_conflict",
        feishu_synced_at=now,
        feishu_source_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add(deviation)
    await db_session.commit()

    response = await client.get("/api/v1/quality/feishu-sync/conflicts", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] >= 1
    item = next(
        conflict for conflict in payload["data"] if conflict["record_code"] == "DEV-API-CONFLICT-001"
    )
    assert item["entity_type"] == "deviation"
    assert item["route_path"] == "/quality/deviations"
    assert item["feishu_last_sync_direction"] == "base_to_system"


@pytest.mark.anyio
async def test_quality_feishu_app_settings_api_roundtrip(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_app_settings(_db: AsyncSession) -> dict:
        return {
            "app_id": "cli_app_id",
            "app_secret_masked": "cli_****_id",
            "is_enabled": True,
            "last_test_status": "success",
            "last_test_error": None,
            "last_tested_at": "2026-07-03T09:00:00+00:00",
        }

    async def fake_update_app_settings(_db: AsyncSession, data) -> dict:
        assert data.app_id == "cli_app_id"
        assert data.app_secret == "cli_secret"
        assert data.is_enabled is True
        return {
            "app_id": data.app_id,
            "app_secret_masked": "cli_****_ret",
            "is_enabled": data.is_enabled,
            "last_test_status": "success",
            "last_test_error": None,
            "last_tested_at": "2026-07-03T09:05:00+00:00",
        }

    async def fake_test_app_settings(_db: AsyncSession) -> dict:
        return {
            "success": True,
            "message": "飞书应用连接成功",
            "checked_at": "2026-07-03T09:10:00+00:00",
            "entity_code": None,
            "table_id": None,
        }

    monkeypatch.setattr(quality_api.service, "get_quality_feishu_app_settings", fake_get_app_settings)
    monkeypatch.setattr(
        quality_api.service,
        "update_quality_feishu_app_settings",
        fake_update_app_settings,
    )
    monkeypatch.setattr(
        quality_api.service,
        "test_quality_feishu_app_settings",
        fake_test_app_settings,
    )

    get_response = await client.get("/api/v1/quality/feishu-settings/app")
    assert get_response.status_code == 200
    assert get_response.json()["app_id"] == "cli_app_id"
    assert get_response.json()["app_secret_masked"] == "cli_****_id"

    put_response = await client.put(
        "/api/v1/quality/feishu-settings/app",
        json={
            "app_id": "cli_app_id",
            "app_secret": "cli_secret",
            "is_enabled": True,
        },
    )
    assert put_response.status_code == 200
    assert put_response.json()["app_secret_masked"] == "cli_****_ret"
    assert put_response.json()["is_enabled"] is True

    test_response = await client.post("/api/v1/quality/feishu-settings/app/test")
    assert test_response.status_code == 200
    assert test_response.json()["success"] is True
    assert test_response.json()["message"] == "飞书应用连接成功"


@pytest.mark.anyio
async def test_quality_feishu_entity_settings_api_roundtrip(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list_entity_settings(_db: AsyncSession) -> list[dict]:
        return [
            {
                "entity_code": "deviation_ledger",
                "entity_name": "偏差台账",
                "entity_group": "偏差管理",
                "app_token": "bascn_deviation",
                "base_table_name": "偏差台账",
                "base_table_id": "tbl_deviation",
                "is_enabled": True,
                "enable_push_to_feishu": True,
                "enable_pull_from_feishu": True,
                "sort_order": 30,
                "last_sync_status": "success",
                "last_sync_error": None,
                "last_synced_at": "2026-07-03T09:15:00+00:00",
            }
        ]

    async def fake_update_entity_setting(_db: AsyncSession, entity_code: str, data) -> dict:
        assert entity_code == "deviation_ledger"
        assert data.app_token == "bascn_deviation"
        assert data.base_table_name == "偏差台账"
        assert data.base_table_id == "tbl_deviation"
        assert data.is_enabled is True
        return {
            "entity_code": entity_code,
            "entity_name": "偏差台账",
            "entity_group": "偏差管理",
            "app_token": data.app_token,
            "base_table_name": data.base_table_name,
            "base_table_id": data.base_table_id,
            "is_enabled": data.is_enabled,
            "enable_push_to_feishu": data.enable_push_to_feishu,
            "enable_pull_from_feishu": data.enable_pull_from_feishu,
            "sort_order": 30,
            "last_sync_status": "success",
            "last_sync_error": None,
            "last_synced_at": "2026-07-03T09:20:00+00:00",
        }

    async def fake_test_entity_setting(_db: AsyncSession, entity_code: str) -> dict:
        assert entity_code == "deviation_ledger"
        return {
            "success": True,
            "message": "偏差台账 配置可访问",
            "checked_at": "2026-07-03T09:25:00+00:00",
            "entity_code": entity_code,
            "table_id": "tbl_deviation",
        }

    monkeypatch.setattr(
        quality_api.service,
        "list_quality_feishu_entity_settings",
        fake_list_entity_settings,
    )
    monkeypatch.setattr(
        quality_api.service,
        "update_quality_feishu_entity_setting",
        fake_update_entity_setting,
    )
    monkeypatch.setattr(
        quality_api.service,
        "test_quality_feishu_entity_setting",
        fake_test_entity_setting,
    )

    list_response = await client.get("/api/v1/quality/feishu-settings/entities")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["entity_code"] == "deviation_ledger"

    put_response = await client.put(
        "/api/v1/quality/feishu-settings/entities/deviation_ledger",
        json={
            "app_token": "bascn_deviation",
            "base_table_name": "偏差台账",
            "base_table_id": "tbl_deviation",
            "is_enabled": True,
            "enable_push_to_feishu": True,
            "enable_pull_from_feishu": True,
        },
    )
    assert put_response.status_code == 200
    assert put_response.json()["app_token"] == "bascn_deviation"
    assert put_response.json()["base_table_id"] == "tbl_deviation"
    assert put_response.json()["is_enabled"] is True

    test_response = await client.post(
        "/api/v1/quality/feishu-settings/entities/deviation_ledger/test"
    )
    assert test_response.status_code == 200
    assert test_response.json()["entity_code"] == "deviation_ledger"
    assert test_response.json()["table_id"] == "tbl_deviation"


@pytest.mark.anyio
async def test_quality_feishu_entity_tables_api_returns_table_options(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list_tables(_db: AsyncSession, entity_code: str, app_token: str | None = None) -> list[dict]:
        assert entity_code == "deviation_ledger"
        assert app_token == "bascn_deviation"
        return [
            {"table_id": "tbl_deviation", "table_name": "偏差台账"},
            {"table_id": "tbl_deviation_push", "table_name": "偏差调查推送"},
        ]

    monkeypatch.setattr(
        quality_api.service,
        "list_quality_feishu_tables",
        fake_list_tables,
    )

    response = await client.get(
        "/api/v1/quality/feishu-settings/entities/deviation_ledger/tables",
        params={"app_token": "bascn_deviation"},
    )
    assert response.status_code == 200
    assert response.json() == [
        {"table_id": "tbl_deviation", "table_name": "偏差台账"},
        {"table_id": "tbl_deviation_push", "table_name": "偏差调查推送"},
    ]


@pytest.mark.anyio
async def test_quality_feishu_entity_field_mapping_api_returns_bundle(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_mapping_bundle(
        _db: AsyncSession,
        entity_code: str,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> dict:
        assert entity_code == "deviation_ledger"
        assert app_token == "bascn_deviation"
        assert table_id == "tbl_deviation"
        return {
            "entity_code": "deviation_ledger",
            "entity_name": "偏差台账",
            "system_fields": [
                {"field_key": "偏差编号", "field_label": "偏差编号", "direction": "both"},
                {"field_key": "根本原因", "field_label": "根本原因", "direction": "both"},
            ],
            "feishu_fields": [
                {"field_id": "fld_code", "field_name": "偏差编号", "field_type": 1},
                {"field_id": "fld_reason", "field_name": "根本原因", "field_type": 1},
            ],
            "field_mappings": [
                {"system_field": "偏差编号", "feishu_field": "偏差编号"},
                {"system_field": "根本原因", "feishu_field": "根本原因"},
            ],
        }

    monkeypatch.setattr(
        quality_api.service,
        "get_quality_feishu_entity_field_mapping_bundle",
        fake_get_mapping_bundle,
    )

    response = await client.get(
        "/api/v1/quality/feishu-settings/entities/deviation_ledger/field-mapping",
        params={"app_token": "bascn_deviation", "table_id": "tbl_deviation"},
    )
    assert response.status_code == 200
    assert response.json()["entity_code"] == "deviation_ledger"
    assert response.json()["entity_name"] == "偏差台账"
    assert len(response.json()["system_fields"]) == 2
    assert response.json()["field_mappings"][0]["system_field"] == "偏差编号"


@pytest.mark.anyio
async def test_department_contacts_feishu_api_delegates_db_and_pagination(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_department_contact_list_from_feishu(
        db: AsyncSession,
        page: int,
        page_size: int,
    ) -> dict:
        assert db is not None
        assert page == 2
        assert page_size == 50
        return {
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "department": "质量部",
                    "name": "张三",
                    "phone": "13800138000",
                }
            ],
            "total": 1,
            "page": page,
            "page_size": page_size,
        }

    monkeypatch.setattr(
        quality_api.service,
        "get_department_contact_list_from_feishu",
        fake_get_department_contact_list_from_feishu,
    )

    response = await client.get(
        "/api/v1/quality/department-contacts/feishu",
        params={"page": 2, "page_size": 50},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    assert payload["page"] == 2
    assert payload["page_size"] == 50
    assert payload["items"][0]["department"] == "质量部"
    assert payload["items"][0]["name"] == "张三"


@pytest.mark.anyio
async def test_create_deviation_investigation_push_record_triggers_auto_sync(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-AUTO-TRACK-001",
        title="自动同步推送记录",
        status="pending_investigation",
    )
    db_session.add(deviation)
    await db_session.commit()

    auto_sync_mock = AsyncMock()
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_deviation_investigation_push_record_after_write",
        auto_sync_mock,
    )
    monkeypatch.setattr(
        tracking_service,
        "_resolve_selected_submitter_contact",
        AsyncMock(
            return_value={
                "name": "自动触发人",
                "open_id": "ou_submitter_002",
                "department": "QA",
                "department_head_name": "QA负责人甲",
            }
        ),
    )

    result = await tracking_service.create_deviation_investigation_push_record(
        db_session,
        CreateDeviationInvestigationPushRecordRequest(
            deviation_id=deviation.id,
            push_round="第1次",
            investigation_report_url="https://example.com/report.pdf",
            submitter_open_id="ou_submitter_002",
        ),
        "system",
    )

    assert result["deviation_code"] == "DEV-AUTO-TRACK-001"
    assert auto_sync_mock.await_count == 1
    assert auto_sync_mock.await_args.args[0] is db_session
    assert auto_sync_mock.await_args.args[1] == uuid.UUID(result["id"])


@pytest.mark.anyio
async def test_create_deviation_investigation_push_record_reloads_after_sync_state_changes(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-TRACK-RELOAD-001",
        title="偏差调查推送重载测试",
        status="pending_investigation",
    )
    db_session.add(deviation)
    await db_session.commit()
    monkeypatch.setattr(
        tracking_service.repository,
        "get_deviation_by_id",
        AsyncMock(return_value=deviation),
    )
    monkeypatch.setattr(
        tracking_service,
        "_resolve_selected_submitter_contact",
        AsyncMock(
            return_value={
                "name": "张起智",
                "open_id": "ou_submitter_001",
                "department": "AI创新部",
                "department_head_name": "张起智",
            }
        ),
    )

    async def _fake_auto_sync(_db: AsyncSession, record_id: uuid.UUID) -> None:
        record = await tracking_service.repository.get_deviation_investigation_push_record_by_id(
            _db, record_id
        )
        assert record is not None
        record.feishu_sync_status = "synced"
        record.feishu_base_record_id = "rec_fake_sync_001"
        await _db.commit()
        _db.expire(record, ["updated_at"])

    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_deviation_investigation_push_record_after_write",
        _fake_auto_sync,
    )

    result = await tracking_service.create_deviation_investigation_push_record(
        db_session,
        CreateDeviationInvestigationPushRecordRequest(
            deviation_id=deviation.id,
            push_round="第1次",
            investigation_report_url="https://example.com/report-reload.pdf",
            submitted_at=datetime(2026, 7, 4, 11, 9, tzinfo=timezone.utc),
            submitter_open_id="ou_submitter_001",
        ),
        "system",
    )

    assert result["deviation_code"] == "DEV-TRACK-RELOAD-001"
    assert result["feishu_sync_status"] == "synced"
    assert result["feishu_base_record_id"] == "rec_fake_sync_001"
    assert result["updated_at"] is not None


@pytest.mark.anyio
async def test_update_capa_plan_track_triggers_auto_sync(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-AUTO-TRACK-001",
        status="draft",
        title="自动同步计划跟踪",
    )
    db_session.add(capa)
    await db_session.commit()

    auto_sync_mock = AsyncMock()
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_capa_plan_track_after_write",
        auto_sync_mock,
    )

    create_result = await tracking_service.create_capa_plan_track(
        db_session,
        CreateCapaPlanTrackRequest(
            capa_id=capa.id,
            plan_content="建立自动同步测试计划",
            reminder_status="pending",
        ),
        "system",
    )
    track_id = uuid.UUID(create_result["id"])
    auto_sync_mock.reset_mock()

    result = await tracking_service.update_capa_plan_track(
        db_session,
        track_id,
        UpdateCapaPlanTrackRequest(progress="completed"),
        "system",
    )

    assert result["progress"] == "completed"
    assert auto_sync_mock.await_count == 1
    assert auto_sync_mock.await_args.args[0] is db_session
    assert auto_sync_mock.await_args.args[1] == track_id
