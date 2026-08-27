"""Runtime capability detection for OpenAI-compatible LLM endpoints."""

from __future__ import annotations

import base64
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


def _probe_png_data_url() -> str:
    """Create a small white PNG without adding an imaging dependency."""
    width = height = 32
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))

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
    return content if isinstance(content, str) else ""


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
        "image input is not supported",
        "vision input is not supported",
        "does not support vision",
        "does not support image",
        "unknown variant `image_url`",
        "invalid content type",
        "不支持图像",
        "不支持图片",
        "无法查看图片",
        "无法查看或分析图片",
        "不能查看图片",
        "无法识别图片",
        "不具备视觉",
    )
    return any(marker in normalized for marker in markers)


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
            text_response = await client.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "只回复 OK"}],
                    "max_tokens": 16,
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
            vision_response = await client.post(
                url,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "这是一张纯色测试图片，请只回复你看到的主色。"
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": _probe_png_data_url()},
                                },
                            ],
                        }
                    ],
                    "max_tokens": 32,
                    "stream": False,
                },
            )
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

    content = _response_text(vision_response.json())
    return LLMCapabilities(
        supports_text=True,
        supports_vision=not _is_image_rejection(content),
    )
