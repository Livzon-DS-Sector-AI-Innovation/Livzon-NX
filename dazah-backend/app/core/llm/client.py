"""Unified LLM client interface."""

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, cast

import httpx

from .config import LLMConfigData, get_config
from .exceptions import LLMOutputError, LLMProviderError, LLMRateLimitError

JsonObject = dict[str, Any]
Message = Mapping[str, Any]


def _model_name_suggests_kimi(model_name: str) -> bool:
    lower = model_name.strip().lower()
    return "kimi" in lower or "moonshot" in lower


def _model_name_uses_completion_tokens(model_name: str) -> bool:
    normalized = model_name.strip().lower().rsplit("/", 1)[-1]
    return normalized.startswith("gpt-5")


def _set_max_tokens(body: JsonObject, max_tokens: int, model_name: str) -> None:
    field = (
        "max_completion_tokens"
        if _model_name_uses_completion_tokens(model_name)
        else "max_tokens"
    )
    body[field] = max_tokens


def _apply_temperature(
    body: JsonObject,
    temperature: float | None,
    model_name: str = "",
) -> None:
    """Add temperature only when the value should override provider defaults."""
    if (
        temperature is not None
        and temperature > 0
        and not _model_name_suggests_kimi(model_name)
        and not _model_name_uses_completion_tokens(model_name)
    ):
        body["temperature"] = temperature


class LLMClient:
    """Unified LLM client for all modules.

    Usage:
        from app.core.llm import llm_client

        result = await llm_client.chat([{"role": "user", "content": "Hello"}])
    """

    async def _get_client_and_config(
        self, config_type: str = "text"
    ) -> tuple[httpx.AsyncClient, LLMConfigData]:
        """Get HTTP client and config."""
        config = await get_config(config_type)

        client = httpx.AsyncClient(
            base_url=config.api_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout_seconds,
        )
        return client, config

    async def chat(
        self,
        messages: Sequence[Message],
        response_format: str | None = "json_object",
        temperature: float | None = None,
        max_tokens: int = 16384,
        config_type: str = "text",
        enable_thinking: bool | None = None,
        custom_context: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """Send a chat completion request and return the response text.

        Args:
            messages: List of message dicts with 'role' and 'content'
            response_format: "json_object" or None
            temperature: Override config temperature
            max_tokens: Max tokens in response
            config_type: "text" or "vision"

        Returns:
            Response text from LLM

        Raises:
            LLMProviderError: If provider returns error
            LLMRateLimitError: If rate limit exceeded
        """
        client, config = await self._get_client_and_config(config_type)
        if timeout is not None:
            await client.aclose()
            client = httpx.AsyncClient(
                base_url=config.api_base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )

        try:
            # Use config temperature if not overridden
            temp = temperature if temperature is not None else config.temperature
            thinking = (
                getattr(config, "enable_thinking", False)
                if enable_thinking is None
                else enable_thinking
            )
            ctx = (
                getattr(config, "custom_context", None)
                if custom_context is None
                else custom_context
            )

            # For json_object format, ensure "json" appears in the prompt
            msgs = [dict(m) for m in messages]
            if ctx:
                msgs = [{"role": "system", "content": ctx}] + msgs
            if response_format == "json_object":
                last = msgs[-1]
                if (
                    isinstance(last.get("content"), str)
                    and "json" not in last["content"].lower()
                ):
                    last["content"] = last["content"] + "\n\n请以 JSON 格式返回结果。"

            body: JsonObject = {
                "model": config.model_name,
                "messages": msgs,
            }
            _set_max_tokens(body, max_tokens, config.model_name)
            _apply_temperature(body, temp, config.model_name)
            if response_format:
                body["response_format"] = {"type": response_format}
            if thinking:
                body["thinking"] = {"type": "enabled"}

            try:
                resp = await client.post("/chat/completions", json=body)
            except httpx.TimeoutException as exc:
                raise LLMProviderError("LLM 服务响应超时", status_code=504) from exc
            except httpx.RequestError as exc:
                raise LLMProviderError("LLM 服务暂不可用", status_code=502) from exc

            if resp.status_code == 429:
                raise LLMRateLimitError("Rate limit exceeded", status_code=429)

            if resp.is_error:
                error_text = resp.text[:500]
                raise LLMProviderError(
                    "LLM 服务返回错误",
                    status_code=resp.status_code,
                    raw_response=error_text,
                )

            data: Any = resp.json()
            return cast(str, data["choices"][0]["message"]["content"])

        finally:
            await client.aclose()

    async def chat_with_tools(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Mapping[str, Any]],
        temperature: float | None = None,
        max_tokens: int = 16384,
        config_type: str = "text",
        enable_thinking: bool | None = None,
        custom_context: str | None = None,
    ) -> JsonObject:
        """Send an OpenAI-compatible tool-calling request.

        Tool orchestration remains inside the owning backend service; this
        method only adapts the unified provider client and returns the
        assistant message envelope (never provider credentials or raw error
        bodies).
        """
        client, config = await self._get_client_and_config(config_type)
        try:
            thinking = (
                getattr(config, "enable_thinking", False)
                if enable_thinking is None
                else enable_thinking
            )
            ctx = (
                getattr(config, "custom_context", None)
                if custom_context is None
                else custom_context
            )
            msgs = [dict(message) for message in messages]
            if ctx:
                msgs = [{"role": "system", "content": ctx}] + msgs
            body: JsonObject = {
                "model": config.model_name,
                "messages": msgs,
                "tools": [dict(tool) for tool in tools],
            }
            _set_max_tokens(body, max_tokens, config.model_name)
            _apply_temperature(body, temperature, config.model_name)
            if thinking:
                body["thinking"] = {"type": "enabled"}
            try:
                response = await client.post("/chat/completions", json=body)
            except httpx.TimeoutException as exc:
                raise LLMProviderError("LLM 服务响应超时", status_code=504) from exc
            except httpx.RequestError as exc:
                raise LLMProviderError("LLM 服务暂不可用", status_code=502) from exc

            if response.status_code == 429:
                raise LLMRateLimitError("Rate limit exceeded", status_code=429)
            if response.is_error:
                raise LLMProviderError(
                    "LLM 服务返回错误", status_code=response.status_code
                )

            payload: Any = response.json()
            choices = payload.get("choices") if isinstance(payload, dict) else None
            if not isinstance(choices, list) or not choices:
                raise LLMProviderError("LLM 服务返回内容为空", status_code=502)
            message = (
                choices[0].get("message") if isinstance(choices[0], dict) else None
            )
            if not isinstance(message, dict):
                raise LLMProviderError("LLM 服务返回消息格式错误", status_code=502)
            return cast(JsonObject, message)
        finally:
            await client.aclose()

    async def chat_json(
        self,
        messages: Sequence[Message],
        expected_keys: list[str] | None = None,
        temperature: float | None = None,
        config_type: str = "text",
        enable_thinking: bool | None = None,
        timeout: int | None = None,
    ) -> JsonObject:
        """Chat + parse JSON response.

        Args:
            messages: List of message dicts
            expected_keys: Optional list of keys to validate
            temperature: Override config temperature
            config_type: "text" or "vision"

        Returns:
            Parsed JSON dict

        Raises:
            LLMOutputError: If response is not valid JSON or missing keys
        """
        raw = await self.chat(
            messages,
            response_format="json_object",
            temperature=temperature,
            config_type=config_type,
            enable_thinking=enable_thinking,
            timeout=timeout,
        )

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            for i, line in enumerate(lines):
                if not line.strip().startswith("```"):
                    cleaned = "\n".join(lines[i:])
                    break
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            parsed: Any = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMOutputError("LLM response is not valid JSON", raw) from e

        # Handle array responses - merge into single dict
        if isinstance(parsed, list):
            if len(parsed) == 0:
                raise LLMOutputError("LLM returned empty list", raw)
            if isinstance(parsed[0], dict):
                merged: JsonObject = {}
                for item in parsed:
                    for k, v in item.items():
                        if k in merged and isinstance(v, str):
                            merged[k] = merged[k] + "；" + v
                        else:
                            merged[k] = v
                parsed = merged
            else:
                parsed = {"_raw": raw}

        if not isinstance(parsed, dict):
            raise LLMOutputError("LLM response is not a JSON object", raw)

        # Coerce boolean strings
        for k, v in parsed.items():
            if isinstance(v, str) and v.lower() in ("true", "false"):
                parsed[k] = v.lower() == "true"

        # Validate expected keys
        if expected_keys:
            missing = [k for k in expected_keys if k not in parsed]
            if missing:
                raise LLMOutputError(f"LLM response missing keys: {missing}", raw)

        return cast(JsonObject, parsed)

    async def chat_vision(
        self,
        text_prompt: str,
        image_urls: list[str],
        temperature: float | None = None,
        max_tokens: int = 16384,
    ) -> str:
        """Send a multimodal chat request with images.

        Args:
            text_prompt: Text prompt
            image_urls: List of image URLs (can be data: URIs or http URLs)
            temperature: Override config temperature
            max_tokens: Max tokens in response

        Returns:
            Response text from LLM
        """
        client, config = await self._get_client_and_config("vision")

        try:
            temp = temperature if temperature is not None else config.temperature

            image_parts: list[JsonObject] = []
            for url in image_urls:
                image_parts.append({"type": "image_url", "image_url": {"url": url}})
            text_part = {"type": "text", "text": text_prompt}
            # Kimi's multimodal adapter expects image parts before text.
            content_parts = (
                image_parts + [text_part]
                if _model_name_suggests_kimi(config.model_name)
                else [text_part] + image_parts
            )

            body: JsonObject = {
                "model": config.model_name,
                "messages": [{"role": "user", "content": content_parts}],
            }
            _set_max_tokens(body, max_tokens, config.model_name)
            _apply_temperature(body, temp, config.model_name)

            try:
                resp = await client.post("/chat/completions", json=body)
            except httpx.TimeoutException as exc:
                raise LLMProviderError("LLM 服务响应超时", status_code=504) from exc
            except httpx.RequestError as exc:
                raise LLMProviderError("LLM 服务暂不可用", status_code=502) from exc

            if resp.status_code == 429:
                raise LLMRateLimitError("Rate limit exceeded", status_code=429)

            if resp.is_error:
                error_text = resp.text[:500]
                raise LLMProviderError(
                    "视觉模型服务返回错误",
                    status_code=resp.status_code,
                    raw_response=error_text,
                )

            data: Any = resp.json()
            return cast(str, data["choices"][0]["message"]["content"])

        finally:
            await client.aclose()

    async def chat_vision_json(
        self,
        text_prompt: str,
        image_urls: list[str],
        expected_keys: list[str] | None = None,
        temperature: float | None = None,
    ) -> JsonObject:
        """Vision chat + parse JSON response.

        Args:
            text_prompt: Text prompt
            image_urls: List of image URLs
            expected_keys: Optional list of keys to validate
            temperature: Override config temperature

        Returns:
            Parsed JSON dict
        """
        raw = await self.chat_vision(
            text_prompt,
            image_urls,
            temperature=temperature,
        )

        # Strip markdown code fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            for i, line in enumerate(lines):
                if not line.strip().startswith("```"):
                    cleaned = "\n".join(lines[i:])
                    break
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            parsed: Any = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMOutputError("Vision LLM response is not valid JSON", raw) from e

        if not isinstance(parsed, dict):
            raise LLMOutputError("Vision LLM response is not a JSON object", raw)

        # Coerce boolean strings
        for k, v in parsed.items():
            if isinstance(v, str) and v.lower() in ("true", "false"):
                parsed[k] = v.lower() == "true"

        if expected_keys:
            missing = [k for k in expected_keys if k not in parsed]
            if missing:
                raise LLMOutputError(
                    f"Vision LLM response missing keys: {missing}", raw
                )

        return cast(JsonObject, parsed)

    async def health_check(self) -> JsonObject:
        """Check LLM connectivity.

        Returns:
            Dict with 'status' and optional 'detail'
        """
        try:
            config = await get_config("text")
            client = httpx.AsyncClient(
                base_url=config.api_base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {config.api_key}"},
                timeout=5.0,
            )
            try:
                resp = await client.get("/models")
                return {
                    "status": "ok" if resp.is_success else "error",
                    "detail": f"HTTP {resp.status_code}",
                }
            finally:
                await client.aclose()
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    async def stream_chat(
        self,
        messages: Sequence[Message],
        temperature: float | None = None,
        max_tokens: int = 4096,
        enable_thinking: bool | None = None,
        custom_context: str | None = None,
    ) -> AsyncIterator[dict[str, str]]:
        """Stream chat completion tokens.

        Yields dicts with keys:
            - type: "reasoning" | "content"
            - text: the token text
        """
        import json as json_module

        config = await get_config("text")
        temp = temperature if temperature is not None else config.temperature
        thinking = (
            getattr(config, "enable_thinking", False)
            if enable_thinking is None
            else enable_thinking
        )
        ctx = (
            getattr(config, "custom_context", None)
            if custom_context is None
            else custom_context
        )

        msgs = list(messages)
        if ctx:
            msgs = [{"role": "system", "content": ctx}] + msgs

        body: JsonObject = {
            "model": config.model_name,
            "messages": msgs,
            "stream": True,
        }
        _set_max_tokens(body, max_tokens, config.model_name)
        _apply_temperature(body, temp, config.model_name)
        if thinking:
            body["thinking"] = {"type": "enabled"}

        async with httpx.AsyncClient(
            base_url=config.api_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout_seconds,
        ) as client:
            async with client.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code == 429:
                    raise LLMRateLimitError("Rate limit exceeded", status_code=429)

                if resp.is_error:
                    error_text = await resp.aread()
                    detail = error_text.decode()[:500]
                    raise LLMProviderError(
                        f"Stream API error: {resp.status_code} - {detail}",
                        status_code=resp.status_code,
                    )

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json_module.loads(data)
                        if not chunk.get("choices"):
                            continue

                        delta = chunk["choices"][0].get("delta", {})
                        reasoning = delta.get("reasoning_content")
                        content = delta.get("content")

                        if reasoning:
                            yield {"type": "reasoning", "text": reasoning}
                        if content:
                            yield {"type": "content", "text": content}
                    except json_module.JSONDecodeError:
                        continue


# Global singleton instance
llm_client = LLMClient()
