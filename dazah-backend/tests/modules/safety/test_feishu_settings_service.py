"""安全模块飞书设置服务与运行时配置测试。

覆盖：脱敏回显、掩码回传保持原值、密文落库、连接测试状态写回、
密钥轮换恢复路径、运行时配置加载（缺失/禁用/解密失败）。
"""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

from app.core.exceptions import AppException
from app.core.llm.encryption import encrypt_api_key
from app.modules.safety.feishu.runtime_config import (
    SafetyFeishuConfigError,
    build_runtime_config,
    load_safety_feishu_runtime_config,
    require_safety_feishu_runtime_config,
)
from app.modules.safety.models import SafetyFeishuAppSettings
from app.modules.safety.schemas.feishu_settings import (
    UpdateSafetyFeishuAppSettingsRequest,
)
from app.modules.safety.service import feishu_settings


class _BoundSessionFactory:
    """把 runtime_config 的独立会话指到当前测试会话（同一事务，随测试回滚）。"""

    def __init__(self, session) -> None:
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info):
        return False


def _bind_runtime_session(monkeypatch, db_session) -> None:
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        _BoundSessionFactory(db_session),
    )


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """启用真实 Fernet 加密，验证密文落库与解密路径。"""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", key)
    return key


@pytest.fixture(autouse=True)
async def _clean_settings_table(db_session):
    yield
    await db_session.execute(delete(SafetyFeishuAppSettings))
    await db_session.commit()


async def _seed_row(db_session, **overrides) -> SafetyFeishuAppSettings:
    values: dict = {
        "app_id": "cli_test_safety",
        "app_secret": encrypt_api_key("secret-plain-value"),
        "bitable_app_token": "bascnTestToken",
        "bitable_hazard_table_id": "tblHazard",
        "is_enabled": True,
    }
    values.update(overrides)
    row = SafetyFeishuAppSettings(**values)
    db_session.add(row)
    await db_session.commit()
    return row


async def _get_single_row(db_session) -> SafetyFeishuAppSettings:
    result = await db_session.execute(select(SafetyFeishuAppSettings))
    return result.scalar_one()


async def _fake_token_ok(*args, **kwargs):
    return "t-fake"


async def _fake_token_fail(*args, **kwargs):
    raise RuntimeError("app secret invalid")


# ── 设置服务 ──


async def test_get_settings_returns_empty_detail_when_missing(db_session):
    detail = await feishu_settings.get_safety_feishu_app_settings(db_session)
    assert detail.app_id == ""
    assert detail.app_secret_masked == ""
    assert detail.is_enabled is True


async def test_update_creates_row_with_encrypted_secret(db_session, encryption_key):
    detail = await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_new",
            app_secret="plain-secret-123",
            bitable_app_token="bascnNew",
            bitable_hazard_table_id="tblNew",
            is_enabled=True,
        ),
    )
    assert detail.app_id == "cli_new"
    assert detail.app_secret_masked
    assert "plain-secret-123" not in detail.app_secret_masked
    assert detail.bitable_app_token == "bascnNew"

    row = await _get_single_row(db_session)
    assert row.app_id == "cli_new"
    assert row.app_secret != "plain-secret-123"
    assert row.app_secret != ""


async def test_update_requires_secret_for_first_save(db_session):
    with pytest.raises(AppException) as exc_info:
        await feishu_settings.update_safety_feishu_app_settings(
            db_session,
            UpdateSafetyFeishuAppSettingsRequest(app_id="cli_new", app_secret=""),
        )
    assert "App Secret" in str(exc_info.value.message)


async def test_update_with_masked_secret_keeps_stored_secret(
    db_session, encryption_key
):
    await _seed_row(db_session)
    before = await _get_single_row(db_session)

    current = await feishu_settings.get_safety_feishu_app_settings(db_session)
    await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_test_safety",
            # UI 未修改 Secret 时回传掩码值，不应覆盖密文
            app_secret=current.app_secret_masked,
        ),
    )
    after = await _get_single_row(db_session)
    assert after.app_secret == before.app_secret


async def test_update_round_trips_knowledge_binding(db_session):
    await _seed_row(db_session)
    detail = await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_test_safety",
            app_secret="",
            knowledge_app_token="FSRubKnowledge",
            knowledge_table_id="tblKnowledge",
        ),
    )
    assert detail.knowledge_app_token == "FSRubKnowledge"
    assert detail.knowledge_table_id == "tblKnowledge"
    assert detail.knowledge_last_sync_status is None

    # 再次保存不带 knowledge 字段：显式传入空值才清空，未传保持原值
    detail = await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(app_id="cli_test_safety", app_secret=""),
    )
    assert detail.knowledge_app_token == "FSRubKnowledge"

    detail = await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_test_safety",
            app_secret="",
            knowledge_app_token="",
            knowledge_table_id=None,
        ),
    )
    assert detail.knowledge_app_token is None
    assert detail.knowledge_table_id is None


async def test_update_with_new_secret_replaces_stored_secret(db_session):
    await _seed_row(db_session)
    await feishu_settings.update_safety_feishu_app_settings(
        db_session,
        UpdateSafetyFeishuAppSettingsRequest(
            app_id="cli_test_safety",
            app_secret="rotated-secret-456",
        ),
    )
    row = await _get_single_row(db_session)
    assert row.app_secret == encrypt_api_key("rotated-secret-456")


async def test_test_settings_success_writes_status(db_session, monkeypatch):
    await _seed_row(db_session)
    monkeypatch.setattr(
        "app.platform.integrations.feishu.auth.FeishuAuth.get_tenant_access_token",
        _fake_token_ok,
    )
    result = await feishu_settings.test_safety_feishu_app_settings(db_session)
    assert result.success is True
    row = await _get_single_row(db_session)
    assert row.last_test_status == "success"
    assert row.last_tested_at is not None


async def test_test_settings_failure_writes_error(db_session, monkeypatch):
    await _seed_row(db_session)
    monkeypatch.setattr(
        "app.platform.integrations.feishu.auth.FeishuAuth.get_tenant_access_token",
        _fake_token_fail,
    )
    result = await feishu_settings.test_safety_feishu_app_settings(db_session)
    assert result.success is False
    assert "invalid" in result.message
    row = await _get_single_row(db_session)
    assert row.last_test_status == "failed"
    assert row.last_test_error


async def test_test_settings_failure_masks_feishu_identifiers(
    db_session, monkeypatch
):
    async def _fail(*args, **kwargs):
        raise RuntimeError(
            "app cli_aa11bb22cc33dd44 auth failed for table tblXx99887766"
        )

    await _seed_row(db_session)
    monkeypatch.setattr(
        "app.platform.integrations.feishu.auth.FeishuAuth.get_tenant_access_token",
        _fail,
    )
    result = await feishu_settings.test_safety_feishu_app_settings(db_session)
    assert result.success is False
    assert "cli_aa11bb22cc33dd44" not in result.message
    assert "tblXx99887766" not in result.message
    assert "cli_" in result.message  # 保留前缀便于定位
    row = await _get_single_row(db_session)
    assert row.last_test_error
    assert "cli_aa11bb22cc33dd44" not in row.last_test_error


async def test_test_settings_requires_saved_config(db_session):
    with pytest.raises(AppException):
        await feishu_settings.test_safety_feishu_app_settings(db_session)


async def test_test_settings_corrupt_cipher_returns_business_error(
    db_session, monkeypatch, encryption_key
):
    async def _must_not_call(**_kwargs):
        raise AssertionError("密文损坏时不应发起飞书连接测试")

    await _seed_row(db_session, app_secret="not-a-valid-cipher")
    monkeypatch.setattr(
        "app.platform.integrations.feishu.auth.FeishuAuth.get_tenant_access_token",
        _must_not_call,
    )
    with pytest.raises(AppException) as exc_info:
        await feishu_settings.test_safety_feishu_app_settings(db_session)
    assert "无法解密" in str(exc_info.value.message)


# ── 运行时配置 ──


async def test_runtime_config_missing_returns_none(db_session, monkeypatch):
    _bind_runtime_session(monkeypatch, db_session)
    assert await load_safety_feishu_runtime_config() is None
    with pytest.raises(SafetyFeishuConfigError):
        await require_safety_feishu_runtime_config()


async def test_runtime_config_disabled_returns_none(db_session, monkeypatch):
    await _seed_row(db_session, is_enabled=False)
    _bind_runtime_session(monkeypatch, db_session)
    assert await load_safety_feishu_runtime_config() is None
    loaded = await load_safety_feishu_runtime_config(include_disabled=True)
    assert loaded is not None
    assert loaded.app_id == "cli_test_safety"


async def test_runtime_config_returns_decrypted_values(db_session, monkeypatch):
    await _seed_row(db_session)
    _bind_runtime_session(monkeypatch, db_session)
    config = await require_safety_feishu_runtime_config()
    assert config.app_id == "cli_test_safety"
    assert config.app_secret == "secret-plain-value"
    assert config.bitable_app_token == "bascnTestToken"
    assert config.bitable_hazard_table_id == "tblHazard"


async def test_runtime_config_undecryptable_secret_raises(db_session, encryption_key):
    row = await _seed_row(db_session, app_secret="not-a-valid-cipher")
    with pytest.raises(SafetyFeishuConfigError):
        build_runtime_config(row)
