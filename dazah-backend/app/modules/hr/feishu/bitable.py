"""Compatibility re-export for the platform-level Feishu Bitable client."""

from app.platform.integrations.feishu.bitable import (
    BitableClient,
    FeishuBitableSync,
    _to_ms_timestamp,
)

__all__ = ["BitableClient", "FeishuBitableSync", "_to_ms_timestamp"]
