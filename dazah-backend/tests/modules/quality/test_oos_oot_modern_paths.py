from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.quality.api import oos_oot as api


class _Result:
    def __init__(
        self, *, scalar: object | None = None, rows: list[object] | None = None
    ) -> None:
        self.scalar_value = scalar
        self.rows = rows or []

    def scalar(self) -> object | None:
        return self.scalar_value

    def scalar_one(self) -> object:
        assert self.scalar_value is not None
        return self.scalar_value

    def scalar_one_or_none(self) -> object | None:
        return self.scalar_value

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


class _Db:
    def __init__(self, results: list[_Result]) -> None:
        self.results = iter(results)
        self.added: list[object] = []
        self.flush = AsyncMock()

    async def execute(self, _statement: object) -> _Result:
        return next(self.results)

    def add(self, value: object) -> None:
        self.added.append(value)


def _record(record_id: object | None = None) -> SimpleNamespace:
    now = datetime(2026, 8, 27, 10, 0)
    return SimpleNamespace(
        id=record_id or uuid4(),
        record_code="OOS-001",
        record_type="OOS",
        title="原料检验异常",
        department="质量部",
        product_name="多拉菌素",
        batch_number="B-001",
        test_item="含量",
        specification="98-102%",
        test_result="97%",
        discovery_date=date(2026, 8, 27),
        description="超限",
        investigation_result=None,
        corrective_actions=None,
        status="open",
        closed_at=None,
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )


@pytest.mark.asyncio
async def test_modern_oos_oot_crud_scope_and_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(api, "_require_user", Mock())
    monkeypatch.setattr(api, "paginated_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "success_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "error_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        "app.platform.identity.data_scope.resolve_user_department_scope",
        AsyncMock(return_value={"质量部"}),
    )
    monkeypatch.setattr(
        "app.platform.identity.data_scope.department_in_clause",
        lambda _column, _scope: None,
    )

    record = _record()
    listed = await api.list_oos_oot(
        record_type="OOS",
        status="open",
        department="质量部",
        keyword="异常",
        page=2,
        page_size=10,
        db=_Db([_Result(scalar=1), _Result(rows=[record])]),
        current_user=user,
    )
    assert listed["total"] == 1
    assert listed["data"][0]["record_code"] == "OOS-001"

    found = await api.get_oos_oot(record.id, _Db([_Result(scalar=record)]), user)
    assert found["data"]["id"] == str(record.id)
    missing = await api.get_oos_oot(uuid4(), _Db([_Result(scalar=None)]), user)
    assert missing["status_code"] == 404

    create_data = api.CreateOosOotRequest(
        record_code="OOS-002", title="新增异常", department="质量部"
    )
    created_record = _record()
    created_record.record_code = "OOS-002"
    create_db = _Db([_Result(scalar=created_record)])
    created = await api.create_oos_oot(create_data, create_db, user)
    assert created["message"] == "创建成功"
    assert len(create_db.added) == 1

    update_record = _record(record.id)
    update_db = _Db([_Result(scalar=update_record), _Result(scalar=update_record)])
    updated = await api.update_oos_oot(
        record.id,
        api.UpdateOosOotRequest(status="investigating", description="复核中"),
        update_db,
        user,
    )
    assert updated["message"] == "更新成功"
    assert update_record.status == "investigating"

    not_found_update = await api.update_oos_oot(
        uuid4(),
        api.UpdateOosOotRequest(status="closed"),
        _Db([_Result(scalar=None)]),
        user,
    )
    assert not_found_update["status_code"] == 404

    deleted_record = _record()
    deleted = await api.delete_oos_oot(
        deleted_record.id, _Db([_Result(scalar=deleted_record)]), user
    )
    assert deleted["message"] == "已删除"
    assert deleted_record.is_deleted is True
    not_found_delete = await api.delete_oos_oot(
        uuid4(), _Db([_Result(scalar=None)]), user
    )
    assert not_found_delete["status_code"] == 404


@pytest.mark.asyncio
async def test_modern_oos_oot_api_maps_database_failures_to_safe_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(api, "_require_user", Mock())
    monkeypatch.setattr(api, "paginated_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "success_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(api, "error_response", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        "app.platform.identity.data_scope.resolve_user_department_scope",
        AsyncMock(return_value=None),
    )

    class _FailDb:
        async def execute(self, _statement: object) -> object:
            raise RuntimeError("db unavailable")

    listed = await api.list_oos_oot(db=_FailDb(), current_user=user)
    assert listed["status_code"] == 500

    record_id = uuid4()
    assert (await api.get_oos_oot(record_id, _FailDb(), user))["status_code"] == 500
    assert (
        await api.create_oos_oot(
            api.CreateOosOotRequest(record_code="OOS-ERR", title="错误"),
            _FailDb(),
            user,
        )
    )["status_code"] == 400
    assert (
        await api.update_oos_oot(
            record_id, api.UpdateOosOotRequest(status="closed"), _FailDb(), user
        )
    )["status_code"] == 400
    assert (await api.delete_oos_oot(record_id, _FailDb(), user))["status_code"] == 500


@pytest.mark.asyncio
async def test_oos_oot_legacy_routes_delegate_all_compatibility_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid4())
    record_id = uuid4()
    product_id = uuid4()
    item_id = uuid4()
    record = _record(record_id)
    now = datetime(2026, 8, 27, 10, 0)
    product = SimpleNamespace(
        id=product_id,
        product_code="P-1",
        product_name="产品",
        document_title="通知单",
        document_year=2026,
        version_label="V1",
        source_file_name="limits.xlsx",
        remark="备注",
        created_at=now,
        updated_at=now,
    )
    item = SimpleNamespace(
        id=item_id,
        product_id=product_id,
        display_order=1,
        item_group="理化",
        item_name="含量",
        standard_value="98%",
        oot_limit_value="97%",
        remark="备注",
        created_at=now,
        updated_at=now,
    )
    db = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(api, "_require_user", Mock())
    service_functions = {
        "list_oos_oot_records": AsyncMock(return_value=([record], 1)),
        "create_oos_oot_record": AsyncMock(return_value=record),
        "start_oos_oot_investigation": AsyncMock(return_value=record),
        "close_oos_oot_record": AsyncMock(return_value=record),
        "get_oos_oot_record": AsyncMock(return_value=record),
        "update_oos_oot_record": AsyncMock(return_value=record),
        "delete_oos_oot_record": AsyncMock(),
        "create_oot_limit_product": AsyncMock(return_value=product),
        "list_oot_limit_products": AsyncMock(return_value=[product]),
        "get_oot_limit_product": AsyncMock(return_value=product),
        "update_oot_limit_product": AsyncMock(return_value=product),
        "delete_oot_limit_product": AsyncMock(),
        "create_oot_limit_item": AsyncMock(return_value=item),
        "list_oot_limit_items": AsyncMock(return_value=[item]),
        "update_oot_limit_item": AsyncMock(return_value=item),
        "delete_oot_limit_item": AsyncMock(),
    }
    for name, value in service_functions.items():
        monkeypatch.setattr(api.oos_oot_service, name, value)
    monkeypatch.setattr(
        api.oos_oot_feishu,
        "sync_oos_oot_record_to_feishu",
        AsyncMock(return_value={"record_id": "feishu-1"}),
    )
    monkeypatch.setattr(
        api.oos_oot_feishu,
        "sync_oot_limit_product_to_feishu",
        AsyncMock(return_value={"record_id": "product-1"}),
    )
    monkeypatch.setattr(
        api.oos_oot_feishu,
        "sync_oot_limit_item_to_feishu",
        AsyncMock(return_value={"record_id": "item-1"}),
    )

    listed = await api.list_legacy_oos_oot_records(
        keyword="异常", page=1, page_size=20, db=db, current_user=user
    )
    assert listed.status_code == 200
    created = await api.create_legacy_oos_oot_record(
        {"batch_no": "B-1", "discovered_date": "2026-08-27", "title": "异常"},
        db,
        user,
    )
    assert created.status_code == 200
    await api.start_legacy_oos_oot_investigation(record_id, db, user)
    await api.close_legacy_oos_oot_record(
        record_id, {"investigation_result": "已查明"}, db, user
    )
    await api.sync_legacy_oos_oot_record_to_feishu(record_id, db, user)
    await api.get_legacy_oos_oot_record(record_id, db, user)
    await api.update_legacy_oos_oot_record(
        record_id,
        {"batch_no": "B-2", "discovered_date": "2026-08-28"},
        db,
        user,
    )
    await api.delete_legacy_oos_oot_record(record_id, db, user)

    await api.create_legacy_oot_limit_product(
        {"product_code": "P-1", "product_name": "产品", "document_no": "N-1"},
        db,
        user,
    )
    await api.list_legacy_oot_limit_products(keyword="产品", db=db, current_user=user)
    await api.get_legacy_oot_limit_product(product_id, db, user)
    await api.update_legacy_oot_limit_product(
        product_id, {"document_no": "N-2"}, db, user
    )
    await api.delete_legacy_oot_limit_product(product_id, db, user)
    await api.create_legacy_oot_limit_item(
        product_id,
        {"specification": "98%", "oot_limit": "97%", "item_name": "含量"},
        db,
        user,
    )
    await api.list_legacy_oot_limit_items(product_id, db, user)
    await api.update_legacy_oot_limit_item(
        item_id, {"specification": "99%", "oot_limit": "98%"}, db, user
    )
    await api.delete_legacy_oot_limit_item(item_id, db, user)
    await api.sync_legacy_oot_limit_product(product_id, db, user)
    await api.sync_legacy_oot_limit_item(item_id, db, user)
    assert db.commit.await_count >= 8
