from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

import app.modules.quality.api.inspection_feishu as inspection_feishu_api


@pytest.mark.anyio
async def test_get_mpa_dashboard_returns_data_and_meta(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        inspection_feishu_api,
        "get_mpa_dashboard_data",
        AsyncMock(
            return_value={
                "source_entity_code": "qc_finished_internal",
                "source_label": "霉酚酸（内控）",
                "charts": [
                    {
                        "metric_key": "总杂质:≤1.00%",
                        "metric_label": "总杂质:≤1.00%",
                        "categories": ["MFN-001"],
                        "actual_series": [0.2],
                        "mean_series": [0.2],
                        "upper_sigma_series": [None],
                        "lower_sigma_series": [None],
                        "spec_lines": [{"label": "标准上限", "value": 1.0}],
                        "points": [{"batch_no": "MFN-001", "value": 0.2}],
                        "summary": {
                            "sample_count": 1,
                            "mean": 0.2,
                            "std_dev": None,
                            "upper_control_limit": None,
                            "lower_control_limit": None,
                        },
                    }
                ],
                "alerts": [],
                "summary": {
                    "source_entity_code": "qc_finished_internal",
                    "source_label": "霉酚酸（内控）",
                    "total_records": 1,
                    "valid_record_count": 1,
                    "skipped_value_count": 0,
                    "alert_batch_count": 0,
                    "alert_metric_count": 0,
                    "first_notification_sent_count": 0,
                    "deduplicated_notification_count": 0,
                    "failed_notification_count": 0,
                    "unmapped_notification_count": 0,
                },
                "configured": True,
            }
        ),
    )

    response = await client.get("/api/v1/quality/inspection-finished/mpa/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["source_entity_code"] == "qc_finished_internal"
    assert payload["data"]["source_label"] == "霉酚酸（内控）"
    assert payload["data"]["charts"][0]["metric_key"] == "总杂质:≤1.00%"
    assert payload["data"]["alerts"] == []
    assert payload["meta"]["configured"] is True


@pytest.mark.anyio
async def test_get_mpa_dashboard_returns_configured_false_when_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        inspection_feishu_api,
        "get_mpa_dashboard_data",
        AsyncMock(
            return_value={
                "source_entity_code": "qc_finished_internal",
                "source_label": "霉酚酸（内控）",
                "charts": [],
                "alerts": [],
                "summary": {
                    "source_entity_code": "qc_finished_internal",
                    "source_label": "霉酚酸（内控）",
                    "total_records": 0,
                    "valid_record_count": 0,
                    "skipped_value_count": 0,
                    "alert_batch_count": 0,
                    "alert_metric_count": 0,
                    "first_notification_sent_count": 0,
                    "deduplicated_notification_count": 0,
                    "failed_notification_count": 0,
                    "unmapped_notification_count": 0,
                },
                "configured": False,
            }
        ),
    )

    response = await client.get("/api/v1/quality/inspection-finished/mpa/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["source_entity_code"] == "qc_finished_internal"
    assert payload["data"]["charts"] == []
    assert payload["meta"]["configured"] is False


@pytest.mark.anyio
async def test_get_mvt_dashboard_returns_data_and_meta(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        inspection_feishu_api,
        "get_mvt_dashboard_data",
        AsyncMock(
            return_value={
                "source_entity_code": "qc_finished_mvt",
                "source_label": "美伐他汀（DMF）",
                "charts": [],
                "alerts": [],
                "summary": {
                    "source_entity_code": "qc_finished_mvt",
                    "source_label": "美伐他汀（DMF）",
                    "total_records": 0,
                    "valid_record_count": 0,
                    "skipped_value_count": 0,
                    "alert_batch_count": 0,
                    "alert_metric_count": 0,
                    "first_notification_sent_count": 0,
                    "deduplicated_notification_count": 0,
                    "failed_notification_count": 0,
                    "unmapped_notification_count": 0,
                },
                "configured": True,
            }
        ),
    )

    response = await client.get("/api/v1/quality/inspection-finished/mvt/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["source_entity_code"] == "qc_finished_mvt"
    assert payload["data"]["source_label"] == "美伐他汀（DMF）"
    assert payload["meta"]["configured"] is True


@pytest.mark.anyio
async def test_get_lft_dashboard_returns_selected_source_data(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        inspection_feishu_api,
        "get_lft_dashboard_data",
        AsyncMock(
            return_value={
                "source_entity_code": "qc_finished_lft_usp",
                "source_label": "洛伐他汀（USP）",
                "charts": [],
                "alerts": [],
                "summary": {
                    "source_entity_code": "qc_finished_lft_usp",
                    "source_label": "洛伐他汀（USP）",
                    "total_records": 0,
                    "valid_record_count": 0,
                    "skipped_value_count": 0,
                    "alert_batch_count": 0,
                    "alert_metric_count": 0,
                    "first_notification_sent_count": 0,
                    "deduplicated_notification_count": 0,
                    "failed_notification_count": 0,
                    "unmapped_notification_count": 0,
                },
                "configured": True,
            }
        ),
    )

    response = await client.get(
        "/api/v1/quality/inspection-finished/lft/dashboard?entity_code=qc_finished_lft_usp"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["source_entity_code"] == "qc_finished_lft_usp"
    assert payload["data"]["source_label"] == "洛伐他汀（USP）"
    assert payload["meta"]["configured"] is True
