"""Centralized LLM service for all modules.

Usage:
    from app.core.llm import llm_client

    result = await llm_client.chat([{"role": "user", "content": "Hello"}])
    parsed = await llm_client.chat_json(messages, expected_keys=["key1", "key2"])
"""

from .client import LLMClient, llm_client
from .config import (
    LLMConfigData,
    LLMConfigModel,
    get_active_config,
    get_config,
    get_env_config,
)
from .encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from .exceptions import (
    LLMConfigError,
    LLMError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from .providers import PROVIDERS, ProviderConfig, ProviderType, get_provider_config

__all__ = [
    # Client
    "LLMClient",
    "llm_client",
    # Config
    "get_config",
    "get_active_config",
    "get_env_config",
    "LLMConfigData",
    "LLMConfigModel",
    # Exceptions
    "LLMError",
    "LLMConfigError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMOutputError",
    # Encryption
    "encrypt_api_key",
    "decrypt_api_key",
    "mask_api_key",
    # Providers
    "ProviderConfig",
    "ProviderType",
    "PROVIDERS",
    "get_provider_config",
]
