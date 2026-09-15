from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.requests import Request

from app.core.exceptions import AppException
from app.modules.quality.api import inspection_feishu as api


def _body(response: object) -> dict[str, object]:
    return json.loads(response.body)  # type: ignore[union-attr]


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/quality/items/inventory",
            "query_string": b"filter_status=active&filter_owner=qa",
            "headers": [],
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 123),
        }
    )


def _page() -> dict[str, object]:
    return {
        "items": [{"record_id": "rec-1"}],
        "page": 2,
        "page_size": 5,
        "total": 1,
        "fields": ["状态"],
    }


def _dashboard() -> dict[str, object]:
    return {
        "source_entity_code": "finished",
        "source_label": "成品检验",
        "charts": [],
        "alerts": [],
        "summary": {"total": 1},
        "configured": True,
    }


@pytest.mark.anyio
async def test_inspection_list_pull_and_subtable_routes_use_safe_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-1", feishu_open_id="ou-1")
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_require_user", Mock())
    monkeypatch.setattr(api, "try_acquire_action_lock", AsyncMock(return_value=True))
    request = _request()

    # 仪器管理：镜像优先列表（meta 带 source=local_mirror），列来自镜像快照
    instrument_list_routes = (
        (api.api_list_equipment, "qc_instr_equipment"),
        (api.api_list_maintenance, "qc_instr_maintenance"),
        (api.api_list_calibrations, "qc_instr_calibration"),
        (api.api_list_repairs, "qc_instr_repair"),
        (api.api_list_instr_contracts, "qc_instr_contracts"),
        (api.api_list_instr_plans, "qc_instr_plans"),
        (api.api_list_instr_cal_plans, "qc_instr_cal_plan"),
        (api.api_list_instr_cal_external, "qc_instr_cal_external"),
    )

    async def fake_list_instrument_mirror(
        _db: object,
        entity_code: str,
        *,
        keyword: str | None = None,
        filters: dict[str, str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, object]:
        return {
            "items": [{"record_id": "rec-1"}],
            "total": 1,
            "page": page,
            "page_size": page_size,
            "configured": True,
            "fields": ["状态"],
            "last_sync_time": "2026-09-14T00:00:00+00:00",
        }

    monkeypatch.setattr(api, "list_instrument_mirror", fake_list_instrument_mirror)
    for route, _entity_code in instrument_list_routes:
        response = await route(
            keyword="关键字",
            page=2,
            page_size=5,
            force=False,
            incremental=False,
            db=db,
            request=request,
            current_user=user,
        )
        assert response.status_code == 200
        assert _body(response)["data"] == [{"record_id": "rec-1"}]
        assert _body(response)["meta"]["fields"] == ["状态"]  # type: ignore[index]
        assert _body(response)["meta"]["source"] == "local_mirror"  # type: ignore[index]

    # 未同步（configured=False）→ 降级实时读（动态列），meta 无 source
    async def fake_list_instrument_mirror_empty(*_args: object, **_kwargs: object):
        return {
            "items": [],
            "total": 0,
            "page": 1,
            "page_size": 20,
            "configured": False,
            "fields": [],
            "last_sync_time": None,
        }

    monkeypatch.setattr(
        api, "list_instrument_mirror", fake_list_instrument_mirror_empty
    )
    monkeypatch.setattr(
        api,
        "_list_feishu_dynamic",
        AsyncMock(return_value=_page()),
    )
    live = await api.api_list_equipment(
        keyword=None,
        page=1,
        page_size=20,
        force=False,
        incremental=False,
        db=db,
        request=request,
        current_user=user,
    )
    assert _body(live)["meta"]["fields"] == ["状态"]  # type: ignore[index]
    assert "source" not in _body(live)["meta"]  # type: ignore[index]

    # 同步按钮：pull 端点触发仪器镜像全量同步
    instrument_pull_routes = (
        (api.api_pull_equipment, "qc_instr_equipment"),
        (api.api_pull_maintenance, "qc_instr_maintenance"),
        (api.api_pull_calibrations, "qc_instr_calibration"),
        (api.api_pull_repairs, "qc_instr_repair"),
        (api.api_pull_instr_contracts, "qc_instr_contracts"),
        (api.api_pull_instr_plans, "qc_instr_plans"),
        (api.api_pull_instr_cal_plans, "qc_instr_cal_plan"),
        (api.api_pull_instr_cal_external, "qc_instr_cal_external"),
    )
    pulled_entities: list[str] = []

    async def fake_sync_instrument_page(
        _db: object, entity_code: str, *, incremental: bool = True
    ) -> dict[str, int]:
        pulled_entities.append(entity_code)
        return {"synced": 1, "removed": 0, "total": 1}

    monkeypatch.setattr(api, "sync_instrument_page", fake_sync_instrument_page)
    for route, expected_entity in instrument_pull_routes:
        response = await route(db=db, current_user=user)
        assert response.status_code == 200
        assert _body(response)["data"]["synced"] == 1  # type: ignore[index]
    assert set(pulled_entities) == {entity for _, entity in instrument_pull_routes}

    monkeypatch.setattr(
        api,
        "list_finished_subtables",
        AsyncMock(
            return_value={"items": [{"entity_code": "finished"}], "configured": True}
        ),
    )
    subtables = await api.api_list_finished_subtables("mpa", user, db)
    assert _body(subtables)["meta"]["configured"] is True  # type: ignore[index]

    monkeypatch.setattr(api, "ensure_finished_entity_in_group", Mock())
    monkeypatch.setattr(api, "list_finished_by_entity", AsyncMock(return_value=_page()))
    finished = await api.api_list_finished_records(
        "mpa",
        entity_code="finished",
        keyword="批号",
        page=2,
        page_size=5,
        current_user=user,
        db=db,
        request=request,
    )
    assert _body(finished)["meta"]["total"] == 1  # type: ignore[index]

    monkeypatch.setattr(
        api,
        "list_material_subtables",
        AsyncMock(return_value={"items": [], "configured": False}),
    )
    solid_subtables = await api.api_list_solid_subtables("amino", user, db)
    liquid_subtables = await api.api_list_liquid_subtables("water", user, db)
    assert _body(solid_subtables)["meta"]["configured"] is False  # type: ignore[index]
    assert _body(liquid_subtables)["data"] == []

    monkeypatch.setattr(api, "ensure_material_entity_in_group", Mock())
    monkeypatch.setattr(
        api, "list_material_records_by_entity", AsyncMock(return_value=_page())
    )
    solid = await api.api_list_solid_records(
        "amino",
        entity_code="solid",
        keyword="物料",
        page=1,
        page_size=20,
        current_user=user,
        db=db,
        request=request,
    )
    liquid = await api.api_list_liquid_records(
        "water",
        entity_code="liquid",
        keyword="物料",
        page=1,
        page_size=20,
        current_user=user,
        db=db,
        request=request,
    )
    assert _body(solid)["meta"]["total"] == _body(liquid)["meta"]["total"]  # type: ignore[index]

    async def material_pull(_db: object, _entity_code: str) -> dict[str, int]:
        return {"synced": 2, "failed": 0}

    monkeypatch.setattr(api, "pull_finished_by_entity", material_pull)
    monkeypatch.setattr(api, "pull_material_records_by_entity", material_pull)
    finished_pull = await api.api_pull_finished("mpa", "finished", user, db)
    solid_pull = await api.api_pull_solid_records("amino", "solid", user, db)
    liquid_pull = await api.api_pull_liquid_records("water", "liquid", user, db)
    assert _body(finished_pull)["data"]["synced"] == 2  # type: ignore[index]
    assert _body(solid_pull)["data"]["synced"] == _body(liquid_pull)["data"]["synced"]  # type: ignore[index]


@pytest.mark.anyio
async def test_inspection_safe_helpers_and_dashboard_routes_cover_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _page()

    async def list_success(*_args: object, **_kwargs: object) -> dict[str, object]:
        return page

    success = await api._safe_list(list_success, SimpleNamespace(), page=3, page_size=7)
    assert _body(success)["meta"]["total"] == 1  # type: ignore[index]

    async def app_failure(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AppException(message="未配置", status_code=503)

    async def unexpected_failure(
        *_args: object, **_kwargs: object
    ) -> dict[str, object]:
        raise RuntimeError("飞书不可用")

    for failed in (app_failure, unexpected_failure):
        response = await api._safe_list(failed, SimpleNamespace(), page=4, page_size=8)
        assert _body(response)["data"] == []
        assert _body(response)["meta"]["configured"] is False  # type: ignore[index]

    monkeypatch.setattr(api, "try_acquire_action_lock", AsyncMock(return_value=False))

    async def pull_success(*_args: object, **_kwargs: object) -> dict[str, int]:
        return {"synced": 1, "failed": 0}

    locked = await api._safe_pull(pull_success, SimpleNamespace())
    assert _body(locked)["data"]["synced"] == 0  # type: ignore[index]

    monkeypatch.setattr(api, "try_acquire_action_lock", AsyncMock(return_value=True))
    pulled = await api._safe_pull(pull_success, SimpleNamespace())
    assert _body(pulled)["data"] == {"synced": 1, "failed": 0}

    async def pull_not_configured(*_args: object, **_kwargs: object) -> dict[str, int]:
        raise AppException(message="未配置", status_code=503)

    async def pull_error(*_args: object, **_kwargs: object) -> dict[str, int]:
        raise RuntimeError("timeout")

    for failed, expected in (
        (pull_not_configured, "飞书未配置"),
        (pull_error, "timeout"),
    ):
        response = await api._safe_pull(failed, SimpleNamespace())
        assert _body(response)["data"]["error"] == expected  # type: ignore[index]

    user = SimpleNamespace(id="user-1", feishu_open_id="ou-1")
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_require_user", Mock())
    dashboard = _dashboard()
    monkeypatch.setitem(
        api._DASHBOARD_GROUP_FETCHERS, "mpa", AsyncMock(return_value=dashboard)
    )
    unified = await api.api_get_inspection_dashboard("mpa", "custom", user, db)
    assert _body(unified)["data"]["source_entity_code"] == "finished"  # type: ignore[index]

    dashboard_routes = (
        (api.api_get_mpa_dashboard, "get_mpa_dashboard_data"),
        (api.api_get_lft_dashboard, "get_lft_dashboard_data"),
        (api.api_get_dls_dashboard, "get_dls_dashboard_data"),
        (api.api_get_lkms_dashboard, "get_lkms_dashboard_data"),
        (api.api_get_bbas_dashboard, "get_bbas_dashboard_data"),
        (api.api_get_tryptophan_dashboard, "get_tryptophan_dashboard_data"),
        (api.api_get_water_dashboard, "get_water_dashboard_data"),
        (api.api_get_formulations_dashboard, "get_formulations_dashboard_data"),
    )
    for route, service_name in dashboard_routes:
        fetcher = AsyncMock(return_value=dashboard)
        monkeypatch.setattr(api, service_name, fetcher)
        response = await route(current_user=user, db=db)
        assert response.status_code == 200
        assert _body(response)["meta"]["configured"] is True  # type: ignore[index]

    mvt = AsyncMock(return_value=dashboard)
    monkeypatch.setattr(api, "get_mvt_dashboard_data", mvt)
    response = await api.api_get_mvt_dashboard(current_user=user, db=db)
    assert response.status_code == 200
    assert mvt.await_count == 1
