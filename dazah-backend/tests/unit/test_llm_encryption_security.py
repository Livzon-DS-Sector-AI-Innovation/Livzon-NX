"""Credential encryption must fail closed and preserve encrypted round trips."""

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.core.llm import encryption
from app.core.llm.exceptions import LLMConfigError


@pytest.mark.parametrize("operation", ["encrypt_api_key", "decrypt_api_key"])
def test_missing_key_never_passes_through_credentials(monkeypatch, operation):
    monkeypatch.setattr(
        encryption,
        "get_settings",
        lambda: SimpleNamespace(LLM_ENCRYPTION_KEY=None),
        raising=False,
    )
    monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="LLM_ENCRYPTION_KEY"):
        getattr(encryption, operation)("synthetic-credential")


def test_encryption_uses_settings_key_and_round_trips(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(
        encryption,
        "get_settings",
        lambda: SimpleNamespace(LLM_ENCRYPTION_KEY=key),
        raising=False,
    )
    encrypted = encryption.encrypt_api_key("synthetic-credential")
    assert encrypted != "synthetic-credential"
    assert encryption.decrypt_api_key(encrypted) == "synthetic-credential"


def test_invalid_key_error_does_not_include_key(monkeypatch):
    invalid = "synthetic-invalid-encryption-value"
    monkeypatch.setattr(
        encryption,
        "get_settings",
        lambda: SimpleNamespace(LLM_ENCRYPTION_KEY=invalid),
        raising=False,
    )
    with pytest.raises(LLMConfigError) as error:
        encryption.encrypt_api_key("synthetic-credential")
    assert invalid not in str(error.value)


def test_plaintext_and_wrong_key_ciphertext_are_rejected(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(
        encryption,
        "get_settings",
        lambda: SimpleNamespace(LLM_ENCRYPTION_KEY=key),
        raising=False,
    )
    for value in (
        "synthetic-plaintext",
        Fernet(Fernet.generate_key()).encrypt(b"synthetic-credential").decode(),
    ):
        with pytest.raises(LLMConfigError):
            encryption.decrypt_api_key(value)
