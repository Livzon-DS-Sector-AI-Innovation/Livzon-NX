from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.llm.config import get_config
from app.core.llm.exceptions import LLMConfigError

SUPPORTED_FIELDS = {
    "messages",
    "tools",
    "tool_choice",
    "temperature",
    "max_tokens",
    "max_completion_tokens",
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

_IMAGE_PART_TYPES = frozenset({"image", "image_url", "input_image"})
_VISION_CONFIG_UNAVAILABLE_MESSAGE = (
    "当前激活的模型未配置图片理解能力，请在系统设置中重新检测并激活支持图片的模型。"
)
_TEXT_CONFIG_UNAVAILABLE_MESSAGE = (
    "当前未配置可用的 LLM 模型，请在系统设置中配置并激活模型。"
)


async def list_active_text_models() -> dict[str, Any]:
    try:
        config = await get_config("text")
    except LLMConfigError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            _TEXT_CONFIG_UNAVAILABLE_MESSAGE,
        ) from exc
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
    has_images = payload_has_images(payload)
    try:
        config = await get_config("vision" if has_images else "text")
    except LLMConfigError as exc:
        detail = (
            _VISION_CONFIG_UNAVAILABLE_MESSAGE
            if has_images
            else _TEXT_CONFIG_UNAVAILABLE_MESSAGE
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail,
        ) from exc
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
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code >= 400 and retry_without_thinking:
                response = await client.post(
                    url,
                    headers=headers,
                    json=body_without_thinking(body),
                )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "LLM 上游服务响应超时，请稍后重试。",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "LLM 上游服务暂不可用，请稍后重试。",
        ) from exc
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, response.text[:1000])
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "LLM 上游返回了无效响应，请稍后重试。",
        ) from exc


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
    if (
        _model_name_uses_completion_tokens(model_name)
        and "max_completion_tokens" not in body
        and "max_tokens" in body
    ):
        body["max_completion_tokens"] = body.pop("max_tokens")
    if "messages" in body:
        body["messages"] = _normalize_multimodal_messages(
            body["messages"], model_name
        )
    if temperature > 0 and not _model_name_uses_completion_tokens(model_name):
        body.setdefault("temperature", temperature)
    apply_model_compatibility_defaults(body, model_name)
    return body


def _normalize_multimodal_messages(messages: Any, model_name: str) -> Any:
    """Apply provider-specific ordering without mutating the caller payload.

    Hermes talks to this endpoint using the proxy model alias, so it cannot
    apply model-specific message shaping itself. Kimi's multimodal adapter
    expects image blocks before text blocks; other providers keep the
    original OpenAI-compatible order.
    """
    if not model_name_suggests_kimi(model_name) or not isinstance(messages, list):
        return messages

    normalized_messages: list[Any] = []
    changed = False
    for message in messages:
        if not isinstance(message, dict):
            normalized_messages.append(message)
            continue
        content = message.get("content")
        if not isinstance(content, list):
            normalized_messages.append(message)
            continue

        image_parts = [
            part
            for part in content
            if isinstance(part, dict) and part.get("type") in _IMAGE_PART_TYPES
        ]
        if not image_parts:
            normalized_messages.append(message)
            continue

        other_parts = [
            part
            for part in content
            if not (isinstance(part, dict) and part.get("type") in _IMAGE_PART_TYPES)
        ]
        normalized_message = dict(message)
        normalized_message["content"] = image_parts + other_parts
        normalized_messages.append(normalized_message)
        changed = True

    return normalized_messages if changed else messages


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


def _model_name_uses_completion_tokens(model_name: str) -> bool:
    normalized = model_name.strip().lower().rsplit("/", 1)[-1]
    return normalized.startswith("gpt-5")


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
