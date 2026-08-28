from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.hr import api


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), name="测试用户", feishu_open_id="ou-user")


def _page() -> SimpleNamespace:
    return SimpleNamespace(page=1, page_size=20)


def _patch_response_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api,
        "success_response",
        lambda **kwargs: {
            "data": kwargs.get("data"),
            "meta": kwargs.get("meta"),
            "message": kwargs.get("message"),
        },
    )
    monkeypatch.setattr(
        api,
        "paginated_response",
        lambda **kwargs: {
            "data": kwargs.get("data"),
            "meta": {
                "page": kwargs.get("page"),
                "page_size": kwargs.get("page_size"),
                "total": kwargs.get("total"),
            },
        },
    )


@pytest.mark.asyncio
async def test_hr_legacy_and_migrated_list_routes_delegate_with_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    db = SimpleNamespace()
    scope = AsyncMock(return_value={"质量部"})
    monkeypatch.setattr(api, "_resolve_visible_scope", scope)
    monkeypatch.setattr(api, "_assert_dept_in_scope", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_assert_employee_page_access", AsyncMock())
    _patch_response_helpers(monkeypatch)

    employee_service = SimpleNamespace(
        session=db,
        list_employees=AsyncMock(return_value=([], 0)),
        get_employee_stats=AsyncMock(return_value={"total": 0}),
        list_contract_expiring=AsyncMock(return_value=([], 0)),
        sync_from_feishu=AsyncMock(
            return_value={"created": 1, "updated": 2, "deleted": 0, "failed": 0}
        ),
        get_sync_status=AsyncMock(
            return_value=SimpleNamespace(model_dump=lambda **_kwargs: {})
        ),
        delete_employee=AsyncMock(return_value="success"),
        sync_to_feishu=AsyncMock(return_value="rec-1"),
    )
    assert (
        await api.list_employees(
            department="质量部",
            status="在职",
            keyword="",
            page_params=_page(),
            db=db,
            service=employee_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.get_employee_stats(db=db, service=employee_service, current_user=user)
    )["data"] == {"total": 0}
    assert (
        await api.list_contract_expiring(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            department="质量部",
            page=1,
            page_size=20,
            db=db,
            service=employee_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.sync_employees_from_feishu(
            service=employee_service, current_user=user
        )
    )["data"]["created"] == 1
    assert (
        await api.get_employee_sync_status(service=employee_service, current_user=user)
    )["data"] == {}
    assert (
        await api.delete_employee(
            employee_id=uuid4(), service=employee_service, current_user=user
        )
    )["meta"]["feishu_sync_status"] == "success"
    assert (
        await api.sync_employee_to_feishu(
            employee_id=uuid4(), service=employee_service, current_user=user
        )
    )["data"]["feishu_record_id"] == "rec-1"

    department_service = SimpleNamespace(
        list_departments=AsyncMock(return_value=([], 0)),
        get_department_tree=AsyncMock(return_value=[]),
        get_org_tree=AsyncMock(return_value=[]),
        delete_department=AsyncMock(),
    )
    assert (
        await api.list_departments(
            page_params=_page(), service=department_service, current_user=user
        )
    )["data"] == []
    assert (
        await api.get_department_tree(service=department_service, current_user=user)
    )["data"] == []
    assert (await api.get_org_tree(service=department_service, current_user=user))[
        "data"
    ] == []
    await api.delete_department(
        department_id=uuid4(), service=department_service, current_user=user
    )

    team_service = SimpleNamespace(list_teams=AsyncMock(return_value=([], 0)))
    assert (
        await api.list_teams(
            department_id=None,
            keyword=None,
            page_params=_page(),
            service=team_service,
            current_user=user,
        )
    )["data"] == []

    offboarding_service = SimpleNamespace(
        list_records=AsyncMock(return_value=([], 0)),
        sync_from_feishu=AsyncMock(
            return_value={"created": 0, "updated": 0, "deleted": 0, "failed": 0}
        ),
        delete_record=AsyncMock(),
    )
    assert (
        await api.list_offboarding_records(
            employee_id=None,
            keyword=None,
            page_params=_page(),
            db=db,
            service=offboarding_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.sync_offboarding_from_feishu(
            service=offboarding_service, current_user=user
        )
    )["data"]["failed"] == 0
    await api.delete_offboarding_record(
        record_id=uuid4(), service=offboarding_service, current_user=user
    )

    transfer_service = SimpleNamespace(
        list_records=AsyncMock(return_value=([], 0)),
        list_approvals=AsyncMock(return_value=([], 0)),
        sync_from_feishu=AsyncMock(return_value={"total": 0}),
        delete_record=AsyncMock(),
    )
    assert (
        await api.list_position_transfers(
            employee_id=None,
            approval_status=None,
            keyword=None,
            page_params=_page(),
            db=db,
            service=transfer_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.list_position_transfer_approvals(
            tab="approved",
            page_params=_page(),
            service=transfer_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.sync_position_transfers_from_feishu(
            service=transfer_service, current_user=user
        )
    )["data"]["total"] == 0
    await api.delete_position_transfer(
        record_id=uuid4(), service=transfer_service, current_user=user
    )


@pytest.mark.asyncio
async def test_hr_training_and_page_routes_delegate_without_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    db = SimpleNamespace()
    monkeypatch.setattr(api, "_resolve_visible_scope", AsyncMock(return_value=None))
    _patch_response_helpers(monkeypatch)
    monkeypatch.setattr(
        "app.platform.identity.rbac.resolve_user_permissions",
        AsyncMock(return_value={"*"}),
    )
    ledger_service = SimpleNamespace(
        list_records=AsyncMock(return_value=([], 0)),
        list_by_department=AsyncMock(return_value=([], 0)),
        list_training_departments=AsyncMock(return_value=[]),
        list_custom_training_departments=AsyncMock(return_value=[]),
        list_dept_mappings=AsyncMock(return_value=[]),
        delete_custom_training_department=AsyncMock(return_value=True),
        delete_dept_mapping=AsyncMock(return_value=True),
        list_pages=AsyncMock(return_value=[]),
    )
    assert (
        await api.list_training_ledgers(
            employee_number=None,
            department=None,
            date_from=None,
            date_to=None,
            session_id=None,
            page_params=_page(),
            db=db,
            service=ledger_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.list_training_departments(service=ledger_service, current_user=user)
    )["data"] == []
    assert (
        await api.list_custom_training_departments(
            service=ledger_service, current_user=user
        )
    )["data"] == []
    assert (
        await api.list_training_dept_mappings(service=ledger_service, current_user=user)
    )["data"] == []
    await api.delete_custom_training_department(
        "质量部", service=ledger_service, current_user=user
    )
    await api.delete_training_dept_mapping(
        uuid4(), db=db, service=ledger_service, current_user=user
    )

    page_service = SimpleNamespace(
        list_pages=AsyncMock(return_value=[]),
        list_pages_with_department=AsyncMock(return_value=[]),
    )
    assert (
        await api.list_training_ledger_pages(service=page_service, current_user=user)
    )["data"] == []
    personnel_service = SimpleNamespace(
        list_configs=AsyncMock(return_value=[]),
        delete_config=AsyncMock(),
        list_new_hires=AsyncMock(return_value=[]),
    )
    assert (
        await api.list_training_personnel_configs(
            level=None,
            department=None,
            db=db,
            service=personnel_service,
            current_user=user,
        )
    )["data"] == []
    assert (
        await api.list_new_hires(
            days=7, db=db, service=personnel_service, current_user=user
        )
    )["data"] == []
    await api.delete_training_personnel_config(
        config_id=uuid4(), service=personnel_service, current_user=user
    )


def test_hr_api_parsers_and_header_helpers_cover_legacy_import_shapes() -> None:
    assert api._parse_excel_date(date(2026, 8, 20)) == date(2026, 8, 20)
    assert api._parse_excel_date("2026/08/20") == date(2026, 8, 20)
    assert api._parse_excel_date("bad") is None
    assert api._calc_duration_from_text("09:00~10:30") == 1.5
    assert api._calc_duration_from_text("全天") is None
    assert api._clip("abcdef", 3) == "abc"
    assert api._clip(None, 3) is None
    assert api._cell_text({"text": "张三"}) == "{'text': '张三'}"
    assert api._cell_text([{"text": "李四"}]) == "[{'text': '李四'}]"
    assert api._cell_text(None) is None
    assert api._map_headers_by_alias(["培训主题", "培训日期", "其他"]) == {
        "1": "training_date"
    }
