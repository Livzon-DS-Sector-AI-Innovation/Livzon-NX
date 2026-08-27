from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.modules.quality.models.finished_trend_alert_notification import (
    FinishedTrendAlertNotification,
)
from app.modules.quality.service import inspection_dashboard_calc as calc

SimpleNamespace: Any = _SimpleNamespace


def _notification(status: str = "sent") -> FinishedTrendAlertNotification:
    return FinishedTrendAlertNotification(
        entity_code="finished",
        batch_no="MC-001",
        metric_key="含量",
        metric_label="含量",
        actual_value=101.0,
        upper_control_limit=100.0,
        lower_control_limit=90.0,
        recipient_name="张三",
        recipient_open_id="ou_1",
        notification_status=status,
        feishu_message_id="m1" if status == "sent" else None,
        notified_at=datetime(2026, 8, 20, tzinfo=UTC) if status == "sent" else None,
    )


def test_metric_and_limit_parsers_cover_common_formats() -> None:
    assert calc._parse_numeric_metric("≤ 1，234。5 ppm％") == 1234.5
    assert calc._parse_numeric_metric("无数据") is None
    assert calc._parse_numeric_metric(None) is None
    assert calc._normalize_oot_item_name(" 含  量 ") == "含量"
    assert calc._split_limit_range_parts("") == []
    assert calc._split_limit_range_parts("90 ~ 100") == ["90", "100"]
    assert calc._split_limit_range_parts("90-100") == ["90", "100"]
    assert calc._parse_limit_spec_lines("≤10", label_prefix="OOT") == [
        {"label": "OOT上限", "value": 10.0}
    ]
    assert calc._parse_limit_spec_lines(">= 2", label_prefix="OOT") == [
        {"label": "OOT下限", "value": 2.0}
    ]
    assert calc._parse_limit_spec_lines("2～8", label_prefix="OOT") == [
        {"label": "OOT下限", "value": 2.0},
        {"label": "OOT上限", "value": 8.0},
    ]
    assert calc._parse_limit_spec_lines("文本", label_prefix="OOT") == []
    assert calc._parse_limit_spec_lines(None, label_prefix="OOT") == []


def test_spec_lines_statistics_and_product_code_helpers() -> None:
    config = {
        "spec_lines": [{"label": "标准上限", "value": "10"}],
        "alert_spec_lines": [{"label": "预警上限", "value": 9}],
    }
    assert calc._build_spec_lines(config)[0]["value"] == 10.0
    assert calc._build_alert_spec_lines(config)[0]["value"] == 9.0
    assert calc._build_alert_spec_lines({}) == []
    merged = calc._merge_spec_lines(
        [{"label": "上限", "value": 10}],
        [{"label": "上限", "value": 10}, {"label": "下限", "value": 2}],
    )
    assert len(merged) == 2
    assert calc._is_value_out_of_spec_lines(11, merged)
    assert calc._is_value_out_of_spec_lines(1, merged)
    assert not calc._is_value_out_of_spec_lines(5, merged)
    assert calc._compute_metric_statistics([])["mean"] is None
    assert calc._compute_metric_statistics([2])["std_dev"] is None
    stats = calc._compute_metric_statistics([1, 2, 3])
    assert stats["mean"] == 2
    assert stats["upper_control_limit"] is not None
    assert calc._extract_batch_product_code(None) is None
    assert calc._extract_batch_product_code("USMC-001") == "MC"
    assert calc._extract_batch_product_code("abc_001") == "ABC"
    assert calc._extract_batch_product_code("XYZ001") == "XYZ"
    assert calc._extract_batch_product_code("123") == "123"


def test_recipient_join_deduplicates_and_ignores_empty_values() -> None:
    recipients = [
        {"name": "张三", "open_id": "ou1"},
        {"name": "张三", "open_id": ""},
        {"name": "李四", "open_id": "ou2"},
    ]
    assert (
        calc._join_recipient_field(recipients, "name", delimiter="、") == "张三、李四"  # type: ignore[arg-type]
    )
    assert calc._join_recipient_field(recipients, "open_id", delimiter=",") == "ou1,ou2"  # type: ignore[arg-type]
    assert calc._join_recipient_field(recipients, "email", delimiter=",") is None  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ([{"status": "sent", "message_id": "m1"}], "sent"),
        (
            [
                {"status": "sent", "message_id": "m1"},
                {"status": "failed", "message_id": None},
            ],
            "partial",
        ),
        ([{"status": "failed", "message_id": None}], "failed"),
    ],
)
async def test_send_dashboard_alert_notifications_aggregates_results(
    monkeypatch: pytest.MonkeyPatch,
    results: list[dict[str, str | None]],
    expected: str,
) -> None:
    monkeypatch.setattr(
        calc, "_send_mpa_alert_notification", AsyncMock(side_effect=results)
    )
    recipients = [
        {"name": f"用户{i}", "open_id": f"ou{i}", "email": None}
        for i in range(len(results))
    ]
    result = await calc._send_dashboard_alert_notifications(
        db=SimpleNamespace(),
        sender_user_open_id=None,
        source_label="成品",
        recipients=recipients,
        batch_no="B1",
        metric_label="含量",
        actual_value=11,
        upper_control_limit=10,
        lower_control_limit=2,
        spec_lines=[],
    )
    assert result["status"] == expected


@pytest.mark.anyio
async def test_send_mpa_notification_uses_open_id_then_email_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send: Any = AsyncMock(side_effect=[None, "email-message"])
    monkeypatch.setattr(calc, "send_user_card_with_message_id", send)
    result = await calc._send_mpa_alert_notification(
        db=SimpleNamespace(),
        open_id="ou1",
        email="a@example.com",
        batch_no="B1",
        metric_label="含量",
        actual_value=11,
        upper_control_limit=None,
        lower_control_limit=None,
        spec_lines=[{"label": "上限", "value": 10}],
    )
    assert result == {"status": "sent", "message_id": "email-message", "error": None}
    assert send.await_args_list[1].kwargs["receive_id_type"] == "email"
    send.reset_mock(side_effect=True)
    send.side_effect = None
    send.return_value = None
    failed = await calc._send_mpa_alert_notification(
        db=SimpleNamespace(),
        open_id=None,
        email=None,
        batch_no="B1",
        metric_label="含量",
        actual_value=11,
        upper_control_limit=10,
        lower_control_limit=0,
    )
    assert failed["status"] == "failed"


def test_serialize_dashboard_alert_maps_notification_state() -> None:
    sent = calc._serialize_dashboard_alert(
        notification=_notification(),
        mean=95,
        std_dev=2,
        spec_lines=[{"label": "标准上限", "value": 100}],
        notification_deduplicated=True,
    )
    assert sent["notification_sent"] is True
    assert sent["notification_deduplicated"] is True
    assert sent["notified_at"].startswith("2026-08-20")
    missing = calc._serialize_dashboard_alert(
        notification=_notification("unmapped"),
        mean=None,
        std_dev=None,
        spec_lines=[],
        notification_deduplicated=False,
        notification_error="未映射",
    )
    assert missing["notification_sent"] is False
    assert missing["notified_at"] is None


def _alert_kwargs() -> dict[str, object]:
    return {
        "source_label": "成品",
        "entity_code": "finished",
        "batch_no": "MC-001",
        "metric_key": "含量",
        "metric_label": "含量",
        "actual_value": 101.0,
        "mean": 95.0,
        "std_dev": 2.0,
        "upper_control_limit": 100.0,
        "lower_control_limit": 90.0,
        "spec_lines": [{"label": "标准上限", "value": 100}],
    }


@pytest.mark.anyio
async def test_materialize_dashboard_alert_handles_existing_and_new_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _notification("sent")
    monkeypatch.setattr(
        calc, "_get_existing_dashboard_notification", AsyncMock(return_value=existing)
    )
    result = await calc._materialize_dashboard_alert(
        SimpleNamespace(),
        **_alert_kwargs(),  # type: ignore[arg-type]
    )
    assert result["notification_deduplicated"] is True

    retry: Any = AsyncMock(return_value={"retried": True})
    monkeypatch.setattr(calc, "_retry_incomplete_dashboard_notification", retry)
    monkeypatch.setattr(
        calc,
        "_get_existing_dashboard_notification",
        AsyncMock(return_value=_notification("unmapped")),
    )
    assert await calc._materialize_dashboard_alert(
        SimpleNamespace(),
        **_alert_kwargs(),  # type: ignore[arg-type]
    ) == {"retried": True}

    create: Any = AsyncMock(
        side_effect=lambda *args, **kwargs: _notification(
            str(kwargs["notification_status"])
        )
    )
    monkeypatch.setattr(calc, "_create_dashboard_notification", create)
    monkeypatch.setattr(
        calc, "_get_existing_dashboard_notification", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        calc, "_resolve_dashboard_recipients", AsyncMock(return_value=[])
    )
    unmapped = await calc._materialize_dashboard_alert(
        SimpleNamespace(),
        **_alert_kwargs(),  # type: ignore[arg-type]
    )
    assert unmapped["notification_status"] == "unmapped"

    monkeypatch.setattr(
        calc,
        "_resolve_dashboard_recipients",
        AsyncMock(return_value=[{"name": "张三", "open_id": None, "email": None}]),
    )
    missing = await calc._materialize_dashboard_alert(
        SimpleNamespace(),
        **_alert_kwargs(),  # type: ignore[arg-type]
    )
    assert missing["notification_status"] == "missing_open_id"

    monkeypatch.setattr(
        calc,
        "_resolve_dashboard_recipients",
        AsyncMock(return_value=[{"name": "张三", "open_id": "ou1", "email": None}]),
    )
    monkeypatch.setattr(
        calc,
        "_send_dashboard_alert_notifications",
        AsyncMock(
            return_value={"status": "partial", "message_id": "m1", "error": "一个失败"}
        ),
    )
    partial = await calc._materialize_dashboard_alert(
        SimpleNamespace(),
        **_alert_kwargs(),  # type: ignore[arg-type]
    )
    assert partial["notification_status"] == "partial"


@pytest.mark.anyio
async def test_finished_dashboard_data_handles_unconfigured_and_alerting_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        calc,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException("not configured")),  # type: ignore[arg-type]
    )
    empty = await calc._get_finished_dashboard_data(
        SimpleNamespace(),
        source_entity_code="finished",
        source_label="成品",
        metric_configs=(),
    )
    assert empty["configured"] is False

    monkeypatch.setattr(
        calc, "_resolve_runtime_entity", AsyncMock(return_value=(None, None))
    )
    monkeypatch.setattr(
        calc,
        "_search_entity_records_with_fallback",
        AsyncMock(
            return_value=[
                {"fields": {calc.FINISHED_DASHBOARD_BATCH_FIELD: "B1", "含量": "5"}},  # type: ignore[attr-defined]
                {"fields": {calc.FINISHED_DASHBOARD_BATCH_FIELD: "B2", "含量": "20"}},  # type: ignore[attr-defined]
                {"fields": {calc.FINISHED_DASHBOARD_BATCH_FIELD: "B3", "含量": "异常"}},  # type: ignore[attr-defined]
                {"fields": {calc.FINISHED_DASHBOARD_BATCH_FIELD: "", "含量": "7"}},  # type: ignore[attr-defined]
            ]
        ),
    )
    monkeypatch.setattr(
        calc,
        "_get_oot_limit_items_by_product_code",
        AsyncMock(return_value={"含量": SimpleNamespace(oot_limit_value="≤10")}),
    )
    alert = calc._serialize_dashboard_alert(
        notification=_notification("partial"),
        mean=12.5,
        std_dev=7.5,
        spec_lines=[{"label": "OOT上限", "value": 10}],
        notification_deduplicated=False,
    )
    alert["batch_no"] = "B2"
    monkeypatch.setattr(
        calc,
        "_materialize_dashboard_alert",
        AsyncMock(return_value=alert),
    )
    data = await calc._get_finished_dashboard_data(
        SimpleNamespace(),
        source_entity_code="finished",
        source_label="成品",
        oot_product_code="MC",
        metric_configs=(
            {
                "metric_key": "含量",
                "metric_label": "含量",
                "oot_item_name": "含量",
                "spec_lines": [{"label": "标准上限", "value": 100}],
                "alert_spec_lines": [],
            },
        ),
    )
    assert data["configured"] is True
    assert data["summary"]["total_records"] == 4
    assert data["summary"]["valid_record_count"] == 2
    assert data["summary"]["skipped_value_count"] == 1
    assert data["summary"]["alert_metric_count"] == 1
    assert data["summary"]["failed_notification_count"] == 1
    assert data["charts"][0]["actual_series"] == [5.0, 20.0]
