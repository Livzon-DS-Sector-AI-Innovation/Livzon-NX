from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.platform.identity import service
from app.platform.identity.models import FeishuConfig
from app.platform.identity.schemas import ExternalIdentityBindingOut, FeishuConfigUpsert


class FakeDb:
    def __init__(self) -> None:
        self.flush_count = 0
        self.refresh_count = 0

    async def flush(self) -> None:
        self.flush_count += 1

    async def refresh(self, instance) -> None:
        self.refresh_count += 1


class FakeFeishuConfigRepo:
    def __init__(self, config: FeishuConfig | None = None) -> None:
        self.config = config
        self.saved: FeishuConfig | None = None

    async def get_latest(self, db) -> FeishuConfig | None:
        return self.config

    async def get_active(self, db) -> FeishuConfig | None:
        return self.config if self.config and self.config.is_active else None

    async def save(self, db, config: FeishuConfig) -> FeishuConfig:
        self.saved = config
        self.config = config
        await db.flush()
        return config


class FakeHttpResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300


class FakeHttpClient:
    status_code = 200

    def __init__(self, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def put(self, *args, **kwargs) -> FakeHttpResponse:
        return FakeHttpResponse(self.status_code)


def test_external_identity_binding_out_normalizes_migrated_source() -> None:
    now = datetime.now(UTC)
    binding = ExternalIdentityBindingOut.model_validate(
        {
            "id": uuid4(),
            "tenant_id": "default",
            "platform": "feishu",
            "app_fingerprint": "cli_test",
            "external_open_id": "ou_test",
            "local_user_id": uuid4(),
            "source": "identity.users",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )

    assert binding.source == "directory_sync"


@pytest.mark.anyio
async def test_save_livzon_feishu_config_preserves_existing_secret(monkeypatch) -> None:
    async def ignore_hermes_credential_push(**kwargs) -> None:
        return None

    monkeypatch.setattr(
        service,
        "_push_livzon_credentials_to_hermes",
        ignore_hermes_credential_push,
    )
    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="old-app",
        encrypted_app_secret="legacy-secret",
        is_active=True,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(config),
    )

    response = await service.save_livzon_feishu_config(
        FakeDb(),
        FeishuConfigUpsert(
            config_name="Livzon 助手飞书设置",
            app_id="new-app",
            sync_root_department_id="0",
            sync_member_department_id="od-test",
            is_active=True,
        ),
    )

    assert response.app_id == "new-app"
    assert response.app_secret_configured is True
    assert config.encrypted_app_secret == "legacy-secret"
    assert config.sync_member_department_id == "od-test"


@pytest.mark.anyio
async def test_save_livzon_feishu_config_reports_secret_encryption_error(
    monkeypatch,
) -> None:
    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="old-app",
        encrypted_app_secret="legacy-secret",
        is_active=True,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(config),
    )

    def fail_encrypt(_plain_text: str) -> str:
        raise RuntimeError("ENCRYPTION_KEY must be configured in production")

    monkeypatch.setattr(service, "encrypt_secret", fail_encrypt)

    with pytest.raises(HTTPException) as exc_info:
        await service.save_livzon_feishu_config(
            FakeDb(),
            FeishuConfigUpsert(
                config_name="Livzon 助手飞书设置",
                app_id="new-app",
                app_secret="new-secret",
                sync_root_department_id="0",
                sync_member_department_id="0",
                is_active=True,
            ),
        )

    assert exc_info.value.status_code == 500
    assert "ENCRYPTION_KEY" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_push_livzon_credentials_reports_hermes_version_conflict(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes",
            HERMES_INTERNAL_TOKEN="test-token",
        ),
    )
    FakeHttpClient.status_code = 409
    monkeypatch.setattr(service.httpx, "AsyncClient", FakeHttpClient)

    with pytest.raises(HTTPException) as exc_info:
        await service._push_livzon_credentials_to_hermes(
            app_id="cli_test",
            app_secret="secret",
            tenant_id="default",
            gateway_enabled=True,
            version=3,
        )

    assert exc_info.value.status_code == 409
    assert "过期" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_restart_livzon_feishu_gateway_waits_for_connected_result(
    monkeypatch,
) -> None:
    class Response:
        status_code = 200
        is_success = True

        def json(self):
            return {
                "status": "connected",
                "message": "Hermes 飞书 Gateway 已重新建立连接",
                "previous_reconnects": 2,
                "gateway_reconnects": 3,
                "credential_version": 4,
                "config_version": 3,
            }

    class Client:
        def __init__(self, *, timeout):
            assert timeout == 70

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers):
            assert url == "http://hermes/internal/feishu/gateway/restart"
            assert headers["Authorization"] == "Bearer test-token"
            return Response()

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes/",
            HERMES_INTERNAL_TOKEN="test-token",
        ),
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", Client)

    result = await service.restart_livzon_feishu_gateway()

    assert result.status == "connected"
    assert result.gateway_reconnects == 3


@pytest.mark.anyio
async def test_restart_livzon_feishu_gateway_preserves_runtime_conflict(
    monkeypatch,
) -> None:
    class Response:
        status_code = 409
        is_success = False

        def json(self):
            return {"detail": "飞书 Gateway 当前未启用"}

    class Client:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers):
            return Response()

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes",
            HERMES_INTERNAL_TOKEN="test-token",
        ),
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", Client)

    with pytest.raises(HTTPException) as exc_info:
        await service.restart_livzon_feishu_gateway()

    assert exc_info.value.status_code == 409
    assert "未启用" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_restart_livzon_feishu_gateway_explains_old_hermes_version(
    monkeypatch,
) -> None:
    class Response:
        status_code = 404
        is_success = False

    class Client:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers):
            return Response()

    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            HERMES_INTERNAL_URL="http://hermes",
            HERMES_INTERNAL_TOKEN="test-token",
        ),
    )
    monkeypatch.setattr(service.httpx, "AsyncClient", Client)

    with pytest.raises(HTTPException) as exc_info:
        await service.restart_livzon_feishu_gateway()

    assert exc_info.value.status_code == 503
    assert "重新部署 Hermes" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_diagnose_livzon_feishu_config_reports_missing_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(None),
    )
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            FEISHU_APP_ID="",
            FEISHU_APP_SECRET="",
            FEISHU_SYNC_ROOT_DEPT_ID="",
            FEISHU_SYNC_MEMBER_DEPT_ID="",
        ),
    )

    result = await service.diagnose_livzon_feishu_config(FakeDb())

    assert result.status == "error"
    assert result.steps[0].name == "应用凭证"


@pytest.mark.anyio
async def test_diagnose_livzon_feishu_config_reports_secret_decryption_error(
    monkeypatch,
) -> None:
    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="fernet:v1:encrypted",
        sync_root_department_id="0",
        sync_member_department_id="0",
        is_active=True,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(config),
    )

    def fail_decrypt(_encrypted_text: str) -> str:
        raise RuntimeError("ENCRYPTION_KEY is required to decrypt secret")

    monkeypatch.setattr(service, "decrypt_secret", fail_decrypt)

    with pytest.raises(HTTPException) as exc_info:
        await service.diagnose_livzon_feishu_config(FakeDb())

    assert exc_info.value.status_code == 500
    assert "ENCRYPTION_KEY" in str(exc_info.value.detail)


@pytest.mark.anyio
async def test_diagnose_livzon_feishu_config_warns_for_missing_user_fields(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.contact as contact
    import app.platform.integrations.feishu.utils as utils

    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="legacy-secret",
        sync_root_department_id="0",
        sync_member_department_id="od_member",
        is_active=True,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(config),
    )

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_departments(*args, **kwargs) -> list[dict]:
        return [{"department_id": "od_member", "name": "生产部"}]

    async def fake_scope(*args, **kwargs) -> dict:
        return {
            "department_ids": ["od_member"],
            "user_ids": [],
            "group_ids": [],
        }

    async def fake_users(*args, **kwargs) -> list[dict]:
        return [{"user_id": "u1", "name": "张三"}]

    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(contact, "get_contact_scope", fake_scope)
    monkeypatch.setattr(contact, "get_all_departments", fake_departments)
    monkeypatch.setattr(contact, "find_users_by_department", fake_users)

    result = await service.diagnose_livzon_feishu_config(FakeDb())

    assert result.status == "warning"
    assert result.department_count == 1
    assert result.sample_user_count == 1
    assert any(step.name == "通讯录授权范围" for step in result.steps)
    assert any(step.name == "用户手机号" for step in result.steps)


@pytest.mark.anyio
async def test_diagnose_uses_authorized_department_instead_of_inaccessible_root(
    monkeypatch,
) -> None:
    import app.platform.integrations.feishu.contact as contact
    import app.platform.integrations.feishu.utils as utils

    config = FeishuConfig(
        config_name="Livzon 助手飞书设置",
        app_id="cli_test",
        encrypted_app_secret="legacy-secret",
        sync_root_department_id="0",
        sync_member_department_id="0",
        is_active=True,
    )
    monkeypatch.setattr(
        service,
        "_feishu_config_repo",
        FakeFeishuConfigRepo(config),
    )

    async def fake_token(*args, **kwargs) -> str:
        return "tenant-token"

    async def fake_scope(*args, **kwargs) -> dict:
        return {
            "department_ids": ["od_authorized"],
            "user_ids": [],
            "group_ids": [],
        }

    async def fake_departments(*, root_department_id, **kwargs) -> list[dict]:
        assert root_department_id == "od_authorized"
        return []

    async def fake_users(department_id, **kwargs) -> list[dict]:
        assert department_id == "od_authorized"
        return [{
            "user_id": "u1",
            "name": "张三",
            "department_ids": ["od_authorized"],
            "mobile": "masked",
            "email": "masked@example.invalid",
        }]

    monkeypatch.setattr(utils, "get_tenant_access_token", fake_token)
    monkeypatch.setattr(contact, "get_contact_scope", fake_scope)
    monkeypatch.setattr(contact, "get_all_departments", fake_departments)
    monkeypatch.setattr(contact, "find_users_by_department", fake_users)

    result = await service.diagnose_livzon_feishu_config(FakeDb())

    assert result.status == "warning"
    assert next(step for step in result.steps if step.name == "部门列表").status == "ok"
    assert next(step for step in result.steps if step.name == "部门用户").status == "ok"
    target_step = next(step for step in result.steps if step.name == "诊断目标部门")
    assert target_step.code == 40004
    assert "不在当前通讯录权限范围" in target_step.message


def test_contact_api_suggestion_classifies_department_authority_error() -> None:
    error = RuntimeError("code=40004, msg=no dept authority error")

    suggestion = service._contact_api_suggestion(error, resource="部门列表")

    assert "Scope 已开通" in suggestion
    assert "通讯录权限范围" in suggestion
    assert service._feishu_error_code(error) == 40004
