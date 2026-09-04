"""Runtime capability detection for OpenAI-compatible LLM endpoints."""

from __future__ import annotations

import base64
import re
import struct
import zlib
from dataclasses import dataclass
from typing import Any

import httpx

from .exceptions import LLMConfigError


@dataclass(frozen=True)
class LLMCapabilities:
    supports_text: bool
    supports_vision: bool

    @property
    def config_type(self) -> str:
        return "vision" if self.supports_vision else "text"


_VISION_PROBE_BANDS: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("blue", (37, 99, 235)),
    ("yellow", (234, 179, 8)),
    ("red", (220, 38, 38)),
)
_VISION_COLOR_TOKEN_PATTERN = re.compile(
    r"\b(?:red|blue|green|yellow)\b|红色?|蓝色?|绿色?|黄色?"
)
_VISION_COLOR_TOKEN_NAMES = {
    "red": "red",
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "红": "red",
    "红色": "red",
    "蓝": "blue",
    "蓝色": "blue",
    "绿": "green",
    "绿色": "green",
    "黄": "yellow",
    "黄色": "yellow",
}


def _probe_png_data_url() -> str:
    """Create a small three-band color chart without an imaging dependency."""
    width, height = 96, 48
    band_width = width // len(_VISION_PROBE_BANDS)
    raw = b"".join(
        b"\x00"
        + b"".join(bytes(rgb) * band_width for _, rgb in _VISION_PROBE_BANDS)
        for _ in range(height)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        payload = kind + data
        return (
            struct.pack(">I", len(data))
            + payload
            + struct.pack(">I", zlib.crc32(payload))
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


def _response_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        content_text = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
        if content_text:
            return content_text
    reasoning_content = message.get("reasoning_content")
    return reasoning_content if isinstance(reasoning_content, str) else ""


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("detail") or error)[:500]
        return str(payload.get("detail") or payload.get("message") or payload)[:500]
    return str(payload)[:500]


def _is_image_rejection(text: str) -> bool:
    normalized = text.lower()
    markers = (
        "image_url is not supported",
        "image_url content is not supported",
        "image_url type is not supported",
        "image input is not supported",
        "vision input is not supported",
        "does not support vision",
        "does not support image",
        "unknown variant `image_url`",
        "invalid content type",
        "不支持图像",
        "不支持图片",
        "无法查看图片",
        "无法查看图像",
        "无法查看或分析图片",
        "不能查看图片",
        "看不到图片",
        "看不见图片",
        "无法读取图片",
        "无法分析图片",
        "image is not available",
        "cannot see the image",
        "can't see the image",
        "unable to see the image",
        "cannot view the image",
        "can't view the image",
        "无法识别图片",
        "不具备视觉",
    )
    return any(marker in normalized for marker in markers)


def _is_max_tokens_rejection(text: str) -> bool:
    normalized = text.lower()
    if "max_tokens" not in normalized and "max_completion_tokens" not in normalized:
        return False
    markers = (
        "unsupported",
        "not support",
        "not allowed",
        "unknown",
        "unrecognized",
        "invalid",
        "不支持",
        "不允许",
        "无效",
    )
    return any(marker in normalized for marker in markers)


def _is_thinking_rejection(text: str) -> bool:
    normalized = text.lower()
    if (
        "thinking" not in normalized
        and "reasoning" not in normalized
        and "思考" not in normalized
    ):
        return False
    markers = (
        "unsupported",
        "not support",
        "not allowed",
        "unknown",
        "unrecognized",
        "invalid",
        "不支持",
        "不允许",
        "无效",
    )
    return any(marker in normalized for marker in markers)


def _normalized_model_name(model_name: str) -> str:
    normalized = model_name.strip().lower()
    return normalized.rsplit("/", 1)[-1]


def _uses_completion_tokens(model_name: str) -> bool:
    return _normalized_model_name(model_name).startswith("gpt-5")


def _uses_disabled_thinking(model_name: str) -> bool:
    normalized = _normalized_model_name(model_name)
    return normalized.startswith(("kimi-k2.5", "kimi-k2.6"))


def _build_vision_probe_payload(
    *,
    model_name: str,
    image_type: str = "image_url",
    image_first: bool = True,
    image_shorthand: bool = False,
    token_field: str | None = None,
    include_model_thinking: bool = True,
) -> dict[str, Any]:
    token_field = token_field or (
        "max_completion_tokens" if _uses_completion_tokens(model_name) else "max_tokens"
    )
    image_url = _probe_png_data_url()
    image_part = (
        {"type": "input_image", "image_url": image_url}
        if image_type == "input_image"
        else (
            {"type": "image_url", "image_url": image_url}
            if image_shorthand
            else {"type": "image_url", "image_url": {"url": image_url}}
        )
    )
    text_part = {
        "type": "text",
        "text": (
            "请观察附带的测试图像，按从左到右识别三个色块。"
            "仅输出三个英文颜色名称，用逗号分隔，不要解释。"
        ),
    }
    content = [image_part, text_part] if image_first else [text_part, image_part]
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        token_field: 32,
        "stream": False,
    }
    if include_model_thinking and _uses_disabled_thinking(model_name):
        payload["thinking"] = {"type": "disabled"}
    return payload


def _vision_response_text(response: httpx.Response) -> str:
    try:
        return _response_text(response.json())
    except ValueError as exc:
        raise LLMConfigError("视觉能力检测失败：响应格式无效") from exc


def _extract_vision_probe_colors(text: str) -> tuple[str, ...]:
    return tuple(
        _VISION_COLOR_TOKEN_NAMES[token]
        for token in _VISION_COLOR_TOKEN_PATTERN.findall(text.lower())
    )


def _matches_vision_probe(text: str) -> bool:
    """Require the model to identify the actual image, not just accept it."""
    if not text.strip() or _is_image_rejection(text):
        return False
    expected = tuple(color for color, _ in _VISION_PROBE_BANDS)
    actual = _extract_vision_probe_colors(text)
    return len(actual) >= len(expected) and actual[-len(expected) :] == expected


async def probe_api_base_url(
    *,
    api_base_url: str,
    api_key: str,
    timeout_seconds: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Verify that an OpenAI-compatible API base URL and credential work."""
    url = api_base_url.rstrip("/") + "/models"
    timeout = httpx.Timeout(min(timeout_seconds, 30))
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        except httpx.HTTPError as exc:
            raise LLMConfigError(f"URL 连通性测试失败：{type(exc).__name__}") from exc

    if response.is_success:
        return
    if response.status_code in {401, 403}:
        raise LLMConfigError("URL 可访问，但认证失败，请检查 API 密钥")
    if response.status_code == 404:
        raise LLMConfigError(
            "未找到模型列表接口，请检查 API 基础 URL 是否包含正确版本路径"
        )
    raise LLMConfigError(f"URL 连通性测试失败（HTTP {response.status_code}）")


async def detect_model_capabilities(
    *,
    api_base_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMCapabilities:
    url = api_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(min(timeout_seconds, 60))
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        try:
            text_token_field = (
                "max_completion_tokens"
                if _uses_completion_tokens(model_name)
                else "max_tokens"
            )
            text_response = await client.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "只回复 OK"}],
                    text_token_field: 16,
                    "stream": False,
                },
            )
        except httpx.HTTPError as exc:
            raise LLMConfigError(f"模型连接失败：{type(exc).__name__}") from exc
        if text_response.status_code >= 400:
            raise LLMConfigError(
                f"文本能力检测失败（{text_response.status_code}）："
                f"{_error_detail(text_response)}"
            )

        try:
            image_type = "image_url"
            image_first = True
            image_shorthand = False
            token_field = (
                "max_completion_tokens"
                if _uses_completion_tokens(model_name)
                else "max_tokens"
            )
            include_model_thinking = True

            async def post_vision_probe(
                *, include_thinking: bool
            ) -> httpx.Response:
                payload = _build_vision_probe_payload(
                    model_name=model_name,
                    image_type=image_type,
                    image_first=image_first,
                    image_shorthand=image_shorthand,
                    token_field=token_field,
                    include_model_thinking=include_thinking,
                )
                return await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            vision_response = await post_vision_probe(
                include_thinking=include_model_thinking
            )
            if vision_response.status_code in {400, 422} and _is_max_tokens_rejection(
                _error_detail(vision_response)
            ):
                token_field = (
                    "max_tokens"
                    if token_field == "max_completion_tokens"
                    else "max_completion_tokens"
                )
                vision_response = await post_vision_probe(
                    include_thinking=include_model_thinking
                )
            if vision_response.status_code in {400, 422} and _is_thinking_rejection(
                _error_detail(vision_response)
            ):
                include_model_thinking = False
                vision_response = await post_vision_probe(
                    include_thinking=include_model_thinking
                )
            if vision_response.status_code in {400, 415, 422} and _is_image_rejection(
                _error_detail(vision_response)
            ):
                if image_type == "image_url" and not image_shorthand:
                    image_shorthand = True
                    vision_response = await post_vision_probe(
                        include_thinking=include_model_thinking
                    )
                if (
                    vision_response.status_code in {400, 415, 422}
                    and _is_image_rejection(_error_detail(vision_response))
                ):
                    image_type = "input_image"
                    image_shorthand = False
                    vision_response = await post_vision_probe(
                        include_thinking=include_model_thinking
                    )

            if vision_response.status_code < 400:
                vision_content = _vision_response_text(vision_response)
                if _matches_vision_probe(vision_content):
                    return LLMCapabilities(supports_text=True, supports_vision=True)

                # Some OpenAI-compatible adapters require image parts before
                # text parts (Kimi is one example). Retry one alternate order
                # when the response did not explicitly reject image input.
                if not _is_image_rejection(vision_content):
                    image_first = not image_first
                    alternate_response = await post_vision_probe(
                        include_thinking=include_model_thinking
                    )
                    if alternate_response.status_code < 400 and _matches_vision_probe(
                        _vision_response_text(alternate_response)
                    ):
                        return LLMCapabilities(
                            supports_text=True,
                            supports_vision=True,
                        )
            elif vision_response.status_code in {400, 422} and not _is_image_rejection(
                _error_detail(vision_response)
            ):
                # A few gateways report an invalid content ordering as a
                # generic validation error rather than an image error.
                image_first = not image_first
                alternate_response = await post_vision_probe(
                    include_thinking=include_model_thinking
                )
                if alternate_response.status_code < 400:
                    vision_response = alternate_response
        except httpx.HTTPError as exc:
            raise LLMConfigError(f"视觉能力检测失败：{type(exc).__name__}") from exc
    if vision_response.status_code >= 400:
        detail = _error_detail(vision_response)
        if _is_image_rejection(detail) or vision_response.status_code in {
            400,
            415,
            422,
        }:
            return LLMCapabilities(supports_text=True, supports_vision=False)
        raise LLMConfigError(
            f"视觉能力检测失败（{vision_response.status_code}）：{detail}"
        )

    content = _vision_response_text(vision_response)
    return LLMCapabilities(
        supports_text=True,
        supports_vision=_matches_vision_probe(content),
    )
