"""LLM configuration management."""

import os
from dataclasses import dataclass

from sqlalchemy import Boolean, Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import async_session_factory
from app.shared.base_model import BaseModel

from .encryption import decrypt_api_key
from .exceptions import LLMConfigError


@dataclass
class LLMConfigData:
    """LLM configuration data."""

    id: str
    config_name: str
    config_type: str  # Auto-detected capability: "text" or "vision"
    api_base_url: str
    api_key: str  # Decrypted API key
    model_name: str
    temperature: float
    timeout_seconds: int
    is_active: bool


class LLMConfigModel(BaseModel):
    """Database model for LLM configuration."""

    __tablename__ = "llm_configs"
    __table_args__ = {"schema": "core", "comment": "LLM configuration table"}

    config_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Configuration name"
    )
    config_type: Mapped[str] = mapped_column(
        String(20),
        default="text",
        server_default="text",
        nullable=False,
        comment="Auto-detected capability: text or vision",
    )
    api_base_url: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="API base URL"
    )
    encrypted_api_key: Mapped[str] = mapped_column(
        String(1000), nullable=False, comment="Encrypted API key"
    )
    model_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Model name"
    )
    temperature: Mapped[float] = mapped_column(
        Float, default=0.1, server_default="0.1", nullable=False, comment="Temperature"
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        default=120,
        server_default="120",
        nullable=False,
        comment="Timeout seconds",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment="Is active config",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Notes")

    def to_config_data(self) -> LLMConfigData:
        """Convert to config data with decrypted API key."""
        return LLMConfigData(
            id=str(self.id),
            config_name=self.config_name,
            config_type=self.config_type,
            api_base_url=self.api_base_url,
            api_key=decrypt_api_key(self.encrypted_api_key),
            model_name=self.model_name,
            temperature=self.temperature,
            timeout_seconds=self.timeout_seconds,
            is_active=self.is_active,
        )


async def get_active_config(config_type: str = "text") -> LLMConfigData | None:
    """Get active LLM config from database.

    Args:
        config_type: "text" or "vision"

    Returns:
        LLMConfigData or None if not found
    """
    async with async_session_factory() as session:
        query = select(LLMConfigModel).where(
            LLMConfigModel.is_active.is_(True),
            LLMConfigModel.is_deleted.is_(False),
        )
        if config_type == "vision":
            query = query.where(LLMConfigModel.config_type == "vision")
        query = query.order_by(LLMConfigModel.updated_at.desc()).limit(1)
        result = await session.execute(query)
        config = result.scalar_one_or_none()
        if config:
            return config.to_config_data()
    return None


def get_env_config() -> LLMConfigData | None:
    """Get LLM config from environment variables (for local dev).

    Returns:
        LLMConfigData or None if not configured
    """
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("LLM_MODEL", "deepseek-chat")

    if not api_key:
        return None

    return LLMConfigData(
        id="env",
        config_name="Environment Config",
        config_type="text",
        api_base_url=base_url,
        api_key=api_key,
        model_name=model,
        temperature=0.1,
        timeout_seconds=120,
        is_active=True,
    )


async def get_config(config_type: str = "text") -> LLMConfigData:
    """Get LLM config - tries DB first, falls back to env.

    Args:
        config_type: "text" or "vision"

    Returns:
        LLMConfigData

    Raises:
        LLMConfigError: If no config is available
    """
    # Try DB config first (production/staging)
    config = await get_active_config(config_type)
    if config:
        return config

    # Fall back to env config (local dev)
    config = get_env_config()
    if config:
        return config

    raise LLMConfigError(
        "LLM not configured. Set LLM_API_KEY in the workspace root .env.local "
        "or configure via admin UI."
    )
