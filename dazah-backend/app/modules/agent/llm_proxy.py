import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack
from typing import Any

import httpx
from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.core.llm.capacity import hold_capacity
from app.core.llm.config import get_config
from app.core.llm.exceptions import LLMConfigError, LLMRateLimitError
from app.core.llm.http_security import provider_client, validate_provider_url


class _CapacityStream(StreamingResponse):
    """Release admission even when the client disconnects before the first byte."""

    def __init__(
        self, content: AsyncIterator[bytes], lease: AbstractAsyncContextManager[object]
    ) -> None:
        self.lease = lease
        self._released = False
        super().__init__(self._iterate(content), media_type="text/event-stream")

    async def _release(self) -> None:
        if not self._released:
            self._released = True
            await self.lease.__aexit__(None, None, None)

    async def _iterate(self, content: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
        try:
            async for chunk in content:
                yield chunk
        finally:
            try:
                close = getattr(content, "aclose", None)
                if close is not None:
                    await close()
            finally:
                await self._release()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                close = getattr(self.body_iterator, "aclose", None)
                if close is not None:
                    await close()
            finally:
                await self._release()


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
    validate_provider_url(config.api_base_url)
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
        resources = AsyncExitStack()
        try:
            await resources.enter_async_context(hold_capacity())
            client = await resources.enter_async_context(
                provider_client(timeout=timeout)
            )
            response = await resources.enter_async_context(
                client.stream("POST", url, headers=headers, json=body)
            )
            if response.status_code >= 400 and retry_without_thinking:
                await response.aclose()
                response = await resources.enter_async_context(
                    client.stream(
                        "POST", url, headers=headers, json=body_without_thinking(body)
                    )
                )
            if response.status_code >= 300:
                raise _upstream_http_error(response.status_code)
        except LLMRateLimitError as exc:
            await resources.aclose()
            raise HTTPException(429, "AI 服务繁忙，请稍后重试") from exc
        except httpx.TimeoutException as exc:
            await resources.aclose()
            raise HTTPException(504, "LLM 上游服务响应超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            await resources.aclose()
            raise HTTPException(502, "LLM 上游服务暂不可用，请稍后重试。") from exc
        except BaseException:
            await resources.aclose()
            raise
        return _CapacityStream(_stream_chat(response), resources)
    try:
        async with hold_capacity(), provider_client(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code >= 400 and retry_without_thinking:
                response = await client.post(
                    url,
                    headers=headers,
                    json=body_without_thinking(body),
                )
    except LLMRateLimitError as exc:
        raise HTTPException(429, "AI 服务繁忙，请稍后重试") from exc
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
    if response.status_code >= 300:
        raise _upstream_http_error(response.status_code)
    try:
        data = response.json()
        if (
            not isinstance(data, dict)
            or data.get("error") is not None
            or not isinstance(data.get("choices"), list)
            or not data["choices"]
        ):
            raise HTTPException(502, "LLM 上游返回了无效响应，请稍后重试。")
        return data
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
        body["messages"] = _normalize_multimodal_messages(body["messages"], model_name)
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
    if _model_name_uses_completion_tokens(model_name):
        # Hermes sees only the proxy alias, so it cannot apply the actual
        # model's temperature contract. Match the unified client's behavior.
        body.pop("temperature", None)
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


def _upstream_http_error(status_code: int) -> HTTPException:
    if status_code == 429:
        return HTTPException(429, "AI 服务繁忙，请稍后重试")
    if status_code in {408, 504}:
        return HTTPException(504, "LLM 上游服务响应超时，请稍后重试。")
    return HTTPException(502, "LLM 上游服务暂不可用，请稍后重试。")


def _stream_error_frame() -> bytes:
    payload = {
        "error": {
            "message": "LLM 上游流式响应失败，请稍后重试。",
            "type": "upstream_error",
            "code": "upstream_error",
        }
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode()


def _safe_stream_frame(lines: list[str]) -> tuple[bytes, bool]:
    data = "\n".join(line[5:].lstrip(" ") for line in lines if line.startswith("data:"))
    if any(line.startswith("event:") and line[6:].strip() == "error" for line in lines):
        return _stream_error_frame(), True
    if not data:
        if any(
            not line.startswith((":", "event:", "id:", "retry:")) for line in lines
        ):
            return _stream_error_frame(), True
        return b": keepalive\n\n", False
    if data.strip() == "[DONE]":
        return b"data: [DONE]\n\n", True
    try:
        payload = json.loads(data)
    except ValueError:
        return _stream_error_frame(), True
    if (
        not isinstance(payload, dict)
        or payload.get("error") is not None
        or payload.get("type") == "error"
        or not isinstance(payload.get("choices"), list)
    ):
        return _stream_error_frame(), True
    return ("data: " + data + "\n\n").encode(), False


async def _stream_chat(response: httpx.Response) -> AsyncIterator[bytes]:
    """Bound frame buffering and replace errors before forwarding SSE data."""
    lines: list[str] = []
    frame_size = 0
    pending = b""
    try:
        async for chunk in response.aiter_bytes():
            pending += chunk
            while b"\n" in pending:
                raw_line, pending = pending.split(b"\n", 1)
                frame_size += len(raw_line)
                if frame_size > 256 * 1024:
                    yield _stream_error_frame()
                    return
                line = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
                if line:
                    lines.append(line)
                    if len(lines) > 1024:
                        yield _stream_error_frame()
                        return
                elif lines:
                    frame, finished = _safe_stream_frame(lines)
                    yield frame
                    if finished:
                        return
                    lines, frame_size = [], 0
            if len(pending) + frame_size > 256 * 1024:
                yield _stream_error_frame()
                return
        if pending:
            lines.append(pending.decode("utf-8", errors="replace"))
        if lines:
            frame, _ = _safe_stream_frame(lines)
            yield frame
    except httpx.HTTPError:
        yield _stream_error_frame()
