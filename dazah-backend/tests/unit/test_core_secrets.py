from dataclasses import dataclass

import pytest
from cryptography.fernet import Fernet

from app.core import secrets


@dataclass
class FakeSettings:
    ENCRYPTION_KEY: str | None = None
    is_production: bool = False


def patch_settings(monkeypatch: pytest.MonkeyPatch, settings: FakeSettings) -> None:
    monkeypatch.setattr(secrets, "get_settings", lambda: settings)


def test_encrypt_secret_uses_fernet_with_version_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode()
    patch_settings(monkeypatch, FakeSettings(ENCRYPTION_KEY=key))

    encrypted = secrets.encrypt_secret("app-secret")

    assert encrypted.startswith(secrets.ENCRYPTED_SECRET_PREFIX)
    assert encrypted != "app-secret"
    assert secrets.decrypt_secret(encrypted) == "app-secret"


def test_encrypt_secret_rejects_plaintext_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_settings(monkeypatch, FakeSettings(is_production=True))

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        secrets.encrypt_secret("app-secret")


def test_decrypt_secret_keeps_legacy_plaintext_without_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = Fernet.generate_key().decode()
    patch_settings(monkeypatch, FakeSettings(ENCRYPTION_KEY=key))

    assert secrets.decrypt_secret("legacy-plain-secret") == "legacy-plain-secret"
