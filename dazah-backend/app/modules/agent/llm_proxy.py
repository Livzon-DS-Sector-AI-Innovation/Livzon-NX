from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.llm.config import get_config

SUPPORTED_FIELDS = {
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "max_tokens",
    "stream",
    "response_format",
    "parallel_tool_calls",
    "stop",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "reasoning_effort",
}


async def list_active_text_models() -> dict[str, Any]:
    config = await get_config("text")
    return {
        "object": "list",
        "data": [
            {
                "id": "dazah-active-text",
                "object": "model",
                "owned_by": "dazah",
                "root": config.model_name,
            }
        ],
    }


async def forward_chat_completion(payload: dict[str, Any]) -> Any:
    config = await get_config("vision" if payload_has_images(payload) else "text")
    body = build_provider_body(payload, config.model_name, config.temperature)
    retry_without_thinking = should_retry_without_auto_thinking(
        payload, body, config.model_name
    )
    url = config.api_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(config.timeout_seconds)
    if body.get("stream"):
        return StreamingResponse(
            _stream_chat(url, headers, body, timeout, retry_without_thinking),
            media_type="text/event-stream",
        )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=body)
        if response.status_code >= 400 and retry_without_thinking:
            response = await client.post(
                url,
                headers=headers,
                json=body_without_thinking(body),
            )
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, response.text[:1000])
    return response.json()


def payload_has_images(payload: dict[str, Any]) -> bool:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") in {
                "image",
                "image_url",
                "input_image",
            }:
                return True
    return False


def build_provider_body(
    payload: dict[str, Any],
    model_name: str,
    temperature: float,
) -> dict[str, Any]:
    """Build the upstream OpenAI-compatible request body.

    Hermes-Lite sends provider-specific fields through the OpenAI SDK's
    ``extra_body`` parameter. Because this proxy posts raw JSON via httpx,
    those keys must be merged into the top-level body before forwarding.
    """
    body = {key: value for key, value in payload.items() if key in SUPPORTED_FIELDS}
    extra_body = payload.get("extra_body")
    if isinstance(extra_body, dict):
        body.update(extra_body)

    body["model"] = model_name
    if temperature > 0:
        body.setdefault("temperature", temperature)
    apply_model_compatibility_defaults(body, model_name)
    return body


def apply_model_compatibility_defaults(body: dict[str, Any], model_name: str) -> None:
    """Apply defaults required by specific upstream model families."""
    if not model_name_suggests_kimi(model_name):
        return

    body.pop("temperature", None)

    # When Hermes talks through the Dazah proxy it only sees the proxy model
    # id (dazah-active-text), so its Kimi-specific thinking controls are not
    # emitted. Kimi may otherwise return reasoning-only chunks that leave the
    # OpenAI-compatible visible content empty. Default to non-thinking mode
    # unless the caller explicitly opted into a Kimi thinking shape.
    if "thinking" not in body:
        body.pop("reasoning_effort", None)
        body["thinking"] = {"type": "disabled"}


def model_name_suggests_kimi(model_name: str) -> bool:
    lower = model_name.strip().lower()
    return "kimi" in lower or "moonshot" in lower


def should_retry_without_auto_thinking(
    payload: dict[str, Any],
    body: dict[str, Any],
    model_name: str,
) -> bool:
    if not model_name_suggests_kimi(model_name):
        return False
    if body.get("thinking") != {"type": "disabled"}:
        return False
    extra_body = payload.get("extra_body")
    caller_sent_thinking = isinstance(extra_body, dict) and "thinking" in extra_body
    return not caller_sent_thinking and "thinking" not in payload


def body_without_thinking(body: dict[str, Any]) -> dict[str, Any]:
    retry_body = dict(body)
    retry_body.pop("thinking", None)
    return retry_body


async def _stream_chat(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: httpx.Timeout,
    retry_without_thinking: bool = False,
) -> AsyncIterator[bytes]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400 and retry_without_thinking:
                await response.aread()
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=body_without_thinking(body),
                ) as retry_response:
                    if retry_response.status_code >= 400:
                        detail = await retry_response.aread()
                        raise HTTPException(
                            status.HTTP_502_BAD_GATEWAY,
                            detail.decode(errors="ignore")[:1000],
                        )
                    async for chunk in retry_response.aiter_bytes():
                        yield chunk
                return
            if response.status_code >= 400:
                detail = await response.aread()
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, detail.decode(errors="ignore")[:1000]
                )
            async for chunk in response.aiter_bytes():
                yield chunk
