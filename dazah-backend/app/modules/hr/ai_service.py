"""AI chat service for HR turnover analysis.

Uses core.llm for streaming completions.
"""

from collections.abc import AsyncGenerator

from app.core.config import get_settings
from app.core.llm import llm_client


class AiChatService:
    """Service for streaming chat completions via core.llm."""

    def __init__(self) -> None:
        pass

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Stream chat completion tokens from the LLM.

        Yields dicts with keys:
            - type: "reasoning" | "content"
            - text: the token text
        """
        all_messages: list[dict[str, str]] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        async for chunk in llm_client.stream_chat(messages=all_messages):
            yield chunk

    @staticmethod
    def build_system_prompt(page: str | None = None) -> str:
        """Build the system prompt for the HR assistant."""
        settings = get_settings()
        prompt = settings.AI_SYSTEM_PROMPT

        if page:
            prompt += f"\n当前页面：{page}"

        return prompt
