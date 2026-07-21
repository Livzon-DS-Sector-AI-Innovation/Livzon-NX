"""Compatibility re-export for the platform-level Feishu auth client.

HR-specific code should keep its field mapping here, but tenant token management
belongs to app.platform.integrations.feishu.
"""

from app.platform.integrations.feishu.auth import FeishuAuth

__all__ = ["FeishuAuth"]
