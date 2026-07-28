from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.platform.identity import service
from app.platform.identity.models import FeishuConfig
from app.platform.identity.schemas import FeishuConfigUpsert


class FakeDb:
    def __init__(self) -> None:
        self.flush_count = 0

    async def flush(self) -> None:
        self.flush_count += 1


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


@pytest.mark.anyio
async def test_save_livzon_feishu_config_preserves_existing_secret(monkeypatch) -> None:
    from app.platform.identity import hermes_api

    async def ignore_hermes_credential_push(**kwargs) -> None:
        return None

    async def ignore_hermes_access_snapshot(db) -> None:
        return None

    monkeypatch.setattr(
        service,
        "_push_livzon_credentials_to_hermes",
        ignore_hermes_credential_push,
    )
    monkeypatch.setattr(
        hermes_api,
        "push_access_snapshot_to_hermes",
        ignore_hermes_access_snapshot,
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
        )
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
