import json
from typing import Any

import httpx
import pytest

from app.core.llm.capabilities import detect_model_capabilities, probe_api_base_url
from app.core.llm.exceptions import LLMConfigError


@pytest.mark.asyncio
async def test_detect_model_capabilities_identifies_vision_model() -> None:
    requests: list[dict[Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        answer: str | list[dict[str, str]] = (
            [{"type": "text", "text": "blue, yellow, red"}]
            if isinstance(content, list)
            else "OK"
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="multimodal-model",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_text is True
    assert capabilities.supports_vision is True
    assert capabilities.config_type == "vision"
    assert len(requests) == 2
    assert requests[1]["messages"][0]["content"][0]["type"] == "image_url"


@pytest.mark.asyncio
async def test_detect_model_capabilities_identifies_text_only_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        if isinstance(content, list):
            return httpx.Response(
                400,
                json={"error": {"message": "image input is not supported"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="text-model",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_text is True
    assert capabilities.supports_vision is False
    assert capabilities.config_type == "text"


@pytest.mark.asyncio
async def test_detect_model_capabilities_rejects_silent_image_discard() -> None:
    """A text-only gateway may accept and silently discard list content."""

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        answer = "red, blue, green" if isinstance(content, list) else "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="text-model-behind-compatible-gateway",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_text is True
    assert capabilities.supports_vision is False
    assert capabilities.config_type == "text"


@pytest.mark.asyncio
async def test_detect_model_capabilities_uses_completion_tokens_for_gpt5() -> None:
    requests: list[dict[Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        answer = "blue, yellow, red" if isinstance(content, list) else "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="GPT-5.6-Luna",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is True
    assert len(requests) == 2
    assert requests[0]["max_completion_tokens"] == 16
    assert requests[1]["max_completion_tokens"] == 32
    assert "max_tokens" not in requests[1]


@pytest.mark.asyncio
async def test_detect_model_capabilities_handles_kimi_k26_vision_defaults() -> None:
    requests: list[dict[Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        is_valid_kimi_probe = (
            isinstance(content, list)
            and content[0]["type"] == "image_url"
            and content[1]["type"] == "text"
            and payload.get("thinking") == {"type": "disabled"}
        )
        answer = "蓝色、黄色、红色" if is_valid_kimi_probe else ""
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="kimi-k2.6",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is True
    assert len(requests) == 2
    assert requests[1]["max_tokens"] == 32
    assert requests[1]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_detect_model_capabilities_retries_when_thinking_is_unsupported() -> None:
    requests: list[dict[Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        if isinstance(content, list) and "thinking" in payload:
            return httpx.Response(
                400,
                json={"error": {"message": "thinking is not supported"}},
                request=request,
            )
        answer = "blue, yellow, red" if isinstance(content, list) else "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="kimi-k2.6",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is True
    assert len(requests) == 3
    assert requests[1]["thinking"] == {"type": "disabled"}
    assert "thinking" not in requests[2]


@pytest.mark.asyncio
async def test_detect_model_capabilities_retries_token_parameter() -> None:
    requests: list[dict[Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        if isinstance(content, list) and "max_tokens" in payload:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": (
                            "Unsupported parameter: max_tokens; "
                            "use max_completion_tokens"
                        )
                    }
                },
                request=request,
            )
        answer = "blue, yellow, red" if isinstance(content, list) else "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="compatible-model",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is True
    assert len(requests) == 3
    assert requests[1]["max_tokens"] == 32
    assert requests[2]["max_completion_tokens"] == 32
    assert "max_tokens" not in requests[2]


@pytest.mark.asyncio
async def test_detect_model_capabilities_retries_with_alternate_image_content() -> None:
    requests: list[dict[Any, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        content = payload["messages"][0]["content"]
        if isinstance(content, list):
            image_part = next(
                part for part in content if part.get("type") != "text"
            )
            if image_part["type"] == "image_url":
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": (
                                "image_url content is not supported; use input_image"
                            )
                        }
                    },
                    request=request,
                )
            answer = "blue, yellow, red"
        else:
            answer = "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="GPT-5.6-Luna",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is True
    assert len(requests) == 4
    assert requests[1]["messages"][0]["content"][0]["type"] == "image_url"
    assert requests[2]["messages"][0]["content"][0]["image_url"].startswith(
        "data:image/png;base64,"
    )
    assert requests[3]["messages"][0]["content"][0]["type"] == "input_image"
    assert requests[3]["max_completion_tokens"] == 32


@pytest.mark.asyncio
async def test_detect_model_capabilities_rejects_unverified_image_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        answer = "我无法查看图片" if isinstance(content, list) else "OK"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="text-model",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is False


@pytest.mark.asyncio
async def test_detect_model_capabilities_accepts_reasoning_probe_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        message: dict[str, Any]
        if isinstance(content, list):
            message = {
                "content": "",
                "reasoning_content": "The image colors are blue, yellow, red.",
            }
        else:
            message = {"content": "OK"}
        return httpx.Response(
            200,
            json={"choices": [{"message": message}]},
            request=request,
        )

    capabilities = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="GPT-5.6-Luna",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    assert capabilities.supports_vision is True


@pytest.mark.asyncio
async def test_detect_model_capabilities_rejects_invalid_image_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        if isinstance(content, list):
            return httpx.Response(200, text="not-json", request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
            request=request,
        )

    with pytest.raises(LLMConfigError, match="视觉能力检测失败：响应格式无效"):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="model",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_detect_model_capabilities_rejects_broken_text_connection() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "invalid key"}},
            request=request,
        )

    with pytest.raises(LLMConfigError, match="文本能力检测失败"):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="bad-key",
            model_name="model",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )


@pytest.mark.asyncio
async def test_probe_api_base_url_uses_models_endpoint_and_authentication() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": []}, request=request)

    await probe_api_base_url(
        api_base_url="https://llm.example/v1/",
        api_key="test-key",
        timeout_seconds=120,
        transport=httpx.MockTransport(handler),
    )

    assert requests[0].url == "https://llm.example/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_probe_api_base_url_reports_authentication_failure_safely() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="secret provider response", request=request)

    with pytest.raises(LLMConfigError, match="认证失败") as exc_info:
        await probe_api_base_url(
            api_base_url="https://llm.example/v1",
            api_key="bad-key",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )

    assert "secret provider response" not in str(exc_info.value)
