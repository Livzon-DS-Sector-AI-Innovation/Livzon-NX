"""认证与外部回调安全辅助函数。"""

import hashlib
import hmac

from app.core.config import get_settings


def verify_feishu_signature(
    *,
    timestamp: str | None,
    nonce: str | None,
    body: str,
    signature: str | None,
) -> bool:
    """Verify a Feishu callback using the configured event encrypt key.

    Feishu signs ``timestamp + nonce + encrypt_key + body`` with SHA-256.
    Missing configuration or headers fails closed so a local deployment does
    not accidentally expose the public webhook without verification.
    """

    encrypt_key = get_settings().FEISHU_EVENT_ENCRYPT_KEY
    if not encrypt_key or not timestamp or not nonce or not signature:
        return False
    payload = f"{timestamp}{nonce}{encrypt_key}{body}".encode()
    expected = hashlib.sha256(payload).hexdigest()
    return hmac.compare_digest(expected, signature)
