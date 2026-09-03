"""质量飞书应用设置：存量密文损坏（密钥轮换）后的加载/保存恢复路径测试。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key, mask_api_key
from app.modules.quality.models import QualityFeishuAppSettings
from app.modules.quality.schemas.feishu_settings import (
    UpdateQualityFeishuAppSettingsRequest,
)
from app.modules.quality.service import quality_feishu_settings as settings_service


def _build_detail(model):
    return settings_service._build_app_settings_detail(model)


async def _update_settings(db_session, request):
    return await settings_service.update_quality_feishu_app_settings(
        db_session, request
    )


async def _test_connection(db_session):
    return await settings_service.test_quality_feishu_app_settings(db_session)

APP_ID = "cli_aa1fa68e34b89cd4"


@pytest.fixture
def fernet_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, str]]:
    """当前环境密钥 + 旧密钥：模拟密钥轮换后存量密文解不开的场景。"""
    current = Fernet.generate_key().decode()
    stale = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", current)
    yield current, stale
    monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)


def _stale_encrypted(stale_key: str, plain: str) -> str:
    return Fernet(stale_key.encode()).encrypt(plain.encode()).decode()


def _build_request(secret: str) -> UpdateQualityFeishuAppSettingsRequest:
    return UpdateQualityFeishuAppSettingsRequest(
        app_id=APP_ID,
        app_secret=secret,
        is_enabled=True,
        deviation_report_form_url=None,
        deviation_investigation_push_form_url=None,
        oos_oot_report_form_url=None,
        oos_oot_investigation_push_form_url=None,
    )


@pytest.fixture(autouse=True)
async def _clean_app_settings(db_session: AsyncSession) -> Iterator[None]:
    await db_session.execute(delete(QualityFeishuAppSettings))
    await db_session.commit()
    yield
    await db_session.execute(delete(QualityFeishuAppSettings))
    await db_session.commit()


async def _seed_stale_secret(
    db_session: AsyncSession, stale_key: str
) -> QualityFeishuAppSettings:
    model = QualityFeishuAppSettings(
        app_id=APP_ID,
        app_secret=_stale_encrypted(stale_key, "old-secret"),
        is_enabled=True,
    )
    db_session.add(model)
    await db_session.commit()
    result = await db_session.get(QualityFeishuAppSettings, model.id)
    assert result is not None
    return result


@pytest.mark.anyio
async def test_build_detail_tolerates_stale_encrypted_secret(
    db_session: AsyncSession,
    fernet_keys: Any,
) -> None:
    _, stale = fernet_keys
    model = await _seed_stale_secret(db_session, stale)
    detail = _build_detail(model)
    assert detail.app_id == APP_ID
    assert detail.app_secret_masked == mask_api_key("")


@pytest.mark.anyio
async def test_update_overwrites_stale_encrypted_secret(
    db_session: AsyncSession,
    fernet_keys: Any,
) -> None:
    current, stale = fernet_keys
    model = await _seed_stale_secret(db_session, stale)
    detail = await _update_settings(db_session, _build_request("new-secret-value"))
    assert detail.app_secret_masked == mask_api_key("new-secret-value")

    refreshed = await db_session.get(QualityFeishuAppSettings, model.id)
    assert refreshed is not None
    assert decrypt_api_key(refreshed.app_secret) == "new-secret-value"
    assert refreshed.app_secret.startswith("gAAAA")  # 已按当前密钥重新加密


@pytest.mark.anyio
async def test_update_keeps_masked_value_untouched(
    db_session: AsyncSession,
    fernet_keys: Any,
) -> None:
    """掩码回传（未修改密钥）不得被当新密钥加密覆盖存量密文。"""
    _, stale = fernet_keys
    model = await _seed_stale_secret(db_session, stale)
    stale_ciphertext = model.app_secret
    await _update_settings(db_session, _build_request(mask_api_key("")))
    refreshed = await db_session.get(QualityFeishuAppSettings, model.id)
    assert refreshed is not None
    assert refreshed.app_secret == stale_ciphertext


@pytest.mark.anyio
async def test_test_connection_prompts_resave_on_stale_secret(
    db_session: AsyncSession,
    fernet_keys: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, stale = fernet_keys
    await _seed_stale_secret(db_session, stale)

    async def _fail(**_kwargs: object) -> str:
        raise AssertionError("不应在密文损坏时发起飞书连接测试")

    monkeypatch.setattr(
        "app.platform.integrations.feishu.auth.FeishuAuth.get_tenant_access_token",
        _fail,
    )
    with pytest.raises(AppException) as exc_info:
        await _test_connection(db_session)
    assert "重新输入 App Secret" in str(exc_info.value.message)


@pytest.mark.anyio
async def test_test_connection_succeeds_after_resave(
    db_session: AsyncSession,
    fernet_keys: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current, stale = fernet_keys
    model = await _seed_stale_secret(db_session, stale)
    await _update_settings(db_session, _build_request("valid-secret"))

    async def _fake_token(**kwargs: object) -> str:
        assert kwargs["app_secret"] == "valid-secret"
        return "token-x"

    monkeypatch.setattr(
        "app.platform.integrations.feishu.auth.FeishuAuth.get_tenant_access_token",
        _fake_token,
    )
    result = await _test_connection(db_session)
    assert result.success is True
    refreshed = await db_session.get(QualityFeishuAppSettings, model.id)
    assert refreshed is not None
    assert refreshed.last_test_status == "success"
