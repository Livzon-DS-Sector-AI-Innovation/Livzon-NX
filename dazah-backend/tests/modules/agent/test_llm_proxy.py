from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.llm.exceptions import LLMConfigError
from app.modules.agent import api as agent_api
from app.modules.agent import llm_proxy
from app.modules.agent.llm_proxy import (
    body_without_thinking,
    build_provider_body,
    forward_chat_completion,
    payload_has_images,
    should_retry_without_auto_thinking,
)


def _proxy_config(model_name: str = "kimi-k2.6") -> SimpleNamespace:
    return SimpleNamespace(
        api_base_url="https://llm.example/v1",
        api_key="test-key",
        model_name=model_name,
        temperature=0.1,
        timeout_seconds=30,
    )


def test_payload_has_images_detects_multimodal_message() -> None:
    assert payload_has_images(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "识别图片"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,YQ=="},
                        },
                    ],
                }
            ]
        }
    )
    assert not payload_has_images(
        {"messages": [{"role": "user", "content": "普通文本"}]}
    )


def test_build_provider_body_merges_extra_body_for_raw_http_forwarding() -> Any:
    body = build_provider_body(
        {
            "model": "dazah-active-text",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
            "extra_body": {
                "thinking": {"type": "disabled"},
                "provider": {"only": ["moonshot"]},
            },
        },
        model_name="kimi-k2.5",
        temperature=0.1,
    )

    assert body["model"] == "kimi-k2.5"
    assert body["messages"] == [{"role": "user", "content": "hello"}]
    assert body["stream"] is True
    assert body["thinking"] == {"type": "disabled"}
    assert body["provider"] == {"only": ["moonshot"]}
    assert "extra_body" not in body


def test_kimi_image_parts_are_forwarded_before_text_without_mutating_payload() -> Any:
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请分析图片"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,YQ==",
                            "detail": "auto",
                        },
                    },
                    {"type": "text", "text": "保留这段文字"},
                ],
            }
        ]
    }

    body = build_provider_body(
        payload,
        model_name="moonshotai/Kimi-K2.6",
        temperature=0.1,
    )

    assert [part["type"] for part in body["messages"][0]["content"]] == [
        "image_url",
        "text",
        "text",
    ]
    assert payload["messages"][0]["content"][0]["type"] == "text"
    assert payload["messages"][0]["content"][1]["image_url"]["detail"] == "auto"


def test_gpt5_provider_body_uses_completion_tokens_and_default_temperature() -> Any:
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "分析"}],
            "max_tokens": 128,
        },
        model_name="GPT-5.6-Luna",
        temperature=0.1,
    )

    assert body["max_completion_tokens"] == 128
    assert "max_tokens" not in body
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_llm_proxy_route_maps_missing_vision_config_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def missing_config(_config_type: str = "text") -> Any:
        raise LLMConfigError("configuration is missing")

    monkeypatch.setattr(llm_proxy, "get_config", missing_config)
    test_app = FastAPI()
    test_app.include_router(agent_api.router, prefix="/api/v1/agent")
    test_app.dependency_overrides[agent_api.get_settings] = lambda: SimpleNamespace(
        AGENT_LLM_PROXY_TOKEN="test-token"
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/agent/llm/chat/completions",
            headers={"Authorization": "Bearer test-token"},
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请分析图片"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,YQ=="
                                },
                            },
                        ],
                    }
                ]
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "当前激活的模型未配置图片理解能力，请在系统设置中重新检测并激活支持图片的模型。"
    )


@pytest.mark.asyncio
async def test_list_active_text_models_maps_missing_config_to_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def missing_config(_config_type: str = "text") -> Any:
        raise LLMConfigError("configuration is missing")

    monkeypatch.setattr(llm_proxy, "get_config", missing_config)

    with pytest.raises(HTTPException) as exc:
        await llm_proxy.list_active_text_models()

    assert exc.value.status_code == 503
    assert exc.value.detail == (
        "当前未配置可用的 LLM 模型，请在系统设置中配置并激活模型。"
    )


@pytest.mark.asyncio
async def test_llm_proxy_route_forwards_normalized_multimodal_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded: list[dict[str, Any]] = []

    async def configured(_config_type: str = "text") -> SimpleNamespace:
        return _proxy_config()

    class ProviderClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "ProviderClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> httpx.Response:
            forwarded.append(json)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "已识别"}}]},
            )

    monkeypatch.setattr(llm_proxy, "get_config", configured)
    monkeypatch.setattr(llm_proxy.httpx, "AsyncClient", ProviderClient)
    test_app = FastAPI()
    test_app.include_router(agent_api.router, prefix="/api/v1/agent")
    test_app.dependency_overrides[agent_api.get_settings] = lambda: SimpleNamespace(
        AGENT_LLM_PROXY_TOKEN="test-token"
    )

    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/agent/llm/chat/completions",
            headers={"Authorization": "Bearer test-token"},
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "请分析图片"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,YQ==",
                                    "detail": "auto",
                                },
                            },
                        ],
                    }
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "已识别"
    assert forwarded[0]["messages"][0]["content"][0]["type"] == "image_url"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_error", "expected_status"),
    [
        (httpx.TimeoutException("timeout"), 504),
        (httpx.ConnectError("connect"), 502),
    ],
)
async def test_forward_chat_completion_maps_upstream_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
    upstream_error: httpx.HTTPError,
    expected_status: int,
) -> None:
    async def configured(_config_type: str = "text") -> SimpleNamespace:
        return _proxy_config(model_name="text-model")

    class FailingProviderClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FailingProviderClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            raise upstream_error

    monkeypatch.setattr(llm_proxy, "get_config", configured)
    monkeypatch.setattr(llm_proxy.httpx, "AsyncClient", FailingProviderClient)

    with pytest.raises(HTTPException) as exc:
        await forward_chat_completion(
            {"messages": [{"role": "user", "content": "hello"}]}
        )

    assert exc.value.status_code == expected_status


@pytest.mark.asyncio
async def test_forward_chat_completion_maps_invalid_upstream_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def configured(_config_type: str = "text") -> SimpleNamespace:
        return _proxy_config(model_name="text-model")

    class InvalidResponseProviderClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "InvalidResponseProviderClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def post(self, *args: Any, **kwargs: Any) -> httpx.Response:
            return httpx.Response(200, content=b"not-json")

    monkeypatch.setattr(llm_proxy, "get_config", configured)
    monkeypatch.setattr(
        llm_proxy.httpx,
        "AsyncClient",
        InvalidResponseProviderClient,
    )

    with pytest.raises(HTTPException) as exc:
        await forward_chat_completion(
            {"messages": [{"role": "user", "content": "hello"}]}
        )

    assert exc.value.status_code == 502


def test_build_provider_body_disables_kimi_thinking_by_default() -> Any:
    body = build_provider_body(
        {"messages": [{"role": "user", "content": "hello"}]},
        model_name="kimi-k2.5",
        temperature=0.1,
    )

    assert body["thinking"] == {"type": "disabled"}


def test_build_provider_body_preserves_explicit_kimi_thinking() -> Any:
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "extra_body": {"thinking": {"type": "enabled"}},
        },
        model_name="kimi-k2.5",
        temperature=0.1,
    )

    assert body["thinking"] == {"type": "enabled"}
    assert not should_retry_without_auto_thinking(
        {"extra_body": {"thinking": {"type": "enabled"}}},
        body,
        "kimi-k2.5",
    )


def test_build_provider_body_preserves_explicit_reasoning_effort() -> Any:
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "low",
        },
        model_name="deepseek-chat",
        temperature=0.1,
    )

    assert body["reasoning_effort"] == "low"
    assert "thinking" not in body


def test_build_provider_body_does_not_add_kimi_defaults_to_other_models() -> Any:
    body = build_provider_body(
        {"messages": [{"role": "user", "content": "hello"}]},
        model_name="deepseek-chat",
        temperature=0.1,
    )

    assert "thinking" not in body


def test_build_provider_body_omits_config_temperature_when_zero() -> Any:
    body = build_provider_body(
        {"messages": [{"role": "user", "content": "hello"}]},
        model_name="local-model",
        temperature=0,
    )

    assert "temperature" not in body


def test_provider_body_keeps_explicit_temperature_when_config_zero() -> (
    Any
):
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
        },
        model_name="local-model",
        temperature=0,
    )

    assert body["temperature"] == 0.7


def test_build_provider_body_strips_temperature_for_kimi_models() -> Any:
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
        },
        model_name="moonshotai/Kimi-K2.6",
        temperature=0.1,
    )

    assert "temperature" not in body
    assert body["thinking"] == {"type": "disabled"}


def test_provider_body_strips_kimi_reasoning_for_non_thinking() -> (
    Any
):
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "high",
        },
        model_name="kimi-k2.5",
        temperature=0,
    )

    assert "reasoning_effort" not in body
    assert body["thinking"] == {"type": "disabled"}


def test_provider_body_keeps_kimi_reasoning_when_explicit() -> (
    Any
):
    body = build_provider_body(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "reasoning_effort": "high",
            "extra_body": {"thinking": {"type": "enabled"}},
        },
        model_name="kimi-k2.5",
        temperature=0,
    )

    assert body["reasoning_effort"] == "high"
    assert body["thinking"] == {"type": "enabled"}


def test_should_retry_without_auto_thinking_for_auto_kimi_default() -> Any:
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    body = build_provider_body(payload, model_name="kimi-k2.5", temperature=0.1)

    assert should_retry_without_auto_thinking(payload, body, "kimi-k2.5")
    assert "thinking" not in body_without_thinking(body)
