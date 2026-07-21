"""Provider registry for LLM services."""

from typing import Literal
from dataclasses import dataclass


ProviderType = Literal["openai", "deepseek", "qwen", "moonshot", "custom"]


@dataclass
class ProviderConfig:
    """Provider configuration."""
    name: str
    base_url: str
    default_model: str
    supports_vision: bool = False


# Known provider configurations
PROVIDERS: dict[ProviderType, ProviderConfig] = {
    "openai": ProviderConfig(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        supports_vision=True,
    ),
    "deepseek": ProviderConfig(
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        supports_vision=False,
    ),
    "qwen": ProviderConfig(
        name="Qwen (DashScope)",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-vl-max",
        supports_vision=True,
    ),
    "moonshot": ProviderConfig(
        name="Moonshot (Kimi)",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-32k",
        supports_vision=False,
    ),
}


def get_provider_config(provider: ProviderType | str) -> ProviderConfig:
    """Get provider configuration by name."""
    if provider in PROVIDERS:
        return PROVIDERS[provider]
    # Custom provider - return minimal config
    return ProviderConfig(
        name=provider,
        base_url="",
        default_model="",
        supports_vision=False,
    )
