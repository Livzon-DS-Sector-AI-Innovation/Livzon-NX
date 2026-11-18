"""Undeclared persistence fields cannot be written through product updates."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import NotFoundException
from app.main import app as platform_app
from app.modules.product.api import get_product_service, router
from app.modules.product.schemas import ProductUpdate
from app.modules.product.service import ProductService


@pytest.mark.parametrize(
    "field", ["id", "is_deleted", "created_by", "feishu_record_id"]
)
async def test_api_rejects_system_fields_before_service_call(field):
    service = SimpleNamespace(update_product=AsyncMock())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_product_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(f"/products/{uuid4()}", json={field: "injected"})
    assert response.status_code == 422
    service.update_product.assert_not_awaited()


async def test_service_only_updates_declared_fields():
    product = SimpleNamespace(name="before", is_deleted=False, created_by=None)
    service = ProductService.__new__(ProductService)
    service.repo = SimpleNamespace(update=AsyncMock(return_value=product))
    service.get_product = AsyncMock(return_value=product)
    service._sync_to_feishu = AsyncMock()
    data = ProductUpdate(name="after")
    # A trusted in-process caller must not be able to smuggle an ORM attribute.
    object.__setattr__(data, "__pydantic_extra__", {"is_deleted": True})
    await service.update_product(uuid4(), data)
    assert product.name == "after"
    assert product.is_deleted is False
    service.repo.update.assert_awaited_once_with(product)


async def test_api_accepts_declared_business_update():
    product_id = uuid4()
    product = SimpleNamespace(id=product_id, name="after")
    service = SimpleNamespace(update_product=AsyncMock(return_value=product))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_product_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(f"/products/{product_id}", json={"name": "after"})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "after"
    supplied = service.update_product.await_args.args[1]
    assert supplied.model_dump(exclude_unset=True) == {"name": "after"}


async def test_product_write_contract_uses_http_status() -> None:
    product_id = uuid4()
    product = SimpleNamespace(id=product_id, name="产品")
    missing = NotFoundException("产品", str(product_id))
    service = SimpleNamespace(
        create_product=AsyncMock(return_value=product),
        update_product=AsyncMock(side_effect=missing),
        delete_product=AsyncMock(side_effect=[None, missing]),
    )
    test_app = FastAPI(exception_handlers=platform_app.exception_handlers)
    test_app.include_router(router)
    test_app.dependency_overrides[get_product_service] = lambda: service
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        created = await client.post("/products", json={"name": "产品"})
        assert created.status_code == 201
        assert created.json()["data"]["id"] == str(product_id)
        path = f"/products/{product_id}"
        updated = await client.put(path, json={"name": "更新"})
        deleted = await client.delete(path)
        assert deleted.status_code == 200
        assert deleted.json()["data"] is None
        missing_delete = await client.delete(path)
        for result in (updated, missing_delete):
            assert result.status_code == 404
            assert result.json()["code"] == 404
            assert "detail" not in result.json()
