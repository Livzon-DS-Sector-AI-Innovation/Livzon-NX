import base64
import io
import json
from typing import Any

import httpx
import pytest
from PIL import Image

from app.core.llm.capabilities import detect_model_capabilities, probe_api_base_url
from app.core.llm.exceptions import LLMConfigError


def image_answer(payload: dict[str, Any]) -> str:
    content = payload["messages"][0]["content"]
    if not isinstance(content, list):
        return "OK"
    url = next(
        part["image_url"]["url"] for part in content if part["type"] == "image_url"
    )
    image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    colors = {
        (37, 99, 235): "blue",
        (234, 179, 8): "yellow",
        (220, 38, 38): "red",
        (22, 163, 74): "green",
    }
    return ", ".join(colors[image.getpixel((32 + 64 * i, 96))] for i in range(6))


def answer_response(answer: object, **extra: object) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": answer}, **extra}]}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_name", ["unknown-alias", "gpt-5", "kimi-k2.6", "text-only"]
)
async def test_all_names_use_same_visual_challenge(model_name: str) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert "thinking" not in payload
        assert payload["max_tokens"] == 2048
        return answer_response([{"type": "text", "text": image_answer(payload)}])

    result = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name=model_name,
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )
    assert result.supports_text and result.supports_vision
    assert len(requests) == 3
    assert image_answer(requests[1]) != image_answer(requests[2])


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["text", "vision"])
async def test_negotiates_token_parameter_from_error(phase: str) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        vision = isinstance(payload["messages"][0]["content"], list)
        if "max_tokens" in payload and (phase == "text" or vision):
            return httpx.Response(
                400, json={"error": {"message": "unsupported max_tokens"}}
            )
        return answer_response(image_answer(payload))

    result = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="alias",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )
    assert result.supports_vision
    assert len(requests) == 4
    assert "max_completion_tokens" in requests[-1]


@pytest.mark.asyncio
async def test_retries_truncated_final_answer_with_larger_budget() -> None:
    budgets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        budgets.append(payload["max_tokens"])
        if payload["max_tokens"] == 2048:
            return answer_response("", finish_reason="length")
        return answer_response(image_answer(payload))

    result = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="alias",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )
    assert result.supports_vision
    assert budgets == [2048, 8192] * 3


@pytest.mark.asyncio
async def test_alternate_content_order_is_verified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["messages"][0]["content"]
        if isinstance(content, list) and content[0]["type"] == "image_url":
            return answer_response("UNAVAILABLE")
        return answer_response(image_answer(payload))

    result = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="alias",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )
    assert result.supports_vision


@pytest.mark.asyncio
async def test_explicit_input_rejection_identifies_text_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        if isinstance(content, list):
            return httpx.Response(
                400, json={"error": {"message": "does not support images"}}
            )
        return answer_response("OK")

    result = await detect_model_capabilities(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name="alias",
        timeout_seconds=30,
        transport=httpx.MockTransport(handler),
    )
    assert result.supports_text and not result.supports_vision


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "invalid-json",
        "empty",
        "reasoning",
        "length",
        "discard",
        "401",
        "429",
        "500",
        "timeout",
    ],
)
async def test_inconclusive_results_are_not_capability_labels(failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if not isinstance(payload["messages"][0]["content"], list):
            return answer_response("OK")
        if failure == "invalid-json":
            return httpx.Response(200, text="not-json")
        if failure == "empty":
            return httpx.Response(200, json={"choices": []})
        if failure == "reasoning":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": image_answer(payload),
                            }
                        }
                    ]
                },
            )
        if failure == "length":
            return answer_response(image_answer(payload), finish_reason="length")
        if failure == "discard":
            return answer_response("I cannot see the image")
        if failure == "timeout":
            raise httpx.ReadTimeout("private provider data", request=request)
        return httpx.Response(int(failure), text="private provider data")

    with pytest.raises(LLMConfigError) as exc:
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="alias",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )
    assert "private provider data" not in str(exc.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [httpx.Response(401), answer_response("")])
async def test_rejects_broken_text_connection(response: httpx.Response) -> None:
    with pytest.raises(LLMConfigError):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="alias",
            timeout_seconds=30,
            transport=httpx.MockTransport(lambda request: response),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("second_answer", ["cached", "wrong", "schema", "rejection"])
async def test_second_image_must_be_independently_verified(second_answer: str) -> None:
    first_answer = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal first_answer
        payload = json.loads(request.content)
        if not isinstance(payload["messages"][0]["content"], list):
            return answer_response("OK")
        if not first_answer:
            first_answer = image_answer(payload)
            return answer_response(first_answer)
        if second_answer == "schema":
            return httpx.Response(
                400, json={"error": {"message": "does not support image_url schema"}}
            )
        if second_answer == "rejection":
            return httpx.Response(
                400, json={"error": {"message": "does not support images"}}
            )
        return answer_response(first_answer if second_answer == "cached" else "UNKNOWN")

    with pytest.raises(LLMConfigError):
        await detect_model_capabilities(
            api_base_url="https://llm.example/v1",
            api_key="test-key",
            model_name="alias",
            timeout_seconds=30,
            transport=httpx.MockTransport(handler),
        )
