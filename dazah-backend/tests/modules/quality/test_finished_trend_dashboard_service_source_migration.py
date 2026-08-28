from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

import app.modules.quality.service.inspection_dashboard_calc as service
from app.modules.quality.models.contacts import DepartmentContact
from app.modules.quality.models.finished_trend_alert_notification import (
    FinishedTrendAlertNotification,
)
from app.modules.quality.service.inspection_dashboard_config import (
    LFT_DASHBOARD_ENTITY_CONFIGS,
    LFT_USP_DASHBOARD_ENTITY_CODE,
    MPA_DASHBOARD_ENTITY_CODE,
    MPA_DASHBOARD_ENTITY_CONFIGS,
    MPA_DASHBOARD_SOURCE_LABEL,
    MVT_DASHBOARD_ENTITY_CODE,
    MVT_DASHBOARD_METRIC_CONFIGS,
    MVT_DASHBOARD_SOURCE_LABEL,
)


async def _get_mpa_dashboard_data(db_session):
    config = MPA_DASHBOARD_ENTITY_CONFIGS[MPA_DASHBOARD_ENTITY_CODE]
    return await service._get_finished_dashboard_data(
        db_session,
        source_entity_code=MPA_DASHBOARD_ENTITY_CODE,
        source_label=str(config["source_label"]),
        metric_configs=config["metric_configs"],
    )


async def _get_mvt_dashboard_data(db_session):
    return await service._get_finished_dashboard_data(
        db_session,
        source_entity_code=MVT_DASHBOARD_ENTITY_CODE,
        source_label=MVT_DASHBOARD_SOURCE_LABEL,
        metric_configs=MVT_DASHBOARD_METRIC_CONFIGS,
    )


async def _get_lft_dashboard_data(db_session, source_entity_code: str):
    config = LFT_DASHBOARD_ENTITY_CONFIGS[source_entity_code]
    return await service._get_finished_dashboard_data(
        db_session,
        source_entity_code=source_entity_code,
        source_label=str(config["source_label"]),
        metric_configs=config["metric_configs"],
    )


def test_finished_trend_alert_notification_table_shape() -> None:
    assert (
        FinishedTrendAlertNotification.__tablename__
        == "quality_finished_trend_alert_notifications"
    )

    constraint_names = {
        constraint.name
        for constraint in FinishedTrendAlertNotification.__table__.constraints
    }

    assert "uq_quality_finished_trend_alert_notification_key" in constraint_names


def test_parse_numeric_metric_strips_units_and_symbols() -> None:
    assert service._parse_numeric_metric("0.21%") == pytest.approx(0.21)
    assert service._parse_numeric_metric(" 2000ppm ") == pytest.approx(2000.0)
    assert service._parse_numeric_metric("≤0.50%") == pytest.approx(0.5)
    assert service._parse_numeric_metric("无") is None


def test_compute_metric_statistics_builds_sigma_limits() -> None:
    result = service._compute_metric_statistics([0.2, 0.3, 0.4])

    assert result["sample_count"] == 3
    assert result["mean"] == pytest.approx(0.3)
    assert result["std_dev"] == pytest.approx(0.08164965809)
    assert result["upper_control_limit"] == pytest.approx(0.54494897427)
    assert result["lower_control_limit"] == pytest.approx(0.05505102572)


def test_extract_batch_product_code_maps_mpa_batches_to_mc() -> None:
    assert service._extract_batch_product_code("USMC-M-2606013") == "MC"
    assert service._extract_batch_product_code("MC-2606013") == "MC"
    assert service._extract_batch_product_code("MFN-2607001") == "MFN"


@pytest.mark.anyio
async def test_resolve_dashboard_recipients_uses_fixed_override_list(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_mock = AsyncMock(
        side_effect=[
            {"name": "陈连平", "open_id": "ou_chen", "email": None},
            {"name": "席晓", "open_id": "ou_xi", "email": "xixiao@livzon.cn"},
        ]
    )
    monkeypatch.setattr(service, "_resolve_recipient_by_name", resolve_mock)

    result = await service._resolve_dashboard_recipients(
        db_session,
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no="USMC-M-2606013",
    )

    assert result == [
        {"name": "陈连平", "open_id": "ou_chen", "email": None},
        {"name": "席晓", "open_id": "ou_xi", "email": "xixiao@livzon.cn"},
    ]
    assert resolve_mock.await_count == 2


@pytest.mark.anyio
async def test_get_mpa_dashboard_data_computes_charts_and_spec_lines(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    monkeypatch.setattr(
        service,
        "_search_entity_records_with_fallback",
        AsyncMock(
            return_value=[
                {
                    "record_id": "rec1",
                    "fields": {"批号": "MFN-001", "干燥失重:≤0.50%": "0.20%"},
                },
                {
                    "record_id": "rec2",
                    "fields": {"批号": "MFN-002", "干燥失重:≤0.50%": "0.30%"},
                },
                {
                    "record_id": "rec3",
                    "fields": {"批号": "MFN-003", "干燥失重:≤0.50%": "0.40%"},
                },
            ]
        ),
    )
    materialize_mock = AsyncMock()
    monkeypatch.setattr(service, "_materialize_dashboard_alert", materialize_mock)

    result = await _get_mpa_dashboard_data(db_session)

    chart = next(
        item for item in result["charts"] if item["metric_key"] == "干燥失重:≤0.50%"
    )
    assert result["configured"] is True
    assert chart["categories"] == ["MFN-001", "MFN-002", "MFN-003"]
    assert chart["actual_series"] == [0.2, 0.3, 0.4]
    assert chart["summary"]["sample_count"] == 3
    assert chart["summary"]["mean"] == pytest.approx(0.3)
    assert chart["spec_lines"][0]["value"] == pytest.approx(0.5)
    materialize_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_get_mpa_dashboard_data_detects_alerts(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        {
            "record_id": f"rec{i}",
            "fields": {
                "批号": f"MFN-{i:03d}",
                "干燥失重:≤0.50%": "0.10%",
            },
        }
        for i in range(1, 11)
    ]
    records.append(
        {
            "record_id": "rec999",
            "fields": {
                "批号": "MFN-999",
                "干燥失重:≤0.50%": "1.20%",
            },
        }
    )
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    monkeypatch.setattr(
        service,
        "_search_entity_records_with_fallback",
        AsyncMock(return_value=records),
    )
    materialize_mock = AsyncMock(
        return_value={
            "entity_code": MPA_DASHBOARD_ENTITY_CODE,
            "batch_no": "MFN-999",
            "metric_key": "干燥失重:≤0.50%",
            "metric_label": "干燥失重:≤0.50%",
            "actual_value": 1.2,
            "spec_lines": [{"label": "标准上限", "value": 0.5}],
            "notification_status": "sent",
            "notification_sent": True,
            "notification_deduplicated": False,
        }
    )
    monkeypatch.setattr(service, "_materialize_dashboard_alert", materialize_mock)

    result = await _get_mpa_dashboard_data(db_session)

    assert result["summary"]["alert_metric_count"] == 1
    assert result["alerts"][0]["batch_no"] == "MFN-999"
    assert result["alerts"][0]["notification_status"] == "sent"
    materialize_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_get_mvt_dashboard_data_reads_mvt_source_entity(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    search_mock = AsyncMock(
        return_value=[
            {
                "record_id": "rec1",
                "fields": {
                    "批号": "MVT-001",
                    "比旋度（按干燥品计算）：+265°~ +290°": "270",
                },
            },
            {
                "record_id": "rec2",
                "fields": {
                    "批号": "MVT-002",
                    "比旋度（按干燥品计算）：+265°~ +290°": "275",
                },
            },
        ]
    )
    monkeypatch.setattr(
        service,
        "_search_entity_records_with_fallback",
        search_mock,
    )
    monkeypatch.setattr(service, "_materialize_dashboard_alert", AsyncMock())

    result = await _get_mvt_dashboard_data(db_session)

    assert result["source_entity_code"] == MVT_DASHBOARD_ENTITY_CODE
    assert result["source_label"] == MVT_DASHBOARD_SOURCE_LABEL
    search_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_get_lft_dashboard_data_reads_selected_source_entity(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    search_mock = AsyncMock(
        return_value=[
            {
                "record_id": "rec1",
                "fields": {
                    "批号": "LFT-001",
                    "比旋度（无水物）：‘＋325°～＋340°": "330",
                },
            },
            {
                "record_id": "rec2",
                "fields": {
                    "批号": "LFT-002",
                    "比旋度（无水物）：‘＋325°～＋340°": "335",
                },
            },
        ]
    )
    monkeypatch.setattr(
        service,
        "_search_entity_records_with_fallback",
        search_mock,
    )
    monkeypatch.setattr(service, "_materialize_dashboard_alert", AsyncMock())

    result = await _get_lft_dashboard_data(db_session, LFT_USP_DASHBOARD_ENTITY_CODE)

    assert result["source_entity_code"] == LFT_USP_DASHBOARD_ENTITY_CODE
    assert result["source_label"] == "洛伐他汀（USP）"
    search_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_resolve_refining_recipient_from_department_contacts(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contact_name = f"测试提炼负责人_{uuid.uuid4().hex[:8]}"
    open_id = f"ou_test_{uuid.uuid4().hex}"
    db_session.add(
        DepartmentContact(
            name=contact_name,
            department="提炼部",
            open_id=open_id,
        )
    )
    await db_session.commit()

    monkeypatch.setattr(
        service,
        "_get_product_department_extraction_head",
        AsyncMock(return_value=contact_name),
    )
    monkeypatch.setattr(
        "app.modules.quality.service.department_contacts.get_department_contact_list_from_feishu",
        AsyncMock(return_value={"items": []}),
    )

    result = await service._resolve_refining_recipient(db_session, "MFN-2607001")

    assert result == {
        "product_code": "MFN",
        "name": contact_name,
        "open_id": open_id,
        "email": None,
    }


@pytest.mark.anyio
async def test_materialize_dashboard_alert_deduplicates_existing_notification(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = FinishedTrendAlertNotification(
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no="MFN-001",
        metric_key="干燥失重:≤0.50%",
        metric_label="干燥失重:≤0.50%",
        actual_value=1.2,
        upper_control_limit=0.8,
        lower_control_limit=0.1,
        recipient_name="张三",
        recipient_open_id="ou_test_001",
        notification_status="sent",
        feishu_message_id="om_existing",
        notified_at=datetime.now(UTC),
    )

    send_mock = AsyncMock()
    monkeypatch.setattr(
        service,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(service, "_send_mpa_alert_notification", send_mock)

    result = await service._materialize_dashboard_alert(
        db_session,
        source_label=MPA_DASHBOARD_SOURCE_LABEL,
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no="MFN-001",
        metric_key="干燥失重:≤0.50%",
        metric_label="干燥失重:≤0.50%",
        actual_value=1.2,
        mean=0.3,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.1,
        spec_lines=[{"label": "标准上限", "value": 1.0}],
    )

    assert result["notification_deduplicated"] is True
    assert result["notification_status"] == "sent"
    assert result["feishu_message_id"] == "om_existing"
    send_mock.assert_not_awaited()


@pytest.mark.anyio
async def test_materialize_dashboard_alert_marks_failed_notification_without_breaking(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_record = FinishedTrendAlertNotification(
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no="MFN-002",
        metric_key="干燥失重:≤0.50%",
        metric_label="干燥失重:≤0.50%",
        actual_value=1.3,
        upper_control_limit=0.8,
        lower_control_limit=0.1,
        recipient_name="张三",
        recipient_open_id="ou_test_001",
        notification_status="failed",
        feishu_message_id=None,
        notified_at=None,
    )
    create_mock = AsyncMock(return_value=created_record)
    monkeypatch.setattr(
        service,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service,
        "_resolve_dashboard_recipients",
        AsyncMock(
            return_value=[{"name": "张三", "open_id": "ou_test_001", "email": None}]
        ),
    )
    monkeypatch.setattr(service, "_create_dashboard_notification", create_mock)
    monkeypatch.setattr(
        service,
        "_send_dashboard_alert_notifications",
        AsyncMock(
            return_value={
                "status": "failed",
                "message_id": None,
                "error": "飞书通知发送失败",
            }
        ),
    )

    result = await service._materialize_dashboard_alert(
        db_session,
        source_label=MPA_DASHBOARD_SOURCE_LABEL,
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no="MFN-002",
        metric_key="干燥失重:≤0.50%",
        metric_label="干燥失重:≤0.50%",
        actual_value=1.3,
        mean=0.3,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.1,
        spec_lines=[{"label": "标准上限", "value": 1.0}],
    )

    assert result["notification_status"] == "failed"
    assert result["notification_error"] == "飞书通知发送失败"
    create_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_materialize_dashboard_alert_retries_existing_unmapped_notification(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_no = f"USMC-M-{uuid.uuid4().hex[:8]}"
    existing = FinishedTrendAlertNotification(
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no=batch_no,
        metric_key="干燥失重:≤0.50%",
        metric_label="干燥失重:≤0.50%",
        actual_value=1.2,
        upper_control_limit=0.8,
        lower_control_limit=0.1,
        recipient_name=None,
        recipient_open_id=None,
        notification_status="unmapped",
        feishu_message_id=None,
        notified_at=None,
    )
    db_session.add(existing)
    await db_session.commit()

    monkeypatch.setattr(
        service,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        service,
        "_resolve_dashboard_recipients",
        AsyncMock(
            return_value=[{"name": "张三", "open_id": "ou_test_001", "email": None}]
        ),
    )
    monkeypatch.setattr(
        service,
        "_send_dashboard_alert_notifications",
        AsyncMock(
            return_value={
                "status": "sent",
                "message_id": "om_retry_001",
                "error": None,
            }
        ),
    )

    result = await service._materialize_dashboard_alert(
        db_session,
        source_label=MPA_DASHBOARD_SOURCE_LABEL,
        entity_code=MPA_DASHBOARD_ENTITY_CODE,
        batch_no=batch_no,
        metric_key="干燥失重:≤0.50%",
        metric_label="干燥失重:≤0.50%",
        actual_value=1.2,
        mean=0.3,
        std_dev=0.1,
        upper_control_limit=0.8,
        lower_control_limit=0.1,
        spec_lines=[{"label": "标准上限", "value": 1.0}],
    )

    await db_session.refresh(existing)

    assert result["notification_status"] == "sent"
    assert result["recipient_name"] == "张三"
    assert result["notification_deduplicated"] is False
    assert existing.recipient_name == "张三"
    assert existing.recipient_open_id == "ou_test_001"
    assert existing.notification_status == "sent"


@pytest.mark.anyio
async def test_materialize_dashboard_alert_uses_multiple_fixed_recipients(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_record = FinishedTrendAlertNotification(
        entity_code=MVT_DASHBOARD_ENTITY_CODE,
        batch_no="MVT-2607001",
        metric_key="总杂质：≤3.0%",
        metric_label="总杂质：≤3.0%",
        actual_value=3.6,
        upper_control_limit=3.0,
        lower_control_limit=0.5,
        recipient_name="罗勇、周方圆",
        recipient_open_id="ou_luo,ou_zhou",
        notification_status="sent",
        feishu_message_id="om_multi_001,om_multi_002",
        notified_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        service,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        service,
        "_resolve_dashboard_recipients",
        AsyncMock(
            return_value=[
                {"name": "罗勇", "open_id": "ou_luo", "email": "luoyong01@livzon.cn"},
                {
                    "name": "周方圆",
                    "open_id": "ou_zhou",
                    "email": "zhoufangyuan@livzon.cn",
                },
            ]
        ),
    )
    create_mock = AsyncMock(return_value=created_record)
    monkeypatch.setattr(service, "_create_dashboard_notification", create_mock)
    monkeypatch.setattr(
        service,
        "_send_dashboard_alert_notifications",
        AsyncMock(
            return_value={
                "status": "sent",
                "message_id": "om_multi_001,om_multi_002",
                "error": None,
            }
        ),
    )

    result = await service._materialize_dashboard_alert(
        db_session,
        source_label=MVT_DASHBOARD_SOURCE_LABEL,
        entity_code=MVT_DASHBOARD_ENTITY_CODE,
        batch_no="MVT-2607001",
        metric_key="总杂质：≤3.0%",
        metric_label="总杂质：≤3.0%",
        actual_value=3.6,
        mean=1.5,
        std_dev=0.3,
        upper_control_limit=3.0,
        lower_control_limit=0.5,
        spec_lines=[{"label": "标准上限", "value": 3.0}],
    )

    assert result["notification_status"] == "sent"
    assert result["recipient_name"] == "罗勇、周方圆"
    assert result["recipient_open_id"] == "ou_luo,ou_zhou"
    create_mock.assert_awaited_once()
