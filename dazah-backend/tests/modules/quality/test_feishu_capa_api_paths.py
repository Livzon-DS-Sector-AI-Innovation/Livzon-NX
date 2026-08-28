from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import AppException
from app.modules.quality.api import feishu_capa as api


def _page() -> dict[str, object]:
    return {"items": [], "page": 1, "page_size": 50, "total": 0}


def _request() -> SimpleNamespace:
    return SimpleNamespace(model_dump=Mock(return_value={"name": "value"}))


@pytest.mark.anyio
async def test_feishu_capa_api_success_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_require_user", Mock(return_value="user-1"))
    monkeypatch.setattr(api, "list_capa_ledger", AsyncMock(return_value=_page()))
    monkeypatch.setattr(
        api,
        "get_capa_ledger_record",
        AsyncMock(return_value={"record_id": "capa-1"}),
    )
    monkeypatch.setattr(
        api,
        "create_capa_ledger_record",
        AsyncMock(return_value={"record_id": "capa-1"}),
    )
    monkeypatch.setattr(
        api,
        "update_capa_ledger_record",
        AsyncMock(return_value={"record_id": "capa-1"}),
    )
    monkeypatch.setattr(api, "delete_capa_ledger_record", AsyncMock())
    monkeypatch.setattr(api, "list_capa_plan_tracks", AsyncMock(return_value=_page()))
    monkeypatch.setattr(
        api,
        "get_capa_plan_track_record",
        AsyncMock(return_value={"record_id": "track-1"}),
    )
    monkeypatch.setattr(
        api,
        "create_capa_plan_track_record",
        AsyncMock(return_value={"record_id": "track-1"}),
    )
    monkeypatch.setattr(
        api,
        "update_capa_plan_track_record",
        AsyncMock(return_value={"record_id": "track-1"}),
    )
    monkeypatch.setattr(api, "delete_capa_plan_track_record", AsyncMock())
    monkeypatch.setattr(api, "generate_capa_export_docx", Mock(return_value=b"docx"))

    assert (
        await api.api_list_capa_ledger(
            keyword="CAPA", page=2, page_size=10, current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_export_capa_ledger(
            keyword="CAPA", department="质量部", current_user=user, db=db
        )
    ).media_type.endswith("wordprocessingml.document")
    assert (
        await api.api_get_capa_ledger_record("capa-1", current_user=user, db=db)
    ).status_code == 200
    assert (
        await api.api_create_capa_ledger_record(_request(), current_user=user, db=db)
    ).status_code == 200
    assert (
        await api.api_update_capa_ledger_record(
            "capa-1", _request(), current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_delete_capa_ledger_record("capa-1", current_user=user, db=db)
    ).status_code == 200

    assert (
        await api.api_list_capa_plan_tracks(
            keyword="计划", page=2, page_size=10, current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_get_capa_plan_track_record("track-1", current_user=user, db=db)
    ).status_code == 200
    assert (
        await api.api_create_capa_plan_track_record(
            _request(), current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_update_capa_plan_track_record(
            "track-1", _request(), current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_delete_capa_plan_track_record("track-1", current_user=user, db=db)
    ).status_code == 200


@pytest.mark.anyio
async def test_feishu_capa_api_maps_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_require_user", Mock(return_value="user-1"))
    cases = [
        (api.api_list_capa_ledger, "list_capa_ledger", {}),
        (api.api_export_capa_ledger, "list_capa_ledger", {}),
        (api.api_get_capa_ledger_record, "get_capa_ledger_record", {"record_id": "c1"}),
        (
            api.api_create_capa_ledger_record,
            "create_capa_ledger_record",
            {"data": _request()},
        ),
        (
            api.api_update_capa_ledger_record,
            "update_capa_ledger_record",
            {"record_id": "c1", "data": _request()},
        ),
        (
            api.api_delete_capa_ledger_record,
            "delete_capa_ledger_record",
            {"record_id": "c1"},
        ),
        (api.api_list_capa_plan_tracks, "list_capa_plan_tracks", {}),
        (
            api.api_get_capa_plan_track_record,
            "get_capa_plan_track_record",
            {"record_id": "t1"},
        ),
        (
            api.api_create_capa_plan_track_record,
            "create_capa_plan_track_record",
            {"data": _request()},
        ),
        (
            api.api_update_capa_plan_track_record,
            "update_capa_plan_track_record",
            {"record_id": "t1", "data": _request()},
        ),
        (
            api.api_delete_capa_plan_track_record,
            "delete_capa_plan_track_record",
            {"record_id": "t1"},
        ),
    ]
    for endpoint, service_name, kwargs in cases:
        monkeypatch.setattr(
            api, service_name, AsyncMock(side_effect=RuntimeError("provider"))
        )
        with pytest.raises(AppException) as exc_info:
            await endpoint(current_user=user, db=db, **kwargs)
        assert exc_info.value.status_code == 500

    for endpoint, service_name, kwargs in cases[5:]:
        monkeypatch.setattr(
            api,
            service_name,
            AsyncMock(side_effect=AppException(status_code=409, message="conflict")),
        )
        with pytest.raises(AppException) as exc_info:
            await endpoint(current_user=user, db=db, **kwargs)
        assert exc_info.value.status_code == 409
