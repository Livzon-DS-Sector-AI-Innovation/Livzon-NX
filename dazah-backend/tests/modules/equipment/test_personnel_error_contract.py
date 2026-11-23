from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.main import app
from app.modules.equipment.api.personnel import router
from app.modules.equipment.service import personnel


async def test_personnel_role_conflict_and_batch_results(monkeypatch) -> None:
    prefix = "/api/v1/equipment/personnel"
    test_app = FastAPI(exception_handlers=app.exception_handlers)
    test_app.include_router(router, prefix=prefix)
    missing_id, existing_id = uuid4(), uuid4()
    user = SimpleNamespace(id=existing_id)
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: None),
                SimpleNamespace(scalar_one_or_none=lambda: user),
            ]
        ),
    )
    test_app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr(
        personnel.repo, "get_role_by_code", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(personnel.repo, "get_role_by_id", AsyncMock(return_value=None))
    monkeypatch.setattr(
        personnel.repo,
        "get_personnel_by_user_and_workshop",
        AsyncMock(return_value=object()),
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        duplicate = await client.post(
            f"{prefix}/roles", json={"name": "示例角色", "code": "fixture"}
        )
        assert duplicate.status_code == duplicate.json()["code"] == 409
        assert duplicate.json()["detail"] == {
            "error_code": "EQUIPMENT_ROLE_CODE_EXISTS"
        }

        missing = await client.delete(f"{prefix}/roles/{uuid4()}")
        assert missing.status_code == missing.json()["code"] == 404
        assert "detail" not in missing.json()

        batch = await client.post(
            prefix, json={"user_ids": [str(missing_id), str(existing_id)]}
        )
        assert batch.status_code == 200
        assert batch.json()["data"] == {
            "added": [],
            "skipped": [str(existing_id)],
            "errors": [
                {
                    "user_id": str(missing_id),
                    "reason": "所选人员不存在，请刷新后重新选择",
                }
            ],
        }

    response = app.openapi()["paths"][f"{prefix}/roles"]["post"]["responses"]["409"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/EquipmentRoleConflictResponse",
    }
