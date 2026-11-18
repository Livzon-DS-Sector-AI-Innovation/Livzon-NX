from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import storage
from app.core.database import get_db
from app.core.deps import get_current_user
from app.main import app
from app.modules.equipment.api.images import router
from app.modules.equipment.service import work_order_image


async def test_work_order_image_upload_contract(monkeypatch, tmp_path) -> None:
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    prefix = "/api/v1/equipment/maintenance/work-orders"
    test_app.include_router(router, prefix=prefix)
    order_id = uuid4()
    test_app.dependency_overrides[get_db] = lambda: None
    test_app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=uuid4()
    )
    order = AsyncMock(return_value=SimpleNamespace(id=order_id))
    existing = AsyncMock(return_value=[object()] * 9)
    monkeypatch.setattr(work_order_image.repo, "get_work_order_by_id", order)
    monkeypatch.setattr(work_order_image.repo, "get_images_by_work_order", existing)
    create = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(),
            work_order_id=order_id,
            file_name="good.jpg",
            file_size=4,
            uploaded_at=datetime.now(UTC),
        )
    )
    monkeypatch.setattr(work_order_image.repo, "create_image", create)
    monkeypatch.setattr(storage, "is_enabled", lambda: False)
    settings = SimpleNamespace(UPLOAD_DIR=str(tmp_path), MAX_UPLOAD_SIZE_MB=1)
    monkeypatch.setattr(work_order_image, "get_settings", lambda: settings)
    image = ("files", ("good.jpg", b"test", "image/jpeg"))
    path = f"{prefix}/{order_id}/images"

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        limit = await client.post(path, files=[image])
        assert limit.status_code == 400
        assert limit.json()["code"] == 400
        assert limit.json()["detail"] == {
            "error_code": "EQUIPMENT_WORK_ORDER_IMAGE_LIMIT"
        }
        existing.return_value = []
        unsupported = await client.post(
            path, files=[image, ("files", ("bad.txt", b"data", "text/plain"))]
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["code"] == 415
        assert "detail" not in unsupported.json()
        settings.MAX_UPLOAD_SIZE_MB = 0
        oversized = await client.post(path, files=[image])
        assert oversized.status_code == 413
        assert oversized.json()["code"] == 413
        assert "detail" not in oversized.json()
        create.assert_not_awaited()
        assert not list(tmp_path.iterdir())

        settings.MAX_UPLOAD_SIZE_MB = 1
        uploaded = await client.post(path, files=[image])
        assert uploaded.status_code == 200
        assert uploaded.json()["data"][0]["file_name"] == "good.jpg"
        create.assert_awaited_once()

        order.return_value = None
        missing = await client.post(path, files=[image])
        assert missing.status_code == 404
        assert missing.json()["code"] == 404

    response = app.openapi()["paths"][f"{prefix}/{{work_order_id}}/images"]["post"]
    assert response["responses"]["400"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkOrderImageUploadError"
    }
