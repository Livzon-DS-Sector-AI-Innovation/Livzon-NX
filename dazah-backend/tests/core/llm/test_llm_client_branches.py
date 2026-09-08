"""LLMClient chat/chat_with_tools/stream 分支行为测试。

覆盖：custom_context 注入、json 提示补写、thinking 透传、超时/限频/错误映射、
tools 响应解析与流式 reasoning/content 分片。不发真实网络请求。
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.llm.client import LLMClient
from app.core.llm.config import LLMConfigData
from app.core.llm.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
)


def _config(**overrides: Any) -> LLMConfigData:
    values: dict[str, Any] = {
        "id": "cfg-1",
        "config_name": "text",
        "config_type": "text",
        "api_base_url": "https://llm.test/v1",
        "api_key": "k",
        "model_name": "test-model",
        "temperature": 0.2,
        "timeout_seconds": 30,
        "is_active": True,
    }
    values.update(overrides)
    return LLMConfigData(**values)


def _resp(body: dict[str, Any], status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.is_error = status >= 400
    resp.text = "provider boom"
    resp.json.return_value = body
    return resp


def _chat_body(resp: Any) -> dict[str, Any]:
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    client.aclose = AsyncMock()
    return client


def _pair(
    monkeypatch: pytest.MonkeyPatch,
    client_obj: LLMClient,
    http_client: Any,
    cfg: LLMConfigData,
) -> None:
    monkeypatch.setattr(
        client_obj,
        '_get_client_and_config',
        AsyncMock(return_value=(http_client, cfg)),
    )


@pytest.fixture
def client() -> LLMClient:
    return LLMClient()


def _patch_config(monkeypatch: pytest.MonkeyPatch, config: LLMConfigData) -> None:
    monkeypatch.setattr(
        "app.core.llm.client.get_config", AsyncMock(return_value=config)
    )


async def test_chat_injects_custom_context_and_json_hint(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_config(monkeypatch, _config(custom_context="工厂 GMP 语境"))
    http_client = _chat_body(_resp({"choices": [{"message": {"content": "ok"}}]}))
    _pair(monkeypatch, client, http_client, _config(custom_context="工厂 GMP 语境"))

    out = await client.chat([{"role": "user", "content": "分析该偏差"}])

    assert out == "ok"
    body = http_client.post.await_args.kwargs["json"]
    assert body["messages"][0] == {"role": "system", "content": "工厂 GMP 语境"}
    # json_object 且原文不含 json 时自动追加提示
    assert "请以 JSON 格式返回结果" in body["messages"][-1]["content"]
    assert body["response_format"] == {"type": "json_object"}


async def test_chat_enable_thinking_from_config(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(enable_thinking=True)
    http_client = _chat_body(_resp({"choices": [{"message": {"content": "t"}}]}))
    _pair(monkeypatch, client, http_client, cfg)

    await client.chat(
        [{"role": "user", "content": "请返回json"}], response_format=None
    )
    assert http_client.post.await_args.kwargs["json"]["thinking"] == {"type": "enabled"}


async def test_chat_explicit_timeout_uses_dedicated_client_and_maps_errors(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Use a deterministic provider timeout instead of relying on a local port.
    class TimeoutClient:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def post(self, *_args: Any, **_kwargs: Any) -> Any:
            raise httpx.ReadTimeout("test timeout")

        async def aclose(self) -> None:
            return None

    _patch_config(monkeypatch, _config())
    monkeypatch.setattr("app.core.llm.client.httpx.AsyncClient", TimeoutClient)
    with pytest.raises(LLMProviderError) as exc:
        await client.chat([{"role": "user", "content": "x"}], timeout=2)
    assert exc.value.status_code == 504


async def test_chat_rate_limit_and_provider_error(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config()
    rl = _chat_body(_resp({}, status=429))
    _pair(monkeypatch, client, rl, cfg)
    with pytest.raises(LLMRateLimitError):
        await client.chat([{"role": "user", "content": "x"}])

    bad = _chat_body(_resp({}, status=500))
    _pair(monkeypatch, client, bad, cfg)
    with pytest.raises(LLMProviderError) as exc:
        await client.chat([{"role": "user", "content": "x"}])
    assert exc.value.status_code == 500


async def test_chat_with_tools_context_and_payload(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(enable_thinking=True)
    resp = _resp(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {"name": "f", "arguments": "{}"},
                            }
                        ],
                    }
                }
            ]
        }
    )
    http_client = _chat_body(resp)
    _pair(monkeypatch, client, http_client, cfg)

    out = await client.chat_with_tools(
        [{"role": "user", "content": "查一下"}],
        tools=[{"type": "function", "function": {"name": "f"}}],
        custom_context="覆盖上下文",
    )
    body = http_client.post.await_args.kwargs["json"]
    assert body["messages"][0] == {"role": "system", "content": "覆盖上下文"}
    assert body["thinking"] == {"type": "enabled"}
    assert body["tools"][0]["function"]["name"] == "f"
    assert out["tool_calls"][0]["id"] == "call-1"


async def test_chat_with_tools_rejects_empty_or_bad_message(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config()
    empty = _chat_body(_resp({"choices": []}))
    _pair(monkeypatch, client, empty, cfg)
    with pytest.raises(LLMProviderError, match="内容为空"):
        await client.chat_with_tools([{"role": "user", "content": "x"}], tools=[])

    badmsg = _chat_body(_resp({"choices": [{"message": "not-dict"}]}))
    _pair(monkeypatch, client, badmsg, cfg)
    with pytest.raises(LLMProviderError, match="格式错误"):
        await client.chat_with_tools([{"role": "user", "content": "x"}], tools=[])


async def test_chat_vision_orders_images_before_prompt_for_kimi(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(config_type="vision", model_name="moonshotai/Kimi-K2.6")
    http_client = _chat_body(
        _resp({"choices": [{"message": {"content": "ok"}}]})
    )
    _pair(monkeypatch, client, http_client, cfg)

    await client.chat_vision("describe this image", ["data:image/png;base64,YQ=="])

    body = http_client.post.await_args.kwargs["json"]
    assert body["messages"][0]["content"] == [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,YQ=="},
        },
        {"type": "text", "text": "describe this image"},
    ]


async def test_chat_vision_uses_completion_tokens_for_gpt5_model(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(config_type="vision", model_name="GPT-5.6-Luna")
    http_client = _chat_body(
        _resp({"choices": [{"message": {"content": "ok"}}]})
    )
    _pair(monkeypatch, client, http_client, cfg)

    await client.chat_vision("describe this image", ["data:image/png;base64,YQ=="])

    body = http_client.post.await_args.kwargs["json"]
    assert body["max_completion_tokens"] == 16384
    assert "max_tokens" not in body


class _StreamResp:
    def __init__(self, lines: list[str], status: int = 200) -> None:
        self._lines = lines
        self.status_code = status
        self.is_error = status >= 400

    async def __aenter__(self) -> "_StreamResp":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def aiter_lines(self) -> Any:
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b"stream boom"


def _stream_client_factory(resp: _StreamResp) -> Any:
    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: Any) -> bool:
            return False

        def stream(self, method: str, url: str, **kwargs: Any) -> _StreamResp:
            captured["body"] = kwargs.get("json")
            return resp

    captured: dict[str, Any] = {}
    return _Client, captured


async def test_stream_chat_yields_reasoning_and_content(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_config(monkeypatch, _config(enable_thinking=True, custom_context="流式语境"))
    lines = [
        "data: " + '{"choices":[{"delta":{"reasoning_content":"思考1"}}]}',
        "data: " + '{"choices":[{"delta":{"content":"答1"}}]}',
        ": keepalive",
        "data: " + '{"choices":[]}',
        "data: not-json",
        "data: [DONE]",
        "data: " + '{"choices":[{"delta":{"content":"忽略"}}]}',
    ]
    cls, captured = _stream_client_factory(_StreamResp(lines))
    monkeypatch.setattr("app.core.llm.client.httpx.AsyncClient", cls)

    chunks = [
        c async for c in client.stream_chat([{"role": "user", "content": "讲"}])
    ]
    assert chunks == [
        {"type": "reasoning", "text": "思考1"},
        {"type": "content", "text": "答1"},
    ]
    assert captured["body"]["thinking"] == {"type": "enabled"}
    assert captured["body"]["messages"][0] == {
        "role": "system",
        "content": "流式语境",
    }
    assert captured["body"]["stream"] is True


async def test_stream_chat_maps_429_and_api_error(
    client: LLMClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_config(monkeypatch, _config())
    cls429, _ = _stream_client_factory(_StreamResp([], status=429))
    monkeypatch.setattr("app.core.llm.client.httpx.AsyncClient", cls429)
    with pytest.raises(LLMRateLimitError):
        [c async for c in client.stream_chat([{"role": "user", "content": "x"}])]

    cls500, _ = _stream_client_factory(_StreamResp([], status=500))
    monkeypatch.setattr("app.core.llm.client.httpx.AsyncClient", cls500)
    with pytest.raises(LLMProviderError, match="Stream API error"):
        [c async for c in client.stream_chat([{"role": "user", "content": "x"}])]
