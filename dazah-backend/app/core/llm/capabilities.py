"""Runtime capability detection for OpenAI-compatible LLM endpoints."""

from __future__ import annotations

import asyncio
import base64
import re
import secrets
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


_VISION_PROBE_PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("blue", (37, 99, 235)),
    ("yellow", (234, 179, 8)),
    ("red", (220, 38, 38)),
    ("green", (22, 163, 74)),
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


def _probe_png_data_url(bands: tuple[str, ...]) -> str:
    """Create a random six-band color chart without an imaging dependency."""
    width, height = 384, 192
    band_width = width // len(bands)
    raw = b"".join(
        b"\x00"
        + b"".join(
            (bytes(dict(_VISION_PROBE_PALETTE)[color]) * (band_width - 2) + b"\xff" * 6)
            for color in bands
        )
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
    return ""


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


def _build_vision_probe_payload(
    *,
    model_name: str,
    bands: tuple[str, ...],
    image_first: bool = True,
) -> dict[str, Any]:
    image_part = {"type": "image_url", "image_url": {"url": _probe_png_data_url(bands)}}
    text_part = {
        "type": "text",
        "text": (
            "Identify the six colored rectangles in the attached image from left "
            "to right, ignoring white separators. Reply with exactly six English "
            "color names separated by commas. "
            "If the image is unavailable, say UNAVAILABLE. Do not guess."
        ),
    }
    return {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [image_part, text_part]
                if image_first
                else [text_part, image_part],
            }
        ],
        "stream": False,
    }


def _matches_vision_probe(text: str, expected: tuple[str, ...]) -> bool:
    actual = tuple(
        _VISION_COLOR_TOKEN_NAMES[token]
        for token in _VISION_COLOR_TOKEN_PATTERN.findall(text.lower())
    )
    return not _is_image_rejection(text) and actual == expected


@dataclass
class _ProbeSession:
    client: httpx.AsyncClient
    url: str
    headers: dict[str, str]
    token_field: str = "max_tokens"

    async def post(self, payload: dict[str, Any]) -> httpx.Response:
        """Negotiate only from server feedback, with bounded output and retries."""
        budget = 2048
        switched = False
        for _ in range(4):
            response = await self.client.post(
                self.url,
                headers=self.headers,
                json={**payload, self.token_field: budget},
            )
            if (
                response.status_code in {400, 422}
                and _is_max_tokens_rejection(_error_detail(response))
                and not switched
            ):
                self.token_field = (
                    "max_completion_tokens"
                    if self.token_field == "max_tokens"
                    else "max_tokens"
                )
                switched = True
                continue
            if response.is_success:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise LLMConfigError("能力检测失败：响应格式无效") from exc
                choices = data.get("choices") if isinstance(data, dict) else None
                if (
                    not isinstance(choices, list)
                    or not choices
                    or not isinstance(choices[0], dict)
                ):
                    raise LLMConfigError("能力检测失败：响应格式无效")
                if choices[0].get("finish_reason") == "length":
                    if budget < 8192:
                        budget = 8192
                        continue
                    raise LLMConfigError("能力检测未完成：模型输出被截断，请重试")
                if not _response_text(data).strip():
                    raise LLMConfigError("能力检测未完成：未收到有效最终答案，请重试")
            return response
        raise LLMConfigError("能力检测未完成：请求参数协商失败")


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


async def probe_model_connection(
    *,
    api_base_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Check that the configured model returns a text answer in one request."""
    deadline = max(1, min(timeout_seconds, 30))
    try:
        async with (
            asyncio.timeout(deadline),
            httpx.AsyncClient(
                timeout=httpx.Timeout(deadline), transport=transport
            ) as client,
        ):
            session = _ProbeSession(
                client=client,
                url=api_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response = await session.post(
                {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Reply only OK"}],
                    "stream": False,
                }
            )
            if not response.is_success:
                raise LLMConfigError(
                    f"模型连通性测试失败（HTTP {response.status_code}）"
                )
    except (httpx.HTTPError, TimeoutError) as exc:
        raise LLMConfigError(
            f"模型连通性测试未完成：{type(exc).__name__}，请重试"
        ) from exc


async def detect_model_capabilities(
    *,
    api_base_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMCapabilities:
    # The deadline covers all probes/retries, not just each network operation.
    deadline = max(1, min(timeout_seconds, 180))
    try:
        async with (
            asyncio.timeout(deadline),
            httpx.AsyncClient(
                timeout=httpx.Timeout(deadline),
                transport=transport,
            ) as client,
        ):
            session = _ProbeSession(
                client=client,
                url=api_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            text_response = await session.post(
                {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Reply only OK"}],
                    "stream": False,
                }
            )
            if not text_response.is_success:
                raise LLMConfigError(
                    f"文本能力检测失败（HTTP {text_response.status_code}）"
                )

            # The two independent image challenges can run together after text
            # connectivity is confirmed, avoiding a second model round trip.
            palette = tuple(color for color, _ in _VISION_PROBE_PALETTE)
            first_bands = tuple(secrets.choice(palette) for _ in range(6))
            second_bands = tuple(secrets.choice(palette) for _ in range(6))
            if second_bands == first_bands:
                second_bands = (
                    palette[(palette.index(second_bands[0]) + 1) % 4],
                    *second_bands[1:],
                )

            async def verify_image(bands: tuple[str, ...]) -> bool:
                vision_session = _ProbeSession(
                    client=client,
                    url=session.url,
                    headers=session.headers,
                    token_field=session.token_field,
                )
                for attempt in range(2):
                    response = await vision_session.post(
                        _build_vision_probe_payload(
                            model_name=model_name,
                            bands=bands,
                            image_first=attempt == 0,
                        )
                    )
                    if not response.is_success:
                        detail = _error_detail(response)
                        # Schema/transport errors cannot establish model incapability.
                        explicit_rejection = any(
                            marker in detail.lower()
                            for marker in (
                                "image input is not supported",
                                "vision input is not supported",
                                "不支持图像输入",
                                "不支持图片输入",
                            )
                        )
                        explicit_rejection = explicit_rejection or bool(
                            re.search(
                                r"does not support (?:vision|images?)"
                                r"(?: input)?(?:[.,; ]|$)",
                                detail.lower(),
                            )
                        )
                        if (
                            response.status_code in {400, 415, 422}
                            and explicit_rejection
                        ):
                            return False
                        raise LLMConfigError(
                            f"视觉能力检测未完成（HTTP {response.status_code}）："
                            "请检查接口及图片输入兼容性后重试"
                        )
                    if _matches_vision_probe(_response_text(response.json()), bands):
                        return True
                    if attempt == 1:
                        raise LLMConfigError(
                            "视觉能力检测未完成：未能验证图片内容，保留原有能力配置"
                        )
                raise LLMConfigError("视觉能力检测未完成：请重试")

            results = await asyncio.gather(
                verify_image(first_bands),
                verify_image(second_bands),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            if results[0] != results[1]:
                raise LLMConfigError("能力检测结果不一致，请重试")
            return LLMCapabilities(True, bool(results[0]))
    except (httpx.HTTPError, TimeoutError) as exc:
        raise LLMConfigError(f"能力检测未完成：{type(exc).__name__}，请重试") from exc
