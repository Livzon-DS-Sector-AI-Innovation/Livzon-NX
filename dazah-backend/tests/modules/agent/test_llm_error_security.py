"""Provider error bodies must never cross the HTTP/SSE boundary."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.agent import api, llm_proxy

SENSITIVE_BODY = "synthetic-api-key private-prompt /internal/database"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("retry", [False, True])
async def test_upstream_error_is_sanitized_before_response_starts(
    monkeypatch, stream, retry
):
    @asynccontextmanager
    async def capacity():
        yield

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, text=SENSITIVE_BODY)

    config = SimpleNamespace(
        api_base_url="https://provider.example/v1",
        api_key="synthetic",
        model_name="kimi-k2.6",
        temperature=0.1,
        timeout_seconds=10,
    )

    async def get_config(_kind):
        return config

    client_class = httpx.AsyncClient
    monkeypatch.setattr(llm_proxy, "get_config", get_config)
    monkeypatch.setattr(llm_proxy, "hold_capacity", capacity)
    monkeypatch.setattr(
        llm_proxy,
        "provider_client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(
        llm_proxy, "should_retry_without_auto_thinking", lambda *args: retry
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[api.get_settings] = lambda: SimpleNamespace(
        AGENT_LLM_PROXY_TOKEN="synthetic"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agent/llm/chat/completions",
            headers={"Authorization": "Bearer synthetic"},
            json={"messages": [{"role": "user", "content": "test"}], "stream": stream},
        )
    assert response.status_code == 502
    assert SENSITIVE_BODY not in response.text
    assert "private-prompt" not in response.text
    assert len(calls) == (2 if retry else 1)


async def test_sse_error_envelope_is_replaced_without_leaking_provider_text(
    monkeypatch,
):
    @asynccontextmanager
    async def capacity():
        yield

    config = SimpleNamespace(
        api_base_url="https://provider.example/v1",
        api_key="synthetic",
        model_name="test-model",
        temperature=0.1,
        timeout_seconds=10,
    )

    async def get_config(_kind):
        return config

    client_class = httpx.AsyncClient

    def handler(request):
        return httpx.Response(
            200,
            text='data: {"error":{"message":"' + SENSITIVE_BODY + '"}}\n\n',
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(llm_proxy, "get_config", get_config)
    monkeypatch.setattr(llm_proxy, "hold_capacity", capacity)
    monkeypatch.setattr(
        llm_proxy,
        "provider_client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler)),
    )
    response = await llm_proxy.forward_chat_completion({"messages": [], "stream": True})
    chunks = [chunk async for chunk in response.body_iterator]
    payload = b"".join(chunks).decode()
    assert "private-prompt" not in payload
    assert '"error"' in payload


@pytest.fixture
def stream_environment(monkeypatch):
    state = {"admitted": 0, "released": 0}
    clients = []

    @asynccontextmanager
    async def capacity():
        state["admitted"] += 1
        try:
            yield
        finally:
            state["admitted"] -= 1
            state["released"] += 1

    async def config(_kind):
        return SimpleNamespace(
            api_base_url="https://provider.example/v1",
            api_key="synthetic",
            model_name="test",
            temperature=0.1,
            timeout_seconds=10,
        )

    def bind(handler):
        def factory(**kwargs):
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            clients.append(client)
            return client

        monkeypatch.setattr(llm_proxy, "provider_client", factory)

    monkeypatch.setattr(llm_proxy, "get_config", config)
    monkeypatch.setattr(llm_proxy, "hold_capacity", capacity)
    return state, clients, bind


async def test_stream_yields_small_fragmented_frames_without_buffering_until_end(
    stream_environment,
):
    state, clients, bind = stream_environment
    allow_second = asyncio.Event()
    data = {"choices": [{"delta": {"content": "正常内容"}}]}
    frame = ("data: " + json.dumps(data, ensure_ascii=False) + "\n\n").encode()

    class FragmentedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for byte in frame:
                yield bytes([byte])
            await allow_second.wait()
            yield b"data: [DONE]\n\n"

    bind(lambda request: httpx.Response(200, stream=FragmentedStream()))
    response = await llm_proxy.forward_chat_completion({"messages": [], "stream": True})
    first = await asyncio.wait_for(anext(response.body_iterator), timeout=2)
    assert json.loads(first.decode()[6:]) == data
    allow_second.set()
    rest = [item async for item in response.body_iterator]
    assert rest == [b"data: [DONE]\n\n"]
    assert state == {"admitted": 0, "released": 1}
    assert all(client.is_closed for client in clients)


async def test_disconnect_before_first_byte_releases_open_response_and_capacity(
    stream_environment,
):
    state, clients, bind = stream_environment
    bind(lambda request: httpx.Response(200, text="data: [DONE]\n\n"))
    response = await llm_proxy.forward_chat_completion({"messages": [], "stream": True})

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        raise RuntimeError("synthetic disconnect")

    with pytest.raises(RuntimeError, match="synthetic disconnect"):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert state == {"admitted": 0, "released": 1}
    assert all(client.is_closed for client in clients)


@pytest.mark.parametrize(
    "mode", ["event", "malformed", "oversized", "network_error", "plain", "many_lines"]
)
async def test_stream_failure_variants_remain_generic_and_release_resources(
    stream_environment, mode
):
    state, clients, bind = stream_environment
    content = {
        "event": f"event: error\ndata: {SENSITIVE_BODY}\n\n".encode(),
        "malformed": f"data: {SENSITIVE_BODY}\n\n".encode(),
        "oversized": b"data: " + b"x" * (256 * 1024 + 1),
        "plain": SENSITIVE_BODY.encode(),
        "many_lines": b": ping\n" * 1025,
    }

    class FailedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": ping\n\n"
            raise httpx.ReadError(SENSITIVE_BODY)

    bind(
        lambda request: (
            httpx.Response(200, stream=FailedStream())
            if mode == "network_error"
            else httpx.Response(200, content=content[mode])
        )
    )
    response = await llm_proxy.forward_chat_completion({"messages": [], "stream": True})
    body = b"".join([chunk async for chunk in response.body_iterator]).decode()
    assert "private-prompt" not in body
    assert '"error"' in body
    assert state == {"admitted": 0, "released": 1}
    assert all(client.is_closed for client in clients)


async def test_http_200_error_object_is_not_forwarded_as_success(stream_environment):
    _, _, bind = stream_environment
    bind(
        lambda request: httpx.Response(200, json={"error": {"message": SENSITIVE_BODY}})
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await llm_proxy.forward_chat_completion({"messages": []})
    assert error.value.status_code == 502
    assert SENSITIVE_BODY not in str(error.value.detail)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("status", [429, 504])
async def test_rate_limit_and_timeout_stay_classifiable_without_provider_body(
    stream_environment, stream, status
):
    state, clients, bind = stream_environment
    bind(lambda request: httpx.Response(status, text=SENSITIVE_BODY))
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await llm_proxy.forward_chat_completion({"messages": [], "stream": stream})
    assert error.value.status_code == status
    assert SENSITIVE_BODY not in str(error.value.detail)
    assert state == {"admitted": 0, "released": 1}
    assert all(client.is_closed for client in clients)


async def test_stream_success_through_http_route_releases_all_resources(
    stream_environment,
):
    state, clients, bind = stream_environment
    data = {"choices": [{"delta": {"content": "正常内容"}}]}
    bind(
        lambda request: httpx.Response(
            200, text="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n"
        )
    )
    app = FastAPI()
    app.include_router(api.router, prefix="/agent")
    app.dependency_overrides[api.get_settings] = lambda: SimpleNamespace(
        AGENT_LLM_PROXY_TOKEN="synthetic"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/agent/llm/chat/completions",
            headers={"Authorization": "Bearer synthetic"},
            json={"messages": [{"role": "user", "content": "test"}], "stream": True},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert json.loads(response.text.split("\n\n")[0][6:]) == data
    assert "data: [DONE]" in response.text
    assert state == {"admitted": 0, "released": 1}
    assert all(client.is_closed for client in clients)
