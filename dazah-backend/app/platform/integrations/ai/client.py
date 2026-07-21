"""Legacy AI service compatibility wrapper.

New business code should import ``app.core.llm.llm_client`` directly. This
module keeps old callers working while routing every request through the
system LLM configuration in ``core.llm_configs``.
"""

from app.core.llm import LLMOutputError, llm_client


class AIOutputError(LLMOutputError):
    """Raised when AI response cannot be parsed into expected structure."""


class AIService:
    """Compatibility adapter backed by the unified LLM client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        timeout: int = 120,
    ):
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        response_format: str = "json_object",
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> str:
        """Send a chat completion request and return the response text."""
        return await llm_client.chat(
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_parsed(
        self,
        messages: list[dict],
        expected_keys: list[str],
        temperature: float = 0.1,
    ) -> dict:
        """Chat + parse JSON response, validating expected keys exist."""
        return await llm_client.chat_json(
            messages=messages,
            expected_keys=expected_keys,
            temperature=temperature,
        )

    async def chat_vision(
        self,
        text_prompt: str,
        image_urls: list[str],
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> str:
        """Send a multimodal chat request with images (vision-capable model).

        Uses OpenAI-compatible vision format:
        messages = [{"role":"user", "content":[{"type":"text",...}, {"type":"image_url",...}]}]
        """
        return await llm_client.chat_vision(
            text_prompt=text_prompt,
            image_urls=image_urls,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_vision_parsed(
        self,
        text_prompt: str,
        image_urls: list[str],
        expected_keys: list[str],
        temperature: float = 0.1,
    ) -> dict:
        """Vision chat + parse JSON response, validating expected keys."""
        return await llm_client.chat_vision_json(
            text_prompt=text_prompt,
            image_urls=image_urls,
            expected_keys=expected_keys,
            temperature=temperature,
        )

    async def health_check(self) -> dict:
        """Check connectivity by listing models (lightweight endpoint)."""
        return await llm_client.health_check()

    async def close(self) -> None:
        return None
