from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.quality.api import oos_oot_feishu as api


@pytest.mark.asyncio
async def test_oos_oot_feishu_api_wrappers_cover_all_legacy_page_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "_require_user", Mock())
    page_result = {"items": [], "page": 1, "page_size": 20, "total": 0}
    for name in (
        "list_oos_oot_report_records",
        "list_oos_oot_investigation_push_records",
        "list_oos_ledger_records",
        "list_oot_ledger_records",
        "list_product_department_records",
    ):
        monkeypatch.setattr(api, name, AsyncMock(return_value=page_result))
    for name in (
        "create_oos_oot_report_record",
        "create_oos_oot_investigation_push_record",
        "create_oos_ledger_record",
        "create_oot_ledger_record",
        "create_product_department_record",
        "update_oos_oot_report_record",
        "update_oos_oot_investigation_push_record",
        "update_oos_ledger_record",
        "update_oot_ledger_record",
        "update_product_department_record",
    ):
        monkeypatch.setattr(api, name, AsyncMock(return_value={"record_id": "r1"}))
    for name in (
        "delete_oos_oot_report_record",
        "delete_oos_oot_investigation_push_record",
        "delete_oos_ledger_record",
        "delete_oot_ledger_record",
        "delete_product_department_record",
    ):
        monkeypatch.setattr(api, name, AsyncMock())
    for name in (
        "pull_oos_oot_report_records",
        "pull_oos_oot_investigation_push_records",
        "pull_oos_ledger_records",
        "pull_oot_ledger_records",
        "pull_product_department_records",
    ):
        monkeypatch.setattr(
            api, name, AsyncMock(return_value={"synced": 1, "failed": 0})
        )
    monkeypatch.setattr(
        api, "export_oos_ledger", AsyncMock(return_value=BytesIO(b"oos"))
    )
    monkeypatch.setattr(
        api, "export_oot_ledger", AsyncMock(return_value=BytesIO(b"oot"))
    )

    user = SimpleNamespace(id="user-1")
    db = SimpleNamespace()
    assert (
        await api.api_list_report_records(
            page=1, page_size=20, current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_list_investigation_push_records(
            page=1, page_size=20, current_user=user, db=db
        )
    ).status_code == 200
    assert (
        await api.api_list_oos_ledger(page=1, page_size=20, current_user=user, db=db)
    ).status_code == 200
    assert (
        await api.api_list_oot_ledger(page=1, page_size=20, current_user=user, db=db)
    ).status_code == 200
    assert (
        await api.api_list_product_departments(
            page=1, page_size=20, current_user=user, db=db
        )
    ).status_code == 200

    assert (await api.api_create_report_record({}, user, db)).status_code == 200
    assert (
        await api.api_create_investigation_push_record({}, user, db)
    ).status_code == 200
    assert (await api.api_create_oos_ledger({}, user, db)).status_code == 200
    assert (await api.api_create_oot_ledger({}, user, db)).status_code == 200
    assert (await api.api_create_product_department({}, user, db)).status_code == 200

    assert (await api.api_update_report_record("r1", {}, user, db)).status_code == 200
    assert (
        await api.api_update_investigation_push_record("r1", {}, user, db)
    ).status_code == 200
    assert (await api.api_update_oos_ledger("r1", {}, user, db)).status_code == 200
    assert (await api.api_update_oot_ledger("r1", {}, user, db)).status_code == 200
    assert (
        await api.api_update_product_department("r1", {}, user, db)
    ).status_code == 200

    assert (await api.api_delete_report_record("r1", user, db)).status_code == 200
    assert (
        await api.api_delete_investigation_push_record("r1", user, db)
    ).status_code == 200
    assert (await api.api_delete_oos_ledger("r1", user, db)).status_code == 200
    assert (await api.api_delete_oot_ledger("r1", user, db)).status_code == 200
    assert (await api.api_delete_product_department("r1", user, db)).status_code == 200

    assert (await api.api_pull_report_records(user, db)).status_code == 200
    assert (await api.api_pull_investigation_push_records(user, db)).status_code == 200
    assert (await api.api_pull_oos_ledger(user, db)).status_code == 200
    assert (await api.api_pull_oot_ledger(user, db)).status_code == 200
    assert (await api.api_pull_product_departments(user, db)).status_code == 200
    assert (
        (await api.api_export_oos_ledger(user, db))
        .headers["content-disposition"]
        .startswith("attachment")
    )
    assert (
        (await api.api_export_oot_ledger(user, db))
        .headers["content-disposition"]
        .startswith("attachment")
    )
