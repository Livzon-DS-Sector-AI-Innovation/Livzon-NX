from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.encryption import decrypt_api_key
from app.modules.quality import repository
from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.change_control import ChangeControl
from app.modules.quality.models.contacts import DepartmentContact
from app.modules.quality.models.deviation_investigation_push_record import (
    DeviationInvestigationPushRecord,
)
from app.modules.quality.models.deviations import Deviation
from app.modules.quality.schemas.capa import UpdateCapaRequest
from app.modules.quality.schemas.deviations import CreateDeviationRequest
from app.modules.quality.schemas.feishu_settings import (
    UpdateQualityFeishuAppSettingsRequest,
    UpdateQualityFeishuEntitySettingRequest,
)
from app.modules.quality.service import quality_feishu_pages
from app.modules.quality.service import (
    quality_feishu_settings as feishu_settings_service,
)
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service import quality_management as service
from app.platform.identity.models import User
from app.platform.integrations.feishu import bitable as feishu_bitable


@pytest.fixture(autouse=True)
async def _ensure_quality_sync_columns(db_session: AsyncSession) -> AsyncIterator[Any]:
    statements = [
        """
        ALTER TABLE quality.deviations
        ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT
        'pending',
        ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
        ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
        ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
        """,
        """
        ALTER TABLE quality.capas
        ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT
        'pending',
        ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
        ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
        ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
        """,
        """
        ALTER TABLE quality.capa_plan_tracks
        ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT
        'pending',
        ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
        ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
        ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
        """,
        """
        ALTER TABLE quality.deviation_investigation_push_records
        ADD COLUMN IF NOT EXISTS feishu_base_table_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_base_record_id VARCHAR(100),
        ADD COLUMN IF NOT EXISTS feishu_sync_status VARCHAR(20) NOT NULL DEFAULT
        'pending',
        ADD COLUMN IF NOT EXISTS feishu_last_sync_error TEXT,
        ADD COLUMN IF NOT EXISTS feishu_last_sync_direction VARCHAR(20),
        ADD COLUMN IF NOT EXISTS feishu_synced_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS feishu_source_updated_at TIMESTAMPTZ
        """,
    ]
    for statement in statements:
        await db_session.execute(text(statement))
    await db_session.execute(DepartmentContact.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(
        text("DELETE FROM quality.deviation_investigation_push_records")
    )
    await db_session.execute(text("DELETE FROM quality.capa_plan_tracks"))
    await db_session.execute(CAPA.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()
    yield
    await db_session.execute(
        text("DELETE FROM quality.deviation_investigation_push_records")
    )
    await db_session.execute(text("DELETE FROM quality.capa_plan_tracks"))
    await db_session.execute(CAPA.__table__.delete())  # type: ignore[attr-defined]
    await db_session.execute(Deviation.__table__.delete())  # type: ignore[attr-defined]
    await db_session.commit()


@pytest.mark.anyio
async def test_generate_monthly_deviation_code_uses_feishu_first_code_when_month_empty(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)

    monkeypatch.setattr(
        service,
        "_search_deviation_report_record_codes_from_feishu",
        AsyncMock(return_value=[]),
    )

    code = await service._generate_monthly_deviation_code(db_session, now)

    assert code == "PC-2607001"


@pytest.mark.anyio
async def test_generate_monthly_deviation_code_uses_max_code_from_feishu(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)

    monkeypatch.setattr(
        service,
        "_search_deviation_report_record_codes_from_feishu",
        AsyncMock(
            return_value=[
                "PC-2607001",
                "PC-2607008",
                "DEV-20260703-legacy",
                "PC-2606999",
            ]
        ),
    )

    code = await service._generate_monthly_deviation_code(db_session, now)

    assert code == "PC-2607009"


@pytest.mark.anyio
async def test_generate_monthly_deviation_code_resets_each_month(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)

    monkeypatch.setattr(
        service,
        "_search_deviation_report_record_codes_from_feishu",
        AsyncMock(return_value=["PC-2607012", "PC-2607013"]),
    )

    code = await service._generate_monthly_deviation_code(db_session, now)

    assert code == "PC-2608001"


@pytest.mark.anyio
async def test_generate_monthly_deviation_code_fails_when_report_records_unavailable(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)

    monkeypatch.setattr(
        service,
        "_search_deviation_report_record_codes_from_feishu",
        AsyncMock(side_effect=ValueError("报告记录实体未配置")),
    )

    with pytest.raises(ValueError, match="无法从飞书报告记录表生成偏差编号"):
        await service._generate_monthly_deviation_code(db_session, now)


@pytest.mark.anyio
async def test_get_deviation_list_delegates_filters_to_repository(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-20260701-0001",
        title="过滤器破损",
        status="pending_investigation",
        created_at=now,
        updated_at=now,
    )
    linked_capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-20260701-0001",
        title="更换过滤器",
        status="open",
        created_at=now,
        updated_at=now,
    )
    repo_mock: Any = AsyncMock(return_value=([deviation], 1))
    monkeypatch.setattr(service.repository, "get_deviations", repo_mock)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        service.repository,  # type: ignore[attr-defined]
        "get_related_capas_for_deviation",
        AsyncMock(return_value=[linked_capa]),
    )

    result = await service.get_deviation_list(
        db_session,
        status="pending_investigation",
        level="major",
        department="质量部",
        keyword="100%_批",
        deviation_code="DEV-20260701",
        product_keyword="原料A",
        has_occurred_before=True,
        is_closed=False,
        investigation_completed_from="2026-07-01T00:00:00+00:00",
        investigation_completed_to="2026-07-02T00:00:00+00:00",
        root_cause_keyword="阀门",
        corrective_actions_keyword="更换",
        page=2,
        page_size=5,
    )

    kwargs = repo_mock.await_args.kwargs
    assert kwargs["keyword"] == "100%_批"
    assert kwargs["investigation_completed_from"] == datetime(
        2026, 7, 1, 0, 0, tzinfo=UTC
    )
    assert kwargs["investigation_completed_to"] == datetime(
        2026, 7, 3, 0, 0, tzinfo=UTC
    )
    assert kwargs["page"] == 2
    assert kwargs["page_size"] == 5
    assert result["total"] == 1
    assert result["items"][0]["deviation_code"] == "DEV-20260701-0001"
    assert result["items"][0]["related_capa_codes"] == ["CAPA-20260701-0001"]
    assert result["items"][0]["related_capas"] == [
        {"id": linked_capa.id, "capa_code": "CAPA-20260701-0001"}
    ]


@pytest.mark.anyio
async def test_get_change_list_builds_action_plan_counts(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    change = ChangeControl(
        id=uuid.uuid4(),
        serial_number="1",
        change_code="BG-2026-001",
        applicant_department="质量部",
        change_object="反应釜",
        change_content="更换密封件",
        change_level="一级",
        created_at=now,
        updated_at=now,
    )
    get_changes_mock: Any = AsyncMock(return_value=([change], 1))
    get_counts_mock: Any = AsyncMock(return_value={str(change.id): 3})
    monkeypatch.setattr(service.repository, "get_changes", get_changes_mock)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        service.repository,  # type: ignore[attr-defined]
        "get_change_action_plan_counts_by_change_ids",
        get_counts_mock,
    )

    result = await service.get_change_list(
        db_session,
        change_code="BG-2026",
        application_date_from="2026-07-01",
        page=1,
        page_size=10,
    )

    assert (
        get_changes_mock.await_args.kwargs["application_date_from"]
        == datetime(2026, 7, 1, 0, 0).date()
    )
    assert result["items"][0]["change_code"] == "BG-2026-001"
    assert result["items"][0]["action_plan_count"] == 3


@pytest.mark.anyio
async def test_get_capa_list_converts_datetime_range_before_query(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-2026-001",
        title="纠正预防措施",
        status="open",
        deviation_id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )
    repo_mock: Any = AsyncMock(return_value=([capa], 1))
    monkeypatch.setattr(service.repository, "get_capas", repo_mock)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        service.repository,  # type: ignore[attr-defined]
        "get_capa_plan_tracks_by_capa_ids",
        AsyncMock(return_value=[]),
    )

    result = await service.get_capa_list(
        db_session,
        status="open",
        closure_date_from="2026-07-01T00:00:00+00:00",
        closure_date_to="2026-07-02T00:00:00+00:00",
        page=1,
        page_size=10,
    )

    kwargs = repo_mock.await_args.kwargs
    assert kwargs["closure_date_from"] == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    assert kwargs["closure_date_to"] == datetime(2026, 7, 3, 0, 0, tzinfo=UTC)
    assert result["items"][0]["capa_code"] == "CAPA-2026-001"
    assert result["items"][0]["deviation_id"] == capa.deviation_id
    assert result["items"][0]["linked_plan_tracks"] == []


@pytest.mark.anyio
async def test_get_deviation_report_record_list_reads_feishu_report_records(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 1, 8, 0, tzinfo=UTC)
    linked_deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-20260701-0101",
        title="本地偏差详情",
        department="质量部",
        status="pending_investigation",
        created_at=now,
        updated_at=now,
    )

    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            (
                "deviation_report_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_report",
                table_id="tbl_report_real",
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
    ) -> list[dict[Any, Any]]:
        assert entity_code == "deviation_report_record"
        assert table_id is None
        assert filter_str is None
        return [
            {
                "record_id": "rec_report_001",
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "DEV-20260701-0101",
                    "报告时间": int(
                        datetime(2026, 7, 2, 10, 0, tzinfo=UTC).timestamp() * 1000
                    ),
                    "偏差内容": "洁净区压差异常",
                    "偏差报告": "https://example.com/report-1.docx",
                    "涉及产品名称/批号": "原料A/B-001",
                    "部门": "质量部",
                    "报告人": "报告人甲",
                    "部门负责人": {
                        "type": 11,
                        "value": [
                            {
                                "name": "部门负责人甲",
                            }
                        ],
                    },
                    "部门负责人确认": "是",
                    "QA": "QA甲",
                    "QA确认": "否",
                    "QA负责人": "QA负责人甲",
                    "QA负责人确认": "是",
                    "报告状态": "已完成",
                },
            },
            {
                "record_id": "rec_report_002",
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "DEV-20260701-9999",
                    "报告时间": int(now.timestamp() * 1000),
                    "偏差内容": "纯飞书记录",
                    "部门": "生产部",
                },
            },
            {
                "record_id": "rec_report_003",
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "DEV-20260701-8888",
                    "报告时间": int(now.timestamp() * 1000),
                    "QA确认": True,
                    "QA负责人确认": True,
                    "部门负责人确认": False,
                },
            },
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync, "search_records", fake_search_records
    )

    db_session.add(linked_deviation)
    await db_session.commit()

    result = await service.get_deviation_report_record_list(
        db_session,
        page=1,
        page_size=20,
    )

    first_item = result["items"][0]
    assert first_item["id"] == "rec_report_001"
    assert first_item["deviation_id"] == linked_deviation.id
    assert first_item["deviation_code"] == "DEV-20260701-0101"
    assert first_item["description"] == "洁净区压差异常"
    assert first_item["report_document"] == "https://example.com/report-1.docx"
    assert first_item["product_batch"] == "原料A/B-001"
    assert first_item["reporter_name"] == "报告人甲"
    assert first_item["department_head"] == "部门负责人甲"
    assert first_item["qa_head_name"] == "QA负责人甲"
    assert first_item["qa_result"] == "rejected"
    assert first_item["report_status"] == "已完成"
    assert first_item["report_time"] == datetime(2026, 7, 2, 10, 0, tzinfo=UTC)
    assert first_item["feishu_base_table_id"] == "tbl_report_real"
    assert first_item["feishu_base_record_id"] == "rec_report_001"

    second_item = result["items"][1]
    assert second_item["id"] == "rec_report_002"
    assert second_item["deviation_id"] is None
    assert second_item["deviation_code"] == "DEV-20260701-9999"
    assert second_item["description"] == "纯飞书记录"
    assert second_item["department"] == "生产部"
    assert second_item["department_head"] is None
    assert second_item["qa_name"] is None
    assert second_item["report_time"] == now

    third_item = result["items"][2]
    assert third_item["id"] == "rec_report_003"
    assert third_item["department_head_result"] == "rejected"
    assert third_item["qa_result"] == "approved"
    assert third_item["qa_head_result"] == "approved"


@pytest.mark.anyio
async def test_get_quality_sync_conflicts_returns_recent_conflicts(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 7, 3, 8, 0, tzinfo=UTC)
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-CONFLICT-001",
        title="偏差冲突记录",
        status="pending_investigation",
        feishu_sync_status="conflict",
        feishu_last_sync_error="检测到系统与飞书 Base 均已更新",
        feishu_last_sync_direction="base_to_system",
        feishu_base_table_id="tbl_deviation",
        feishu_base_record_id="rec_dev_conflict",
        feishu_synced_at=now,
        feishu_source_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-CONFLICT-001",
        title="CAPA冲突记录",
        status="open",
        feishu_sync_status="conflict",
        feishu_last_sync_error="检测到系统与飞书 Base 均已更新",
        feishu_last_sync_direction="system_to_base",
        feishu_base_table_id="tbl_capa",
        feishu_base_record_id="rec_capa_conflict",
        feishu_synced_at=now,
        feishu_source_updated_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([deviation, capa])
    await db_session.commit()

    result = await feishu_sync_service.get_quality_sync_conflicts(db_session, limit=10)

    assert len(result) == 2
    assert result[0]["record_code"] in {"DEV-CONFLICT-001", "CAPA-CONFLICT-001"}
    deviation_item = next(item for item in result if item["entity_type"] == "deviation")
    capa_item = next(item for item in result if item["entity_type"] == "capa")
    assert deviation_item["route_path"] == "/quality/deviations"
    assert deviation_item["feishu_last_sync_direction"] == "base_to_system"
    assert capa_item["route_path"] == "/quality/capas"
    assert capa_item["feishu_last_sync_direction"] == "system_to_base"


@pytest.mark.anyio
async def test_pull_quality_records_from_feishu_updates_push_record_snapshot(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 8, 0, tzinfo=UTC)
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-PULL-001",
        title="回拉报告记录",
        status="pending_investigation",
        created_at=now,
        updated_at=now,
    )
    push_record = DeviationInvestigationPushRecord(
        id=uuid.uuid4(),
        deviation_id=deviation.id,
        deviation_code=deviation.deviation_code,
        push_round="第2次",
        submitter="本地提交人",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([deviation, push_record])
    await db_session.commit()

    async def _fake_search_records(
        _db: AsyncSession,
        entity_code: str,
        table_id: str,
        *,
        filter_str: str | None = None,
    ) -> list[dict[Any, Any]]:
        if entity_code == "deviation_investigation_push_record":
            return [
                {
                    "record_id": "rec_report_pull_001",
                    "last_modified_time": int(now.timestamp() * 1000),
                    "fields": {
                        "偏差编号": "DEV-PULL-001",
                        "第N次推送": "第2次",
                        "提交日期": int(now.timestamp() * 1000),
                        "偏差调查报告": "https://example.com/pull-report.pdf",
                        "提交人": "飞书报告人",
                        "部门负责人": "飞书部门负责人",
                        "部门负责人审核结果": "通过",
                        "QA": "飞书QA",
                        "QA审核结果": "通过",
                        "QA负责人": "飞书QA负责人",
                        "QA负责人审核结果": "不通过",
                    },
                }
            ]
        return []

    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_dev",
                table_id="tbl_dev",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            "capa_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_capa",
                table_id="tbl_capa",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            "capa_plan_track": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_plan",
                table_id="tbl_plan",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            (
                "deviation_investigation_push_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_report",
                table_id="tbl_push",
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
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        _fake_search_records,
    )

    result = await feishu_sync_service.pull_quality_records_from_feishu(db_session)

    await db_session.refresh(push_record)
    assert result == {
        "entity_code": None,
        "entity_label": None,
        "synced": 1,
        "failed": 0,
        "conflicts": 0,
    }
    assert push_record.submitter == "飞书报告人"
    assert push_record.department_head == "飞书部门负责人"
    assert push_record.department_head_result == "approved"
    assert push_record.qa_name == "飞书QA"
    assert push_record.qa_result == "approved"
    assert push_record.qa_head_name == "飞书QA负责人"
    assert push_record.qa_head_result == "rejected"
    assert push_record.feishu_base_record_id == "rec_report_pull_001"
    assert push_record.feishu_last_sync_direction == "base_to_system"


@pytest.mark.anyio
async def test_pull_quality_records_reuses_deviation_on_duplicate(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 30, tzinfo=UTC)
    existing = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-DUP-001",
        title="已存在偏差",
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db_session.add(existing)
    await db_session.commit()

    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_dev",
                table_id="tbl_dev_dup",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            "capa_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_capa",
                table_id="tbl_capa_dup",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            "capa_plan_track": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_plan",
                table_id="tbl_plan_dup",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            (
                "deviation_investigation_push_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_report",
                table_id="tbl_push_dup",
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
        table_id: str,
        *,
        filter_str: str | None = None,
    ) -> list[dict[Any, Any]]:
        if entity_code == "deviation_ledger":
            return [
                {
                    "record_id": "rec_dev_dup_001",
                    "last_modified_time": int(now.timestamp() * 1000),
                    "fields": {
                        "偏差编号": "DEV-DUP-001",
                        "偏差简要描述": "飞书重复偏差",
                        "产品名称/批号": "BATCH-001",
                    },
                }
            ]
        return []

    create_deviation_mock: Any = AsyncMock(
        side_effect=IntegrityError(
            "INSERT", {"deviation_code": "DEV-DUP-001"}, Exception("duplicate")
        )
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync, "search_records", fake_search_records
    )
    monkeypatch.setattr(repository, "create_deviation", create_deviation_mock)

    result = await feishu_sync_service.pull_quality_records_from_feishu(db_session)

    await db_session.refresh(existing)
    assert result == {
        "entity_code": None,
        "entity_label": None,
        "synced": 1,
        "failed": 0,
        "conflicts": 0,
    }
    assert existing.feishu_base_table_id == "tbl_dev_dup"
    assert existing.feishu_base_record_id == "rec_dev_dup_001"
    assert existing.feishu_last_sync_direction == "base_to_system"


@pytest.mark.anyio
async def test_upsert_record_maps_push_fields_and_search_filter(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_deviation",
                table_id="tbl_deviation_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={
                    "偏差编号": "偏差编码",
                    "根本原因": "真实原因",
                },
            )
        },
    )

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    async def fake_list_fields(self: Any, table_id: str) -> list[dict[Any, Any]]:
        assert table_id == "tbl_deviation_real"
        return [
            {"field_name": "偏差编码", "type": 1},
            {"field_name": "真实原因", "type": 1},
        ]

    search_mock: Any = AsyncMock(return_value=[])
    create_calls: list[tuple[str, dict[str, object]]] = []

    async def fake_create_record(
        self: Any, table_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        create_calls.append((table_id, fields))
        return {"record_id": "rec_mapped_deviation"}

    monkeypatch.setattr(feishu_bitable.BitableClient, "list_fields", fake_list_fields)
    monkeypatch.setattr(feishu_bitable.BitableClient, "search_records", search_mock)
    monkeypatch.setattr(
        feishu_bitable.BitableClient, "create_record", fake_create_record
    )

    record_id, table_id = await feishu_sync_service.feishu_sync._upsert_record(
        db_session,
        "deviation_ledger",
        None,
        None,
        {"偏差编号": "DEV-MAP-001", "根本原因": "飞书字段映射"},
        search_conditions=[("偏差编号", "DEV-MAP-001")],
    )

    assert record_id == "rec_mapped_deviation"
    assert table_id == "tbl_deviation_real"
    assert (
        search_mock.await_args.kwargs["filter_str"]
        == 'CurrentValue.[偏差编码] = "DEV-MAP-001"'
    )
    assert create_calls == [
        (
            "tbl_deviation_real",
            {"偏差编码": "DEV-MAP-001", "真实原因": "飞书字段映射"},
        )
    ]


@pytest.mark.anyio
async def test_pull_quality_records_from_feishu_reads_mapped_report_fields(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-PULL-MAP-001",
        title="回拉映射报告记录",
        status="pending_investigation",
        created_at=now,
        updated_at=now,
    )
    push_record = DeviationInvestigationPushRecord(
        id=uuid.uuid4(),
        deviation_id=deviation.id,
        deviation_code=deviation.deviation_code,
        push_round="第1次",
        submitter="本地提交人",
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([deviation, push_record])
    await db_session.commit()

    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_dev",
                table_id="tbl_dev",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            "capa_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_capa",
                table_id="tbl_capa",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            "capa_plan_track": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_plan",
                table_id="tbl_plan",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={},
            ),
            (
                "deviation_investigation_push_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_report",
                table_id="tbl_push_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={
                    "偏差编号": "偏差编码",
                    "第N次推送": "推送轮次",
                    "提交日期": "上报时间",
                    "偏差调查报告": "报告链接",
                    "提交人": "提交人",
                    "部门负责人": "部门复核人",
                    "部门负责人审核结果": "部门复核结果",
                    "QA": "质量人员",
                    "QA审核结果": "质量确认结果",
                    "QA负责人": "质量负责人",
                    "QA负责人审核结果": "质量负责人结果",
                },
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
        table_id: str,
        *,
        filter_str: str | None = None,
    ) -> list[dict[Any, Any]]:
        if entity_code == "deviation_investigation_push_record":
            return [
                {
                    "record_id": "rec_push_mapped_001",
                    "last_modified_time": int(now.timestamp() * 1000),
                    "fields": {
                        "偏差编码": "DEV-PULL-MAP-001",
                        "推送轮次": "第1次",
                        "上报时间": int(now.timestamp() * 1000),
                        "报告链接": "https://example.com/mapped-report.pdf",
                        "提交人": "飞书映射提交人",
                        "部门复核人": "飞书部门复核",
                        "部门复核结果": "通过",
                        "质量人员": "飞书质量",
                        "质量确认结果": "不通过",
                        "质量负责人": "飞书质量负责人",
                        "质量负责人结果": "通过",
                    },
                }
            ]
        return []

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync, "search_records", fake_search_records
    )

    result = await feishu_sync_service.pull_quality_records_from_feishu(db_session)

    await db_session.refresh(push_record)
    assert result == {
        "entity_code": None,
        "entity_label": None,
        "synced": 1,
        "failed": 0,
        "conflicts": 0,
    }
    assert push_record.submitter == "飞书映射提交人"
    assert push_record.department_head == "飞书部门复核"
    assert push_record.department_head_result == "approved"
    assert push_record.qa_name == "飞书质量"
    assert push_record.qa_result == "rejected"
    assert push_record.qa_head_name == "飞书质量负责人"
    assert push_record.qa_head_result == "approved"
    assert push_record.feishu_base_table_id == "tbl_push_real"
    assert push_record.feishu_base_record_id == "rec_push_mapped_001"


@pytest.mark.anyio
async def test_pull_quality_records_from_feishu_supports_single_report_record_entity(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            (
                "deviation_report_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_report_record",
                table_id="tbl_report_record",
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
        table_id: str | None,
        *,
        filter_str: str | None = None,
    ) -> list[dict[Any, Any]]:
        assert entity_code == "deviation_report_record"
        assert table_id is None
        return [
            {
                "record_id": "rec_report_001",
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {"偏差编号": "PC-2607001"},
            },
            {
                "record_id": "rec_report_002",
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {"偏差编号": "PC-2607002"},
            },
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )

    result = await feishu_sync_service.pull_quality_records_from_feishu(
        db_session,
        entity_code="deviation_report_record",
    )

    assert result == {
        "entity_code": "deviation_report_record",
        "entity_label": "报告记录",
        "synced": 2,
        "failed": 0,
        "conflicts": 0,
    }


@pytest.mark.anyio
async def test_pull_investigation_push_counts_remote_without_local_create(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 10, 0, tzinfo=UTC)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            (
                "deviation_investigation_push_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
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
    ) -> list[dict[Any, Any]]:
        if entity_code == "deviation_investigation_push_record":
            return [
                {
                    "record_id": "rec_push_missing_001",
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
                        "QA负责人审核结果": "不通过",
                    },
                }
            ]
        return []

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )

    result = await feishu_sync_service.pull_quality_records_from_feishu(
        db_session,
        entity_code="deviation_investigation_push_record",
    )

    assert result == {
        "entity_code": "deviation_investigation_push_record",
        "entity_label": "调查推送",
        "synced": 1,
        "failed": 0,
        "conflicts": 0,
    }
    deviation = await repository.get_deviation_by_code(db_session, "PC-2602001")
    records, total = await repository.get_deviation_investigation_push_records(
        db_session,
        deviation_code="PC-2602001",
        page=1,
        page_size=10,
    )
    assert deviation is None
    assert total == 0
    assert records == []


@pytest.mark.anyio
async def test_pull_quality_records_from_feishu_rejects_unknown_entity_code(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={},
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    with pytest.raises(ValueError, match="不支持的飞书回拉实体"):
        await feishu_sync_service.pull_quality_records_from_feishu(
            db_session,
            entity_code="unknown_entity",
        )


@pytest.mark.anyio
async def test_entity_settings_prefill_change_and_validation_sources(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    monkeypatch.setattr(
        feishu_settings_service.settings, "FEISHU_APP_ID", "cli_app_seeded"
    )
    monkeypatch.setattr(
        feishu_settings_service.settings, "FEISHU_APP_SECRET", "cli_secret_seeded"
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_FEISHU_APP_TOKEN",
        "test-quality-app-token",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_FEISHU_DEVIATION_INVESTIGATION_PUSH_TABLE_ID",
        "tblizEvuhtSPFDni",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_CHANGE_LEDGER_FEISHU_APP_TOKEN",
        "WwXnbkC8waxuzBsEbuWc6DAUnZg",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_CHANGE_LEDGER_FEISHU_TABLE_ID",
        "tblSDbnr2D7wk2b0",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_VALIDATION_FEISHU_APP_TOKEN",
        "EZUib0hvTa7lnfsz9xScjFpAnvc",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_VALIDATION_FEISHU_TABLE_ID",
        "tblQeNmOWMCAaLrX",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_DEPARTMENT_CONTACT_FEISHU_APP_TOKEN",
        "DL2DbLU08auoEZs8kXAcLBPUnhg",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_DEPARTMENT_CONTACT_FEISHU_TABLE_ID",
        "tblDq7JM4ibtL4MO",
    )

    app_settings = await feishu_settings_service.get_quality_feishu_app_settings(
        db_session
    )
    entity_items = await feishu_settings_service.list_quality_feishu_entity_settings(
        db_session
    )
    entity_map = {item.entity_code: item for item in entity_items}

    assert app_settings.app_id == "cli_app_seeded"

    push_item = entity_map["deviation_investigation_push_record"]
    assert push_item.app_token == "test-quality-app-token"
    assert push_item.base_table_id == "tblizEvuhtSPFDni"
    assert push_item.base_table_name == "偏差调查推送记录"
    assert push_item.is_enabled is True

    change_item = entity_map["change_ledger"]
    assert change_item.app_token == "WwXnbkC8waxuzBsEbuWc6DAUnZg"
    assert change_item.base_table_id == "tblSDbnr2D7wk2b0"
    assert change_item.base_table_name == "变更总表"
    assert change_item.is_enabled is True

    validation_item = entity_map["validation_process"]
    assert validation_item.app_token == "EZUib0hvTa7lnfsz9xScjFpAnvc"
    assert validation_item.base_table_id == "tblQeNmOWMCAaLrX"
    assert validation_item.base_table_name == "验证总表"
    assert (
        validation_item.source_note
        == "验证与确认共用同一张飞书源表，平台按验证类型截取到不同模块。"
    )
    assert validation_item.is_enabled is True

    contact_item = entity_map["department_contact"]
    assert contact_item.app_token == "DL2DbLU08auoEZs8kXAcLBPUnhg"
    assert contact_item.base_table_id == "tblDq7JM4ibtL4MO"
    assert contact_item.base_table_name == "部门联系人"
    assert contact_item.is_enabled is True


@pytest.mark.anyio
async def test_get_quality_feishu_app_settings_does_not_backfill_existing_db_config(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="db_app_id",
            app_secret="db_secret",
            is_enabled=False,
        ),
    )
    monkeypatch.setattr(feishu_settings_service.settings, "FEISHU_APP_ID", "env_app_id")
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "FEISHU_APP_SECRET",
        "env_app_secret",
    )

    detail = await feishu_settings_service.get_quality_feishu_app_settings(db_session)
    model = await feishu_settings_service._get_app_settings_model(db_session)

    assert detail.app_id == "db_app_id"
    assert detail.is_enabled is False
    assert model is not None
    assert model.app_id == "db_app_id"
    assert decrypt_api_key(model.app_secret) == "db_secret"


@pytest.mark.anyio
async def test_get_quality_feishu_app_settings_reads_saved_db_config_after_reload(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    saved = await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="cli_saved_app_id",
            app_secret="saved_secret_value",
            is_enabled=True,
        ),
    )
    monkeypatch.setattr(feishu_settings_service.settings, "FEISHU_APP_ID", "env_app_id")
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "FEISHU_APP_SECRET",
        "env_app_secret",
    )

    loaded = await feishu_settings_service.get_quality_feishu_app_settings(db_session)

    assert loaded.app_id == "cli_saved_app_id"
    assert loaded.app_secret_masked == saved.app_secret_masked
    assert loaded.is_enabled is True


@pytest.mark.anyio
async def test_update_quality_feishu_app_settings_keeps_secret_when_mask_submitted(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    detail = await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="db_app_id",
            app_secret="db_secret",
            is_enabled=True,
        ),
    )

    await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="db_app_id_updated",
            app_secret=detail.app_secret_masked or "",
            is_enabled=False,
        ),
    )
    model = await feishu_settings_service._get_app_settings_model(db_session)

    assert model is not None
    assert model.app_id == "db_app_id_updated"
    assert model.is_enabled is False
    assert decrypt_api_key(model.app_secret) == "db_secret"


@pytest.mark.anyio
async def test_entity_settings_preserve_existing_db_bindings(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    await feishu_settings_service.list_quality_feishu_entity_settings(db_session)
    await feishu_settings_service.update_quality_feishu_entity_setting(
        db_session,
        "change_ledger",
        UpdateQualityFeishuEntitySettingRequest(
            app_token="db_app_token",
            base_table_name="DB 变更总表",
            base_table_id="tbl_db_change",
            is_enabled=True,
            enable_push_to_feishu=False,
            enable_pull_from_feishu=True,
        ),
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_CHANGE_LEDGER_FEISHU_APP_TOKEN",
        "env_app_token",
    )
    monkeypatch.setattr(
        feishu_settings_service.settings,
        "QUALITY_CHANGE_LEDGER_FEISHU_TABLE_ID",
        "tbl_env_change",
    )

    entity_items = await feishu_settings_service.list_quality_feishu_entity_settings(
        db_session
    )
    entity_map = {item.entity_code: item for item in entity_items}
    change_item = entity_map["change_ledger"]

    assert change_item.app_token == "db_app_token"
    assert change_item.base_table_id == "tbl_db_change"
    assert change_item.base_table_name == "DB 变更总表"
    assert change_item.is_enabled is True
    assert change_item.enable_push_to_feishu is False
    assert change_item.enable_pull_from_feishu is True


@pytest.mark.anyio
async def test_list_quality_feishu_tables_uses_platform_bitable_client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="db_app_id",
            app_secret="db_secret",
            is_enabled=True,
        ),
    )

    class FakeBitableClient:
        async def list_tables(self: Any, page_size: int = 100) -> list[dict[Any, Any]]:
            assert page_size == 100
            return [
                {"table_id": "tbl_deviation", "name": "偏差台账"},
                {"table_id": "", "name": "无效表"},
                {"table_id": "tbl_empty_name", "name": ""},
            ]

    def fake_build_bitable_client(
        *,
        app_token: str | None,
        app_id: str | None,
        app_secret: str | None,
    ) -> FakeBitableClient:
        assert app_token == "basc_override"
        assert app_id == "db_app_id"
        assert app_secret == "db_secret"
        return FakeBitableClient()

    monkeypatch.setattr(
        feishu_settings_service,
        "build_bitable_client",
        fake_build_bitable_client,
    )

    tables = await feishu_settings_service.list_quality_feishu_tables(
        db_session,
        "deviation_ledger",
        app_token="basc_override",
    )

    assert [item.model_dump() for item in tables] == [
        {"table_id": "tbl_deviation", "table_name": "偏差台账"},
    ]


@pytest.mark.anyio
async def test_list_quality_feishu_tables_filters_by_base_table_id(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="db_app_id",
            app_secret="db_secret",
            is_enabled=True,
        ),
    )

    class FakeBitableClient:
        async def list_tables(self: Any, page_size: int = 100) -> list[dict[Any, Any]]:
            return [
                {"table_id": "tbl_other", "name": "其他表"},
                {"table_id": "tbl_target", "name": "目标表"},
            ]

    monkeypatch.setattr(
        feishu_settings_service,
        "build_bitable_client",
        lambda **_: FakeBitableClient(),
    )

    tables = await feishu_settings_service.list_quality_feishu_tables(
        db_session,
        "deviation_ledger",
        app_token="basc_override",
        table_id="tbl_target",
    )

    assert [item.model_dump() for item in tables] == [
        {"table_id": "tbl_target", "table_name": "目标表"},
    ]


@pytest.mark.anyio
async def test_list_quality_feishu_tables_wraps_feishu_errors(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    await feishu_settings_service.update_quality_feishu_app_settings(
        db_session,
        UpdateQualityFeishuAppSettingsRequest(
            app_id="db_app_id",
            app_secret="db_secret",
            is_enabled=True,
        ),
    )

    class FailingBitableClient:
        async def list_tables(self: Any, page_size: int = 100) -> list[dict[Any, Any]]:
            raise RuntimeError("invalid app_token")

    def fake_build_bitable_client(
        *,
        app_token: str | None,
        app_id: str | None,
        app_secret: str | None,
    ) -> FailingBitableClient:
        return FailingBitableClient()

    monkeypatch.setattr(
        feishu_settings_service,
        "build_bitable_client",
        fake_build_bitable_client,
    )

    with pytest.raises(ValueError, match="读取飞书表列表失败：invalid app_token"):
        await feishu_settings_service.list_quality_feishu_tables(
            db_session,
            "deviation_ledger",
            app_token="basc_override",
        )


@pytest.mark.anyio
async def test_update_quality_feishu_entity_setting_resolves_bitable_url(
    db_session: AsyncSession,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    item = await feishu_settings_service.update_quality_feishu_entity_setting(
        db_session,
        "deviation_ledger",
        UpdateQualityFeishuEntitySettingRequest(
            app_token="https://example.feishu.cn/base/basc_from_url?table=tbl_from_url",
            base_table_name="偏差台账",
            base_table_id="",
            is_enabled=True,
            enable_push_to_feishu=True,
            enable_pull_from_feishu=True,
        ),
    )

    assert item.app_token == "basc_from_url"
    assert item.base_table_id == "tbl_from_url"


@pytest.mark.anyio
async def test_update_quality_feishu_entity_setting_refreshes_enabled_report_records(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    pull_mock: Any = AsyncMock(
        return_value={
            "entity_code": "deviation_report_record",
            "synced": 2,
            "failed": 0,
            "conflicts": 0,
        }
    )
    monkeypatch.setattr(
        feishu_sync_service,
        "pull_quality_records_from_feishu",
        pull_mock,
    )

    item = await feishu_settings_service.update_quality_feishu_entity_setting(
        db_session,
        "deviation_report_record",
        UpdateQualityFeishuEntitySettingRequest(
            app_token="basc_report",
            base_table_name="报告记录",
            base_table_id="tbl_report",
            is_enabled=True,
            enable_push_to_feishu=True,
            enable_pull_from_feishu=True,
        ),
    )

    pull_mock.assert_awaited_once()
    assert pull_mock.await_args.kwargs["entity_code"] == "deviation_report_record"
    assert item.last_sync_status == "success"
    assert item.last_sync_error is None
    assert item.last_synced_at is not None


@pytest.mark.anyio
async def test_update_quality_feishu_entity_setting_keeps_config_when_refresh_fails(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await db_session.execute(text("DELETE FROM quality.quality_feishu_entity_settings"))
    await db_session.execute(text("DELETE FROM quality.quality_feishu_app_settings"))
    await db_session.commit()

    pull_mock: Any = AsyncMock(
        side_effect=ValueError("invalid basc_report_token tbl_report_token")
    )
    monkeypatch.setattr(
        feishu_sync_service,
        "pull_quality_records_from_feishu",
        pull_mock,
    )

    item = await feishu_settings_service.update_quality_feishu_entity_setting(
        db_session,
        "deviation_report_record",
        UpdateQualityFeishuEntitySettingRequest(
            app_token="basc_report_token",
            base_table_name="报告记录",
            base_table_id="tbl_report_token",
            is_enabled=True,
            enable_push_to_feishu=True,
            enable_pull_from_feishu=True,
        ),
    )

    assert item.app_token == "basc_report_token"
    assert item.base_table_id == "tbl_report_token"
    assert item.last_sync_status == "failed"
    assert "basc_report_token" not in (item.last_sync_error or "")
    assert "tbl_report_token" not in (item.last_sync_error or "")


@pytest.mark.anyio
async def test_create_deviation_triggers_auto_feishu_sync(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporter_open_id = f"ou_{uuid.uuid4().hex}"
    monkeypatch.setattr(
        service,
        "get_department_contact_list_from_feishu",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "name": "测试提交人",
                        "department": "质量部",
                        "open_id": reporter_open_id,
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 1000,
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_generate_monthly_deviation_code",
        AsyncMock(return_value="PC-2607001"),
    )

    auto_sync_mock: Any = AsyncMock()
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_deviation_after_write",
        auto_sync_mock,
    )

    result = await service.create_deviation(
        db_session,
        CreateDeviationRequest(
            department="质量部",
            reporter_open_id=reporter_open_id,
            description="自动同步偏差内容",
            affected_items="产品A/批号001",
        ),
        "system",
        None,
    )

    created_deviation = await repository.get_deviation_by_id(
        db_session, uuid.UUID(result["id"])
    )

    assert result["id"]
    assert result["code"] == "PC-2607001"
    assert created_deviation is not None
    assert created_deviation.reporter_id is None
    assert created_deviation.discoverer == "测试提交人"
    assert created_deviation.department == "质量部"
    assert created_deviation.description == "自动同步偏差内容"
    assert created_deviation.affected_items == "产品A/批号001"
    assert auto_sync_mock.await_count == 1
    assert auto_sync_mock.await_args.args[0] is db_session
    assert auto_sync_mock.await_args.args[1] == uuid.UUID(result["id"])


@pytest.mark.anyio
async def test_create_deviation_requires_selected_reporter_contact(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "get_department_contact_list_from_feishu",
        AsyncMock(
            return_value={
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 1000,
            }
        ),
    )
    with pytest.raises(
        ValueError,
        match="所选报告人不存在于部门联系人台账中",
    ):
        await service.create_deviation(
            db_session,
            CreateDeviationRequest(
                department="质量部",
                reporter_open_id=f"ou_{uuid.uuid4().hex}",
                description="缺少联系人档案",
                affected_items="产品B/批号002",
            ),
            "system",
            None,
        )


@pytest.mark.anyio
async def test_create_deviation_accepts_reporter_from_feishu_contacts(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auto_sync_mock: Any = AsyncMock()
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_deviation_after_write",
        auto_sync_mock,
    )
    monkeypatch.setattr(
        service,
        "get_department_contact_list_from_feishu",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "name": "张建智",
                        "department": "AI创新部",
                        "open_id": "ou_ai_creator_001",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 1000,
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_generate_monthly_deviation_code",
        AsyncMock(return_value="PC-2607002"),
    )

    result = await service.create_deviation(
        db_session,
        CreateDeviationRequest(
            department="AI创新部",
            reporter_open_id="ou_ai_creator_001",
            description="AI创新部测试偏差",
            affected_items="测试产品/TEST-001",
        ),
        "system",
        None,
    )

    created_deviation = await repository.get_deviation_by_id(
        db_session, uuid.UUID(result["id"])
    )

    assert created_deviation is not None
    assert result["code"] == "PC-2607002"
    assert created_deviation.discoverer == "张建智"
    assert created_deviation.department == "AI创新部"
    assert auto_sync_mock.await_count == 1


@pytest.mark.anyio
async def test_create_deviation_accepts_ledger_only_fields_without_reporter_contact(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auto_sync_mock: Any = AsyncMock()
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_deviation_after_write",
        auto_sync_mock,
    )
    monkeypatch.setattr(
        service,
        "_generate_monthly_deviation_code",
        AsyncMock(return_value="PC-2607003"),
    )

    result = await service.create_deviation(
        db_session,
        CreateDeviationRequest(
            description="仅按台账字段创建",
            affected_items="物料A/批号003",
            has_occurred_before=True,
            root_cause_analysis="设备参数设置错误",
            level="major",
            corrective_actions="重新校准参数并复核",
            material_disposition="隔离待判",
            is_closed=True,
            close_time="2026-07-04T09:30:00+00:00",
        ),
        "system",
        None,
    )

    created_deviation = await repository.get_deviation_by_id(
        db_session, uuid.UUID(result["id"])
    )

    assert created_deviation is not None
    assert created_deviation.deviation_code == "PC-2607003"
    assert created_deviation.department in ("", None)
    assert created_deviation.discoverer == ""
    assert created_deviation.has_occurred_before is True
    assert created_deviation.root_cause_analysis == "设备参数设置错误"
    assert created_deviation.corrective_actions == "重新校准参数并复核"
    assert created_deviation.material_disposition == "隔离待判"
    assert created_deviation.status == "closed"
    assert created_deviation.status_updated_at == datetime(
        2026, 7, 4, 9, 30, tzinfo=UTC
    )
    assert auto_sync_mock.await_count == 1


@pytest.mark.anyio
async def test_create_deviation_fails_when_feishu_code_source_unavailable(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "get_department_contact_list_from_feishu",
        AsyncMock(
            return_value={
                "items": [
                    {
                        "name": "测试提交人",
                        "department": "质量部",
                        "open_id": "ou_reporter_001",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 1000,
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_generate_monthly_deviation_code",
        AsyncMock(side_effect=ValueError("无法从飞书报告记录表生成偏差编号")),
    )

    with pytest.raises(ValueError, match="无法从飞书报告记录表生成偏差编号"):
        await service.create_deviation(
            db_session,
            CreateDeviationRequest(
                department="质量部",
                reporter_open_id="ou_reporter_001",
                description="失败场景",
                affected_items="批号",
            ),
            "system",
            None,
        )


@pytest.mark.anyio
async def test_sync_deviation_report_record_to_feishu_uses_minimal_fields(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = User(
        id=uuid.uuid4(),
        name="报告人甲",
        email="reporter@example.com",
        enterprise_email="reporter@example.com",
        feishu_open_id=f"ou_{uuid.uuid4().hex}",
    )
    db_session.add(current_user)
    await db_session.commit()

    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-REPORT-001",
        title="洁净区压差异常",
        department="质量部",
        description="洁净区压差异常",
        affected_items="原料A/批号B-001",
        reporter_id=current_user.id,
        discoverer="报告人甲",
        status="draft",
        discovery_date=datetime(2026, 7, 3, 9, 0, tzinfo=UTC),
    )
    db_session.add(deviation)
    await db_session.commit()

    upsert_mock: Any = AsyncMock(return_value=("rec_report_001", "tbl_report"))
    monkeypatch.setattr(feishu_sync_service.feishu_sync, "_upsert_record", upsert_mock)
    monkeypatch.setattr(
        feishu_sync_service,
        "_get_department_contacts_from_feishu",
        AsyncMock(
            return_value=[
                {
                    "name": "报告人甲",
                    "department": "质量部",
                    "open_id": current_user.feishu_open_id,
                    "bitable_user_id": "ou_bitable_reporter_001",
                    "department_head_name": "部门负责人甲",
                }
            ]
        ),
    )

    result = await feishu_sync_service.sync_deviation_report_record_to_feishu(
        db_session,
        deviation.id,
    )

    assert result == {"record_id": "rec_report_001", "table_id": "tbl_report"}
    assert upsert_mock.await_count == 1
    assert upsert_mock.await_args.args[1] == "deviation_report_record"
    assert upsert_mock.await_args.args[4] == {
        "偏差编号": "DEV-REPORT-001",
        "报告时间": int(datetime(2026, 7, 3, 9, 0, tzinfo=UTC).timestamp() * 1000),
        "偏差内容": "洁净区压差异常",
        "偏差报告": "",
        "涉及产品名称/批号": "原料A/批号B-001",
        "部门": "质量部",
        "报告人": [{"id": "ou_bitable_reporter_001"}],
        "报告状态": "draft",
    }


@pytest.mark.anyio
async def test_sync_deviation_report_record_to_feishu_uses_target_record_id(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = User(
        id=uuid.uuid4(),
        name="报告人乙",
        email="reporter2@example.com",
        enterprise_email="reporter2@example.com",
        feishu_open_id=f"ou_{uuid.uuid4().hex}",
    )
    db_session.add(current_user)
    await db_session.commit()

    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-REPORT-002",
        title="洁净区温度异常",
        department="质量部",
        description="洁净区温度异常",
        reporter_id=current_user.id,
        discoverer="报告人乙",
        status="draft",
        discovery_date=datetime(2026, 7, 3, 10, 0, tzinfo=UTC),
    )
    db_session.add(deviation)
    await db_session.commit()

    upsert_mock: Any = AsyncMock(return_value=("rec_report_target_001", "tbl_report"))
    monkeypatch.setattr(feishu_sync_service.feishu_sync, "_upsert_record", upsert_mock)
    monkeypatch.setattr(
        feishu_sync_service,
        "_get_department_contacts_from_feishu",
        AsyncMock(
            return_value=[
                {
                    "name": "报告人乙",
                    "department": "质量部",
                    "open_id": current_user.feishu_open_id,
                    "bitable_user_id": "ou_bitable_reporter_002",
                    "department_head_name": "部门负责人乙",
                }
            ]
        ),
    )

    result = await feishu_sync_service.sync_deviation_report_record_to_feishu(
        db_session,
        deviation.id,
        target_record_id="rec_report_origin_001",
    )

    assert result == {"record_id": "rec_report_target_001", "table_id": "tbl_report"}
    assert upsert_mock.await_count == 1
    assert upsert_mock.await_args.args[3] == "rec_report_origin_001"


@pytest.mark.anyio
async def test_list_validation_records_from_feishu_applies_page_filters(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 8, 0, tzinfo=UTC)
    entity = feishu_sync_service.QualityFeishuEntityRuntimeConfig(
        app_token="basc_validation",
        table_id="tbl_validation",
        is_enabled=True,
        enable_push_to_feishu=True,
        enable_pull_from_feishu=True,
        field_mappings={},
    )
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={"validation_process": entity},
    )

    resolve_mock: Any = AsyncMock(return_value=(runtime, entity))
    monkeypatch.setattr(
        quality_feishu_pages,
        "_resolve_runtime_entity",
        resolve_mock,
    )
    monkeypatch.setattr(
        quality_feishu_pages,
        "_search_entity_records",
        AsyncMock(
            return_value=[
                {
                    "record_id": "rec_process_001",
                    "created_time": int(now.timestamp() * 1000),
                    "last_modified_time": int(now.timestamp() * 1000),
                    "fields": {
                        "验证类别": "工艺验证",
                        "确认名称": "工艺验证方案A",
                        "任务状态": "完成",
                        "部门名称": "生产管理部",
                        "验证到期时间": "2026.07",
                        "方案编码": "PV-001",
                        "起草时间": int(
                            datetime(2026, 7, 1, tzinfo=UTC).timestamp() * 1000
                        ),
                    },
                },
                {
                    "record_id": "rec_process_002",
                    "created_time": int(now.timestamp() * 1000),
                    "last_modified_time": int(now.timestamp() * 1000),
                    "fields": {
                        "验证类别": "工艺验证",
                        "确认名称": "工艺验证方案B",
                        "任务状态": "未完成",
                        "部门名称": "生产管理部",
                        "验证到期时间": "2026.05",
                        "方案编码": "PV-002",
                        "起草时间": int(
                            datetime(2026, 5, 1, tzinfo=UTC).timestamp() * 1000
                        ),
                    },
                },
                {
                    "record_id": "rec_cleaning_001",
                    "created_time": int(now.timestamp() * 1000),
                    "last_modified_time": int(now.timestamp() * 1000),
                    "fields": {
                        "验证类别": "清洁验证",
                        "确认名称": "清洁验证方案",
                        "任务状态": "完成",
                        "部门名称": "生产管理部",
                        "验证到期时间": "2026.07",
                        "方案编码": "CV-001",
                        "起草时间": int(
                            datetime(2026, 7, 1, tzinfo=UTC).timestamp() * 1000
                        ),
                    },
                },
            ]
        ),
    )

    result = await quality_feishu_pages.list_validation_records_from_feishu(
        db_session,
        validation_type="process_validation",
        status="完成",
        department="生产管理部",
        keyword="PV-001",
        planned_end_date_from="2026-07-01",
        planned_end_date_to="2026-07-31",
        drafted_at_from="2026-07-01",
        drafted_at_to="2026-07-31",
        page=1,
        page_size=20,
    )

    assert result["total"] == 1
    assert result["items"][0]["record_id"] == "rec_process_001"
    resolve_mock.assert_awaited_once()
    assert resolve_mock.await_args.args[1] == "validation_process"


@pytest.mark.anyio
async def test_sync_deviation_to_feishu_ignores_mismatched_record_id(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-LEDGER-001",
        title="偏差台账同步",
        description="偏差台账同步",
        status="draft",
        feishu_base_table_id="tbl_report_real",
        feishu_base_record_id="rec_report_origin_001",
    )
    db_session.add(deviation)
    await db_session.commit()

    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "deviation_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_deviation",
                table_id="tbl_deviation_real",
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
    monkeypatch.setattr(
        repository,
        "get_related_capas_for_deviation",
        AsyncMock(return_value=[]),
    )
    upsert_mock: Any = AsyncMock(
        return_value=("rec_deviation_001", "tbl_deviation_real")
    )
    monkeypatch.setattr(feishu_sync_service.feishu_sync, "_upsert_record", upsert_mock)

    result = await feishu_sync_service.sync_deviation_to_feishu(
        db_session, deviation.id
    )

    assert result == {
        "record_id": "rec_deviation_001",
        "table_id": "tbl_deviation_real",
    }
    assert upsert_mock.await_count == 1
    assert upsert_mock.await_args.args[3] is None


@pytest.mark.anyio
async def test_ensure_deviation_from_report_record_creates_local_deviation(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            (
                "deviation_report_record"
            ): feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="bascn_report",
                table_id="tbl_report_real",
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
    ) -> list[dict[Any, Any]]:
        assert entity_code == "deviation_report_record"
        return [
            {
                "record_id": "rec_report_bridge_001",
                "last_modified_time": int(now.timestamp() * 1000),
                "fields": {
                    "偏差编号": "PC-2607001",
                    "报告时间": int(now.timestamp() * 1000),
                    "偏差内容": "桥接测试偏差",
                    "偏差报告": "飞书原始报告内容",
                    "涉及产品名称/批号": "产品A/批号B001",
                    "部门": "质量部",
                    "报告人": [{"name": "报告人甲"}],
                },
            }
        ]

    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "search_records",
        fake_search_records,
    )

    result = await service.ensure_deviation_from_report_record(
        db_session,
        "rec_report_bridge_001",
    )

    assert result["created"] is True
    deviation = await repository.get_deviation_by_code(db_session, "PC-2607001")
    assert deviation is not None
    assert deviation.feishu_base_record_id == "rec_report_bridge_001"
    assert deviation.description == "桥接测试偏差"
    assert deviation.report_content == "飞书原始报告内容"
    assert deviation.affected_items == "产品A/批号B001"


@pytest.mark.anyio
async def test_sync_investigation_push_uses_actual_table_fields(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 9, 0, tzinfo=UTC)
    deviation = Deviation(
        id=uuid.uuid4(),
        deviation_code="DEV-PUSH-001",
        title="调查推送偏差",
        department="质量部",
        created_at=now,
        updated_at=now,
    )
    push_record = DeviationInvestigationPushRecord(
        id=uuid.uuid4(),
        deviation_id=deviation.id,
        deviation_code=deviation.deviation_code,
        push_round="第2次",
        investigation_report_url="https://example.com/investigation.pdf",
        submitted_at=now,
        submitter="提交人甲",
        department_head_result="approved",
        department_head_reviewed_at=now,
        qa_name="QA甲",
        qa_result="rejected",
        qa_reviewed_at=now,
        qa_head_name="QA负责人甲",
        qa_head_result="approved",
        qa_head_reviewed_at=now,
        created_at=now,
        updated_at=now,
    )
    db_session.add_all([deviation, push_record])
    await db_session.commit()

    upsert_mock: Any = AsyncMock(return_value=("rec_push_001", "tbl_push"))
    monkeypatch.setattr(feishu_sync_service.feishu_sync, "_upsert_record", upsert_mock)
    monkeypatch.setattr(
        feishu_sync_service,
        "_get_department_contacts_from_feishu",
        AsyncMock(
            return_value=[
                {
                    "name": "提交人甲",
                    "department": "质量部",
                    "bitable_user_id": "ou_submitter_001",
                },
                {
                    "name": "QA甲",
                    "department": "质量管理部",
                    "bitable_user_id": "ou_qa_001",
                },
                {
                    "name": "QA负责人甲",
                    "department": "质量管理部",
                    "bitable_user_id": "ou_qa_head_001",
                },
            ]
        ),
    )

    result = (
        await feishu_sync_service.sync_deviation_investigation_push_record_to_feishu(
            db_session,
            push_record.id,
        )
    )

    assert result == {"record_id": "rec_push_001", "table_id": "tbl_push"}
    assert upsert_mock.await_args.args[1] == "deviation_investigation_push_record"
    assert upsert_mock.await_args.args[4] == {
        "偏差编号": "DEV-PUSH-001",
        "第N次推送": "第2次",
        "偏差调查报告": {
            "link": "https://example.com/investigation.pdf",
            "text": "https://example.com/investigation.pdf",
            "type": "url",
        },
        "提交日期": int(now.timestamp() * 1000),
        "提交人": [{"id": "ou_submitter_001"}],
        "部门负责人审核结果": "通过",
        "部门负责人审核时间": int(now.timestamp() * 1000),
        "QA": [{"id": "ou_qa_001"}],
        "QA审核结果": "不通过",
        "QA审核时间": int(now.timestamp() * 1000),
        "QA负责人": [{"id": "ou_qa_head_001"}],
        "QA负责人审核结果": "通过",
        "QA负责人审核时间": int(now.timestamp() * 1000),
    }
    assert upsert_mock.await_args.kwargs["search_conditions"] == [
        ("偏差编号", "DEV-PUSH-001"),
        ("第N次推送", "第2次"),
    ]


@pytest.mark.anyio
async def test_update_capa_triggers_auto_feishu_sync(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 7, 3, 8, 0, tzinfo=UTC)
    capa = CAPA(
        id=uuid.uuid4(),
        capa_code="CAPA-AUTO-001",
        title="自动同步CAPA",
        status="draft",
        created_at=now,
        updated_at=now,
    )
    db_session.add(capa)
    await db_session.commit()

    auto_sync_mock: Any = AsyncMock()
    monkeypatch.setattr(
        feishu_sync_service,
        "auto_sync_capa_after_write",
        auto_sync_mock,
    )

    result = await service.update_capa(
        db_session,
        capa.id,
        UpdateCapaRequest(title="自动同步CAPA-已更新"),
        "system",
    )

    assert result == {"success": True}
    assert auto_sync_mock.await_count == 1
    assert auto_sync_mock.await_args.args[0] is db_session
    assert auto_sync_mock.await_args.args[1] == capa.id


@pytest.mark.anyio
async def test_change_statistics_prefers_ledger_then_legacy_fields(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = feishu_sync_service.QualityFeishuRuntimeConfig(
        app_id="cli_app_id",
        app_secret="cli_secret",
        is_app_enabled=True,
        legacy_app_token=None,
        entities={
            "change_ledger": feishu_sync_service.QualityFeishuEntityRuntimeConfig(
                app_token="basc_change",
                table_id="tbl_change_real",
                is_enabled=True,
                enable_push_to_feishu=True,
                enable_pull_from_feishu=True,
                field_mappings={
                    "变更申请部门": "申请部门别名",
                    "变更等级": "风险等级",
                    "变更申请日期": "申请时间",
                    "变更计划批准日期": "计划批准时间",
                    "变更正式执行日期": "正式执行时间",
                    "变更关闭日期": "关闭时间",
                },
            ),
        },
    )
    monkeypatch.setattr(
        feishu_sync_service.feishu_sync,
        "_resolve_runtime",
        AsyncMock(return_value=runtime),
    )

    def _to_ms(year: int, month: int, day: int) -> int:
        return int(datetime(year, month, day, tzinfo=UTC).timestamp() * 1000)

    async def fake_search_records(
        self: Any,
        table_id: str,
        *,
        filter_str: str | None = None,
        page_size: int = 500,
        automatic_fields: bool = False,
    ) -> list[dict[Any, Any]]:
        assert table_id == "tbl_change_real"
        assert filter_str is None
        assert page_size == 9999
        assert automatic_fields is True
        return [
            {
                "record_id": "rec_change_001",
                "fields": {
                    "申请部门别名": "质量部",
                    "风险等级": "一级",
                    "申请时间": _to_ms(2026, 7, 1),
                    "计划批准时间": _to_ms(2026, 7, 2),
                    "正式执行时间": _to_ms(2026, 7, 3),
                    "关闭时间": _to_ms(2026, 7, 4),
                },
            },
            {
                "record_id": "rec_change_002",
                "fields": {
                    "变更申请部门": "生产部",
                    "变更级别": "二级",
                    "变更状态": "执行中",
                    "变更类型": "工艺",
                    "变更计划批准日期": _to_ms(2026, 7, 2),
                    "变更正式执行日期": _to_ms(2026, 7, 5),
                },
            },
            {
                "record_id": "rec_change_003",
                "fields": {
                    "变更申请部门": "工程部",
                    "变更等级": "三级",
                    "变更状态": "待审批",
                    "是否延期": "是",
                },
            },
            {
                "record_id": "rec_change_004",
                "fields": {
                    "变更申请部门": "",
                    "变更等级": "unknown",
                    "变更类型": "",
                },
            },
        ]

    monkeypatch.setattr(
        feishu_bitable.BitableClient, "search_records", fake_search_records
    )

    result = await service.get_change_statistics(db_session)

    assert result.total == 4
    assert result.closed_count == 1
    assert result.delay_count == 3
    assert result.action_plan_total == 2
    assert result.action_plan_overdue == 3
    assert result.action_plan_confirmed == 1
    assert {item["status"]: item["count"] for item in result.status_distribution} == {
        "closed": 1,
        "in_progress": 1,
        "pending": 2,
    }
    assert {item["level"]: item["count"] for item in result.level_distribution} == {
        "一级": 1,
        "二级": 1,
        "三级": 1,
    }
    assert {item["type"]: item["count"] for item in result.type_distribution} == {
        "工艺": 1,
    }
    assert {item["name"]: item["count"] for item in result.department_distribution} == {
        "质量部": 1,
        "生产部": 1,
        "工程部": 1,
    }
