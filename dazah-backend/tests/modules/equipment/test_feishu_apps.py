"""设备模块飞书自建应用服务与 API 测试。"""

from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.schemas.inspection import (
    EquipmentInspectionFeishuConfigUpdateRequest,
    FeishuAppCreateRequest,
    FeishuAppUpdateRequest,
)
from app.modules.equipment.service import feishu_app as app_service


@pytest.fixture(autouse=True)
def _test_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential tests use an ephemeral key instead of local configuration."""
    monkeypatch.setattr(
        get_settings(), "LLM_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


@pytest.fixture(autouse=True)
async def _clean_apps_table(
    db_session: AsyncSession,
    _equipment_session: AsyncSession,
) -> Any:
    """前后清空配置与应用表：服务写操作会 commit，不能依赖回滚隔离。

    先删配置行再删应用行（外键）；覆盖服务级与 API 级共享会话两条路径。
    """
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.execute(delete(EquipmentFeishuApp))
        await session.commit()
    yield
    for session in (db_session, _equipment_session):
        await session.execute(delete(EquipmentInspectionFeishuConfig))
        await session.execute(delete(EquipmentFeishuApp))
        await session.commit()


# ---------- 服务 ----------


async def test_create_and_list_apps(db_session: AsyncSession) -> None:
    created = await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="巡检应用", app_id="cli_a", app_secret="secret_a"),
    )
    assert created.app_secret_configured is True
    assert created.app_secret_masked
    assert "secret_a" not in created.model_dump_json()
    assert created.in_use_workshops == []
    stored = await app_service.get_app_by_id(db_session, created.id)
    assert stored is not None
    assert stored.app_secret != "secret_a"
    assert decrypt_api_key(stored.app_secret) == "secret_a"

    apps = await app_service.list_apps(db_session)
    assert [a.app_id for a in apps] == ["cli_a"]
    assert apps[0].name == "巡检应用"


async def test_create_app_duplicate_app_id_rejected(
    db_session: AsyncSession,
) -> None:
    await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="一号应用", app_id="cli_a", app_secret="s"),
    )
    with pytest.raises(AppException, match="已登记"):
        await app_service.create_app(
            db_session,
            FeishuAppCreateRequest(name="二号应用", app_id="cli_a", app_secret="s"),
        )


async def test_create_app_blank_fields_rejected(db_session: AsyncSession) -> None:
    # 纯空格绕过 Schema 的 min_length，由服务层校验拦截
    with pytest.raises(AppException, match="完整填写"):
        await app_service.create_app(
            db_session,
            FeishuAppCreateRequest(name="  ", app_id="cli_a", app_secret="s"),
        )
    with pytest.raises(AppException, match="完整填写"):
        await app_service.create_app(
            db_session,
            FeishuAppCreateRequest(name="n", app_id="cli_a", app_secret="  "),
        )


async def test_update_app_rotates_secret(db_session: AsyncSession) -> None:
    created = await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="改名前", app_id="cli_r", app_secret="old_s"),
    )
    updated = await app_service.update_app(
        db_session,
        created.id,
        FeishuAppUpdateRequest(name="改名后", app_secret="new_s"),
    )
    assert updated.name == "改名后"
    row = await app_service.get_app_by_app_id(db_session, "cli_r")
    assert row is not None
    assert app_service.decrypt_app_secret(row.app_secret) == "new_s"


async def test_update_app_blank_secret_keeps_stored(
    db_session: AsyncSession,
) -> None:
    created = await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="应用", app_id="cli_k", app_secret="keep_s"),
    )
    await app_service.update_app(
        db_session, created.id, FeishuAppUpdateRequest(name=None, app_secret=None)
    )
    row = await app_service.get_app_by_app_id(db_session, "cli_k")
    assert row is not None
    assert app_service.decrypt_app_secret(row.app_secret) == "keep_s"


async def test_update_app_masked_resend_not_treated_as_new_secret(
    db_session: AsyncSession,
) -> None:
    from app.core.llm.encryption import mask_api_key

    created = await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="应用", app_id="cli_m", app_secret="mask_secret"),
    )
    # 前端把掩码原样带回时不得把掩码当新密钥存储
    await app_service.update_app(
        db_session,
        created.id,
        FeishuAppUpdateRequest(name=None, app_secret=mask_api_key("mask_secret")),
    )
    row = await app_service.get_app_by_app_id(db_session, "cli_m")
    assert row is not None
    assert app_service.decrypt_app_secret(row.app_secret) == "mask_secret"


async def test_update_app_missing_raises_404(db_session: AsyncSession) -> None:
    import uuid

    with pytest.raises(AppException) as exc_info:
        await app_service.update_app(
            db_session, uuid.uuid4(), FeishuAppUpdateRequest(name="x")
        )
    assert exc_info.value.status_code == 404


async def test_delete_app_blocked_when_in_use(db_session: AsyncSession) -> None:
    from app.modules.equipment.service import inspection_feishu_config as config_service

    created = await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="占用中", app_id="cli_used", app_secret="s"),
    )
    await config_service.update_config(
        db_session,
        "101-2",
        EquipmentInspectionFeishuConfigUpdateRequest(
            feishu_app_id=created.id, app_token="bascn_used"
        ),
    )
    apps = await app_service.list_apps(db_session)
    assert apps[0].in_use_workshops == ["101-2"]

    with pytest.raises(AppException, match="101-2"):
        await app_service.delete_app(db_session, created.id)


async def test_delete_app_unused_succeeds(db_session: AsyncSession) -> None:
    created = await app_service.create_app(
        db_session,
        FeishuAppCreateRequest(name="闲置", app_id="cli_free", app_secret="s"),
    )
    await app_service.delete_app(db_session, created.id)
    assert await app_service.get_app_by_app_id(db_session, "cli_free") is None
    assert await app_service.list_apps(db_session) == []


def test_decrypt_app_secret_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.llm.exceptions import LLMConfigError

    assert app_service.decrypt_app_secret(None) == ""
    assert app_service.decrypt_app_secret("") == ""

    def broken(_value: str) -> str:
        raise LLMConfigError("no key")

    monkeypatch.setattr(app_service, "decrypt_api_key", broken)
    assert app_service.decrypt_app_secret("bad-cipher") == ""


# ---------- API ----------


async def test_apps_api_requires_login(db_session: AsyncSession) -> None:
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.main import app

    async def _override_get_db() -> Any:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    _missing = "00000000-0000-0000-0000-000000000000"
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            for method, path in (
                ("GET", "/api/v1/equipment/inspection/feishu/apps"),
                ("POST", "/api/v1/equipment/inspection/feishu/apps"),
                (
                    "PUT",
                    f"/api/v1/equipment/inspection/feishu/apps/{_missing}",
                ),
                (
                    "DELETE",
                    f"/api/v1/equipment/inspection/feishu/apps/{_missing}",
                ),
            ):
                resp = await ac.request(method, path, json={})
                assert resp.status_code == 401, (method, path, resp.status_code)
    finally:
        app.dependency_overrides.clear()


async def test_apps_api_crud_flow(client: Any) -> None:
    resp = await client.get("/api/v1/equipment/inspection/feishu/apps")
    assert resp.status_code == 200
    assert resp.json()["data"] == []

    resp = await client.post(
        "/api/v1/equipment/inspection/feishu/apps",
        json={"name": "接口应用", "app_id": "cli_api", "app_secret": "api_secret"},
    )
    assert resp.status_code == 200
    created = resp.json()["data"]
    assert created["app_id"] == "cli_api"
    assert "app_secret" not in created
    assert created["app_secret_masked"]
    app_uuid = created["id"]

    # 重复 App ID 返回业务 4xx
    resp = await client.post(
        "/api/v1/equipment/inspection/feishu/apps",
        json={"name": "重复", "app_id": "cli_api", "app_secret": "s"},
    )
    assert resp.status_code == 400
    assert "已登记" in resp.json()["message"]

    resp = await client.put(
        f"/api/v1/equipment/inspection/feishu/apps/{app_uuid}",
        json={"name": "接口应用改名"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "接口应用改名"

    resp = await client.get("/api/v1/equipment/inspection/feishu/apps")
    assert [a["name"] for a in resp.json()["data"]] == ["接口应用改名"]

    resp = await client.delete(
        f"/api/v1/equipment/inspection/feishu/apps/{app_uuid}"
    )
    assert resp.status_code == 200
    resp = await client.get("/api/v1/equipment/inspection/feishu/apps")
    assert resp.json()["data"] == []

    # 删除不存在的应用返回 404
    resp = await client.delete(
        f"/api/v1/equipment/inspection/feishu/apps/{app_uuid}"
    )
    assert resp.status_code == 404
