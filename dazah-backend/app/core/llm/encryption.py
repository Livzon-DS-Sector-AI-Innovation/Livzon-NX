"""Fernet encryption for API keys."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

from .exceptions import LLMConfigError


def _get_fernet() -> Fernet:
    """Resolve the configured key; never fall back to plaintext credentials."""
    key = get_settings().LLM_ENCRYPTION_KEY
    if not key:
        raise LLMConfigError("LLM_ENCRYPTION_KEY is required for credential encryption")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise LLMConfigError("Invalid LLM_ENCRYPTION_KEY") from exc


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt a credential, refusing writes when encryption is unavailable."""
    fernet = _get_fernet()
    return fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt a credential; plaintext and incompatible ciphertext are rejected."""
    fernet = _get_fernet()
    try:
        return fernet.decrypt(encrypted_key.encode()).decode()
    except InvalidToken:
        raise LLMConfigError(
            "Failed to decrypt API key - invalid encryption key or corrupted data"
        )


def mask_api_key(api_key: str) -> str:
    """Mask API key for display (show first 10 chars + ****)."""
    if not api_key or len(api_key) <= 10:
        return "****"
    return f"{api_key[:10]}****"
