"""Fernet encryption for API keys."""

import os
from cryptography.fernet import Fernet, InvalidToken
from .exceptions import LLMConfigError


def _get_fernet() -> Fernet | None:
    """Get Fernet instance if encryption key is configured."""
    key = os.getenv("LLM_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise LLMConfigError(f"Invalid LLM_ENCRYPTION_KEY: {e}")


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt API key. Returns plain text if encryption not configured."""
    fernet = _get_fernet()
    if not fernet:
        return plain_key
    return fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key. Returns as-is if encryption not configured."""
    fernet = _get_fernet()
    if not fernet:
        return encrypted_key
    try:
        return fernet.decrypt(encrypted_key.encode()).decode()
    except InvalidToken:
        raise LLMConfigError("Failed to decrypt API key - invalid encryption key or corrupted data")


def mask_api_key(api_key: str) -> str:
    """Mask API key for display (show first 10 chars + ****)."""
    if not api_key or len(api_key) <= 10:
        return "****"
    return f"{api_key[:10]}****"
