"""Legacy AI/LLM integration adapter.

Business modules should use ``app.core.llm.llm_client`` directly. The exports
here are retained for older imports and route all calls through the same
system-level LLM configuration.
"""

from functools import lru_cache

from app.platform.integrations.ai.client import AIOutputError, AIService

__all__ = ["AIService", "AIOutputError", "get_ai_service"]


@lru_cache
def get_ai_service() -> AIService:
    """Return a compatibility adapter backed by ``app.core.llm``."""
    return AIService(api_key="", base_url="", model="")
