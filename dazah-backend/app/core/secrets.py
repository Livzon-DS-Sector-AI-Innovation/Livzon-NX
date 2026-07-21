"""Generic secret encryption helpers."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

ENCRYPTED_SECRET_PREFIX = "fernet:v1:"


def _get_fernet() -> Fernet | None:
    settings = get_settings()
    key = getattr(settings, "ENCRYPTION_KEY", None)
    if not key:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plain_text: str) -> str:
    settings = get_settings()
    fernet = _get_fernet()
    if not fernet:
        if getattr(settings, "is_production", False):
            raise RuntimeError("ENCRYPTION_KEY must be configured in production")
        return plain_text
    encrypted = fernet.encrypt(plain_text.encode()).decode()
    return f"{ENCRYPTED_SECRET_PREFIX}{encrypted}"


def decrypt_secret(encrypted_text: str) -> str:
    fernet = _get_fernet()
    if encrypted_text.startswith(ENCRYPTED_SECRET_PREFIX):
        if not fernet:
            raise RuntimeError("ENCRYPTION_KEY is required to decrypt secret")
        encrypted_text = encrypted_text.removeprefix(ENCRYPTED_SECRET_PREFIX)
        try:
            return fernet.decrypt(encrypted_text.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Failed to decrypt secret") from exc

    if not fernet:
        return encrypted_text
    try:
        return fernet.decrypt(encrypted_text.encode()).decode()
    except InvalidToken:
        return encrypted_text


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 10:
        return "****"
    return f"{secret[:6]}****{secret[-4:]}"
