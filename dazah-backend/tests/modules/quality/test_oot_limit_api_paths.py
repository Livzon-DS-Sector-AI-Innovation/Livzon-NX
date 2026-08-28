from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.modules.quality.api import oot_limit as api
from app.modules.quality.models.oot_limit import OotLimitItem, OotLimitProduct
from app.modules.quality.schemas.oot_limit import (
    CreateOotLimitItemRequest,
    CreateOotLimitProductRequest,
    UpdateOotLimitItemRequest,
    UpdateOotLimitProductRequest,
)


class _Result:
    def __init__(
        self,
        row: object | None = None,
        rows: list[object] | None = None,
        total: int = 0,
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.total = total

    def scalar(self) -> int:
        return self.total

    def scalar_one_or_none(self) -> object | None:
        return self.row

    def scalar_one(self) -> object:
        assert self.row is not None
        return self.row

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[object]:
        return self.rows


def _product(product_id=None) -> OotLimitProduct:
    now = datetime.now(UTC)
    return OotLimitProduct(
        id=product_id or uuid4(),
        product_code="P-001",
        product_name="产品一",
        document_title="通知单",
        document_year=2026,
        version_label="V1",
        source_file_name="limits.xlsx",
        remark="备注",
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )


def _item(product_id, item_id=None) -> OotLimitItem:
    now = datetime.now(UTC)
    return OotLimitItem(
        id=item_id or uuid4(),
        product_id=product_id,
        display_order=1,
        item_group="理化",
        item_name="含量",
        specification="98-102%",
        oot_limit="97-103%",
        standard_value="98-102%",
        oot_limit_value="97-103%",
        remark="备注",
        created_at=now,
        updated_at=now,
        is_deleted=False,
    )


def _body(response: object) -> dict[str, object]:
    return json.loads(response.body)  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_oot_limit_product_crud_and_search_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "_require_user", Mock())
    user = SimpleNamespace(id=uuid4())
    product_id = uuid4()
    product = _product(product_id)
    db = SimpleNamespace()

    db.execute = AsyncMock(side_effect=[_Result(total=1), _Result(rows=[product])])
    response = await api.list_oot_limit_products(
        keyword="产品%", page=2, page_size=5, db=db, current_user=user
    )
    assert response.status_code == 200
    assert _body(response)["meta"]["total"] == 1  # type: ignore[index]

    create_data = CreateOotLimitProductRequest(
        product_code="P-002",
        product_name="产品二",
        document_title="通知单二",
    )
    created = _product(uuid4())
    db.add = Mock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=_Result(created))
    response = await api.create_oot_limit_product(create_data, db=db, current_user=user)
    assert response.status_code == 200
    assert db.add.called

    db.execute = AsyncMock(side_effect=[_Result(product), _Result(product)])
    response = await api.update_oot_limit_product(
        product_id,
        UpdateOotLimitProductRequest(product_name="更新产品"),
        db=db,
        current_user=user,
    )
    assert response.status_code == 200
    assert product.product_name == "更新产品"

    db.execute = AsyncMock(return_value=_Result(None))
    response = await api.update_oot_limit_product(
        uuid4(),
        UpdateOotLimitProductRequest(product_name="不存在"),
        db=db,
        current_user=user,
    )
    assert response.status_code == 404

    child = _item(product_id)
    db.execute = AsyncMock(side_effect=[_Result(product), _Result(rows=[child])])
    response = await api.delete_oot_limit_product(product_id, db=db, current_user=user)
    assert response.status_code == 200
    assert product.is_deleted and child.is_deleted

    db.execute = AsyncMock(return_value=_Result(None))
    response = await api.delete_oot_limit_product(uuid4(), db=db, current_user=user)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_oot_limit_item_crud_search_and_parent_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api, "_require_user", Mock())
    user = SimpleNamespace(id=uuid4())
    product_id = uuid4()
    item_id = uuid4()
    product = _product(product_id)
    item = _item(product_id, item_id)
    db = SimpleNamespace()

    db.execute = AsyncMock(side_effect=[_Result(total=1), _Result(rows=[item])])
    response = await api.list_oot_limit_items(
        product_id=product_id,
        keyword="含量_",
        page=1,
        page_size=10,
        db=db,
        current_user=user,
    )
    assert response.status_code == 200

    created = _item(product_id, uuid4())
    db.add = Mock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(side_effect=[_Result(product), _Result(created)])
    response = await api.create_oot_limit_item(
        CreateOotLimitItemRequest(
            product_id=product_id,
            display_order=2,
            item_name="杂质",
            standard_value="不超过1%",
            oot_limit_value="不超过2%",
        ),
        db=db,
        current_user=user,
    )
    assert response.status_code == 200

    db.execute = AsyncMock(return_value=_Result(None))
    response = await api.create_oot_limit_item(
        CreateOotLimitItemRequest(
            product_id=product_id,
            display_order=3,
            item_name="无产品",
            standard_value="1",
            oot_limit_value="2",
        ),
        db=db,
        current_user=user,
    )
    assert response.status_code == 404

    replacement_product = _product(uuid4())
    updated = _item(replacement_product.id, item_id)
    db.execute = AsyncMock(
        side_effect=[_Result(item), _Result(replacement_product), _Result(updated)]
    )
    response = await api.update_oot_limit_item(
        item_id,
        UpdateOotLimitItemRequest(product_id=replacement_product.id, item_name="更新"),
        db=db,
        current_user=user,
    )
    assert response.status_code == 200
    assert item.item_name == "更新"

    db.execute = AsyncMock(side_effect=[_Result(item), _Result(None)])
    response = await api.update_oot_limit_item(
        item_id,
        UpdateOotLimitItemRequest(product_id=uuid4()),
        db=db,
        current_user=user,
    )
    assert response.status_code == 404

    db.execute = AsyncMock(return_value=_Result(item))
    response = await api.delete_oot_limit_item(item_id, db=db, current_user=user)
    assert response.status_code == 200
    assert item.is_deleted

    db.execute = AsyncMock(return_value=_Result(None))
    response = await api.delete_oot_limit_item(uuid4(), db=db, current_user=user)
    assert response.status_code == 404
