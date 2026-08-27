from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import AppException
from app.modules.quality.api import oos_oot_feishu as api


def _body(response: object) -> dict[str, object]:
    return json.loads(response.body)  # type: ignore[union-attr]


def _page() -> dict[str, object]:
    return {"items": [{"record_id": "rec-1"}], "page": 2, "page_size": 5, "total": 1}


@pytest.mark.anyio
async def test_legacy_oos_oot_feishu_api_success_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_require_user", Mock())

    list_functions = {
        "list_oos_oot_report_records": _page(),
        "list_oos_oot_investigation_push_records": _page(),
        "list_oos_ledger_records": _page(),
        "list_oot_ledger_records": _page(),
        "list_product_department_records": _page(),
    }
    for name, result in list_functions.items():
        monkeypatch.setattr(api, name, AsyncMock(return_value=result))

    report_list = await api.api_list_report_records(
        keyword="产品", page=2, page_size=5, current_user=user, db=db
    )
    push_list = await api.api_list_investigation_push_records(
        oos_oot_code="OOS-1",
        push_round="2",
        department_head_result="通过",
        qa_result="通过",
        qa_head_result="待审",
        process_status="处理中",
        page=2,
        page_size=5,
        current_user=user,
        db=db,
    )
    oos_list = await api.api_list_oos_ledger(
        keyword="物料", page=2, page_size=5, current_user=user, db=db
    )
    oot_list = await api.api_list_oot_ledger(
        keyword="物料", page=2, page_size=5, current_user=user, db=db
    )
    product_list = await api.api_list_product_departments(
        keyword="产品", page=2, page_size=5, current_user=user, db=db
    )
    for response in (report_list, push_list, oos_list, oot_list, product_list):
        assert response.status_code == 200
        assert _body(response)["meta"]["total"] == 1  # type: ignore[index]

    create_functions = (
        "create_oos_oot_report_record",
        "create_oos_oot_investigation_push_record",
        "create_oos_ledger_record",
        "create_oot_ledger_record",
        "create_product_department_record",
    )
    update_functions = (
        "update_oos_oot_report_record",
        "update_oos_oot_investigation_push_record",
        "update_oos_ledger_record",
        "update_oot_ledger_record",
        "update_product_department_record",
    )
    delete_functions = (
        "delete_oos_oot_report_record",
        "delete_oos_oot_investigation_push_record",
        "delete_oos_ledger_record",
        "delete_oot_ledger_record",
        "delete_product_department_record",
    )
    for name in create_functions + update_functions + delete_functions:
        monkeypatch.setattr(api, name, AsyncMock(return_value={"record_id": "rec-1"}))

    created = await api.api_create_report_record(
        {"content": "偏差"}, current_user=user, db=db
    )
    created_push = await api.api_create_investigation_push_record(
        {"oos_oot_code": "OOS-1"}, current_user=user, db=db
    )
    created_oos = await api.api_create_oos_ledger(
        {"material_name": "物料"}, current_user=user, db=db
    )
    created_oot = await api.api_create_oot_ledger(
        {"material_name": "物料"}, current_user=user, db=db
    )
    created_product = await api.api_create_product_department(
        {"product_code": "P-1"}, current_user=user, db=db
    )
    for response in (created, created_push, created_oos, created_oot, created_product):
        assert response.status_code == 200
        assert _body(response)["data"]["record_id"] == "rec-1"  # type: ignore[index]

    updated = await api.api_update_report_record(
        "rec-1", {"content": "更新"}, current_user=user, db=db
    )
    updated_push = await api.api_update_investigation_push_record(
        "rec-1", {"process_status": "完成"}, current_user=user, db=db
    )
    updated_oos = await api.api_update_oos_ledger(
        "rec-1", {"root_cause": "方法"}, current_user=user, db=db
    )
    updated_oot = await api.api_update_oot_ledger(
        "rec-1", {"root_cause": "方法"}, current_user=user, db=db
    )
    updated_product = await api.api_update_product_department(
        "rec-1", {"fermentation_department": "发酵部"}, current_user=user, db=db
    )
    for response in (updated, updated_push, updated_oos, updated_oot, updated_product):
        assert response.status_code == 200
        assert _body(response)["data"]["record_id"] == "rec-1"  # type: ignore[index]

    deleted = await api.api_delete_report_record("rec-1", current_user=user, db=db)
    deleted_push = await api.api_delete_investigation_push_record(
        "rec-1", current_user=user, db=db
    )
    deleted_oos = await api.api_delete_oos_ledger("rec-1", current_user=user, db=db)
    deleted_oot = await api.api_delete_oot_ledger("rec-1", current_user=user, db=db)
    deleted_product = await api.api_delete_product_department(
        "rec-1", current_user=user, db=db
    )
    for response in (deleted, deleted_push, deleted_oos, deleted_oot, deleted_product):
        assert response.status_code == 200
        assert _body(response)["message"] == "已删除"

    pull_functions = (
        "pull_oos_oot_report_records",
        "pull_oos_oot_investigation_push_records",
        "pull_oos_ledger_records",
        "pull_oot_ledger_records",
        "pull_product_department_records",
    )
    for name in pull_functions:
        monkeypatch.setattr(
            api, name, AsyncMock(return_value={"synced": 1, "failed": 0})
        )

    pulled = (
        await api.api_pull_report_records(current_user=user, db=db),
        await api.api_pull_investigation_push_records(current_user=user, db=db),
        await api.api_pull_oos_ledger(current_user=user, db=db),
        await api.api_pull_oot_ledger(current_user=user, db=db),
        await api.api_pull_product_departments(current_user=user, db=db),
    )
    for response in pulled:
        assert response.status_code == 200
        assert _body(response)["data"] == {"synced": 1, "failed": 0}

    monkeypatch.setattr(api, "export_oos_ledger", AsyncMock(return_value=[b"oos"]))
    monkeypatch.setattr(api, "export_oot_ledger", AsyncMock(return_value=[b"oot"]))
    oos_export = await api.api_export_oos_ledger(current_user=user, db=db)
    oot_export = await api.api_export_oot_ledger(current_user=user, db=db)
    assert oos_export.status_code == oot_export.status_code == 200
    assert "attachment" in oos_export.headers["content-disposition"]
    assert "attachment" in oot_export.headers["content-disposition"]


@pytest.mark.anyio
async def test_legacy_oos_oot_feishu_api_maps_service_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_require_user", Mock())
    cases = [
        ("api_list_report_records", "list_oos_oot_report_records", {}),
        ("api_create_report_record", "create_oos_oot_report_record", {"data": {}}),
        (
            "api_update_report_record",
            "update_oos_oot_report_record",
            {"record_id": "r1", "data": {}},
        ),
        (
            "api_delete_report_record",
            "delete_oos_oot_report_record",
            {"record_id": "r1"},
        ),
        ("api_export_oos_ledger", "export_oos_ledger", {}),
        ("api_export_oot_ledger", "export_oot_ledger", {}),
        ("api_pull_report_records", "pull_oos_oot_report_records", {}),
        (
            "api_list_investigation_push_records",
            "list_oos_oot_investigation_push_records",
            {},
        ),
        (
            "api_create_investigation_push_record",
            "create_oos_oot_investigation_push_record",
            {"data": {}},
        ),
        (
            "api_update_investigation_push_record",
            "update_oos_oot_investigation_push_record",
            {"record_id": "r1", "data": {}},
        ),
        (
            "api_delete_investigation_push_record",
            "delete_oos_oot_investigation_push_record",
            {"record_id": "r1"},
        ),
        (
            "api_pull_investigation_push_records",
            "pull_oos_oot_investigation_push_records",
            {},
        ),
        ("api_list_oos_ledger", "list_oos_ledger_records", {}),
        ("api_create_oos_ledger", "create_oos_ledger_record", {"data": {}}),
        (
            "api_update_oos_ledger",
            "update_oos_ledger_record",
            {"record_id": "r1", "data": {}},
        ),
        ("api_delete_oos_ledger", "delete_oos_ledger_record", {"record_id": "r1"}),
        ("api_pull_oos_ledger", "pull_oos_ledger_records", {}),
        ("api_list_oot_ledger", "list_oot_ledger_records", {}),
        ("api_create_oot_ledger", "create_oot_ledger_record", {"data": {}}),
        (
            "api_update_oot_ledger",
            "update_oot_ledger_record",
            {"record_id": "r1", "data": {}},
        ),
        ("api_delete_oot_ledger", "delete_oot_ledger_record", {"record_id": "r1"}),
        ("api_pull_oot_ledger", "pull_oot_ledger_records", {}),
        ("api_list_product_departments", "list_product_department_records", {}),
        (
            "api_create_product_department",
            "create_product_department_record",
            {"data": {}},
        ),
        (
            "api_update_product_department",
            "update_product_department_record",
            {"record_id": "r1", "data": {}},
        ),
        (
            "api_delete_product_department",
            "delete_product_department_record",
            {"record_id": "r1"},
        ),
        ("api_pull_product_departments", "pull_product_department_records", {}),
    ]
    for endpoint_name, service_name, extra in cases:
        monkeypatch.setattr(
            api, service_name, AsyncMock(side_effect=RuntimeError("provider"))
        )
        endpoint = getattr(api, endpoint_name)
        response = await endpoint(current_user=user, db=db, **extra)
        assert response.status_code == 500, endpoint_name

    monkeypatch.setattr(
        api,
        "list_oos_oot_report_records",
        AsyncMock(side_effect=AppException(status_code=409, message="冲突")),
    )
    with pytest.raises(AppException):
        await api.api_list_report_records(current_user=user, db=db)
