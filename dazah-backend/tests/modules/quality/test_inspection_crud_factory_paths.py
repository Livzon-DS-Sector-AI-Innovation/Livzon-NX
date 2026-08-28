from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.modules.quality.api import inspection_submodules
from app.modules.quality.models.lab_item import LabItem
from app.modules.quality.schemas.lab_item import (
    CreateLabItemRequest,
    UpdateLabItemRequest,
)


def _item() -> LabItem:
    item = LabItem(
        name="标签纸",
        specification="A4",
        category="耗材",
        quantity=10,
        unit="包",
        location="A区",
        supplier="供应商",
        batch_no="B-1",
        status="normal",
    )
    item.id = uuid4()
    item.created_at = datetime(2026, 1, 1)
    item.updated_at = datetime(2026, 1, 1)
    item.is_deleted = False
    return item


def _endpoint(path: str, method: str):
    return next(
        route.endpoint
        for route in inspection_submodules.router.routes
        if route.path == path and method in route.methods
    )


def _db_for(*results: object) -> SimpleNamespace:
    return SimpleNamespace(
        execute=AsyncMock(side_effect=list(results)),
        add=MagicMock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


def _items_result(items: list[LabItem]) -> SimpleNamespace:
    return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: items))


def _one_result(item: LabItem | None) -> SimpleNamespace:
    return SimpleNamespace(scalar_one_or_none=lambda: item, scalar_one=lambda: item)


@pytest.mark.asyncio
async def test_generated_lab_item_crud_routes_cover_success_and_not_found() -> None:
    item = _item()
    user = SimpleNamespace(id=uuid4(), name="测试用户")
    list_items = _endpoint("/lab-items", "GET")
    db = _db_for(
        SimpleNamespace(scalar=lambda: 1),
        _items_result([item]),
    )
    listed = await list_items(
        current_user=user,
        keyword="标签",
        page=1,
        page_size=20,
        db=db,
    )
    assert listed.status_code == 200

    get_item = _endpoint("/lab-items/{record_id}", "GET")
    got = await get_item(
        record_id=item.id, current_user=user, db=_db_for(_one_result(item))
    )
    assert got.status_code == 200

    create_item = _endpoint("/lab-items", "POST")
    create_db = _db_for(_one_result(item))

    def assign_identity(record: LabItem) -> None:
        record.id = uuid4()
        record.created_at = datetime(2026, 1, 1)
        record.updated_at = datetime(2026, 1, 1)

    create_db.add.side_effect = assign_identity
    created = await create_item(
        data=CreateLabItemRequest(name="新物品"), current_user=user, db=create_db
    )
    assert created.status_code == 200
    assert create_db.commit.await_count == 1

    update_item = _endpoint("/lab-items/{record_id}", "PUT")
    update_db = _db_for(_one_result(item), _one_result(item))
    updated = await update_item(
        record_id=item.id,
        data=UpdateLabItemRequest(name="更新物品"),
        current_user=user,
        db=update_db,
    )
    assert updated.status_code == 200
    assert item.name == "更新物品"

    delete_item = _endpoint("/lab-items/{record_id}", "DELETE")
    deleted = await delete_item(
        record_id=item.id,
        current_user=user,
        db=_db_for(_one_result(item)),
    )
    assert deleted.status_code == 200
    assert item.is_deleted is True

    with pytest.raises(Exception):
        await get_item(
            record_id=uuid4(), current_user=user, db=_db_for(_one_result(None))
        )
