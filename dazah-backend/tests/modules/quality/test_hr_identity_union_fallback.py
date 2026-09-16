"""人员 id 换发兜底：记录里保存的实体应用 open_id 人事应用查不到时，
用签发方应用（实体所属应用）兜底换发同一 union_id，避免混合命名空间
写入报 1254066 UserFieldConvFail（2026-09-16 维保编辑 500 根因）。
"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppException
from app.modules.quality.service import hr_identity


class _FakeContact:
    """按 app_id 模拟：人事应用查不到外部 id，实体应用总能查到。"""

    calls: list[tuple[str, str]] = []

    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id

    async def get_user_union_id(self, open_id: str) -> str | None:
        _FakeContact.calls.append((self.app_id, open_id))
        if self.app_id == "hr_app":
            return None
        return f"on_{open_id}"


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch):
    async def _get(_key: str) -> None:
        return None

    async def _set(_key: str, _value: str, ex: int | None = None) -> None:
        return None

    monkeypatch.setattr(hr_identity, "cache_get", _get)
    monkeypatch.setattr(hr_identity, "cache_set", _set)


def _patch_contacts(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.modules.hr.feishu.contact as contact_mod
    import app.modules.hr.feishu_settings_service as settings_mod

    _FakeContact.calls = []

    async def _hr_credentials(_db, purpose: str = "bitable"):
        return ("hr_app", "hr_secret")

    monkeypatch.setattr(
        settings_mod, "get_hr_feishu_app_credentials", _hr_credentials
    )
    monkeypatch.setattr(contact_mod, "FeishuContact", _FakeContact)


@pytest.mark.anyio
async def test_fallback_resolves_entity_namespace_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """人事应用查不到的 id（实体应用签发）经兜底应用换发成功。"""
    _patch_contacts(monkeypatch)
    result = await hr_identity.translate_hr_open_ids_to_union_ids(
        object(),
        ["ou_entity_1"],
        fallback_credentials=("entity_app", "entity_secret"),
    )
    assert result == {"ou_entity_1": "on_ou_entity_1"}
    assert ("entity_app", "ou_entity_1") in _FakeContact.calls


@pytest.mark.anyio
async def test_contact_unconfigured_uses_fallback_without_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """人事应用未配置时不再直接报错：有兜底凭据就继续换发。"""
    import app.modules.hr.feishu.contact as contact_mod
    import app.modules.hr.feishu_settings_service as settings_mod

    _FakeContact.calls = []

    async def _unconfigured(_db, purpose: str = "bitable"):
        raise settings_mod.HrFeishuNotConfigured("未配置")

    monkeypatch.setattr(
        settings_mod, "get_hr_feishu_app_credentials", _unconfigured
    )
    monkeypatch.setattr(contact_mod, "FeishuContact", _FakeContact)

    result = await hr_identity.translate_hr_open_ids_to_union_ids(
        object(),
        ["ou_entity_2"],
        fallback_credentials=("entity_app", "entity_secret"),
    )
    assert result == {"ou_entity_2": "on_ou_entity_2"}


@pytest.mark.anyio
async def test_contact_unconfigured_without_fallback_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无兜底凭据（如人事目录场景）保持原明确报错行为。"""
    import app.modules.hr.feishu.contact as contact_mod
    import app.modules.hr.feishu_settings_service as settings_mod

    async def _unconfigured(_db, purpose: str = "bitable"):
        raise settings_mod.HrFeishuNotConfigured("未配置")

    monkeypatch.setattr(
        settings_mod, "get_hr_feishu_app_credentials", _unconfigured
    )
    monkeypatch.setattr(contact_mod, "FeishuContact", _FakeContact)

    with pytest.raises(AppException, match="人事模块飞书应用未配置"):
        await hr_identity.translate_hr_open_ids_to_union_ids(object(), ["ou_x"])
