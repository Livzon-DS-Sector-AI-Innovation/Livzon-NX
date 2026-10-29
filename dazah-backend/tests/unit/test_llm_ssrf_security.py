"""Provider requests must not send credentials to local or metadata services."""

import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.llm import http_security
from app.core.llm.capabilities import probe_api_base_url
from app.core.llm.exceptions import LLMConfigError


@pytest.fixture(autouse=True)
def egress_policy(monkeypatch):
    settings = SimpleNamespace(LLM_ALLOWED_PRIVATE_API_ORIGINS="")
    monkeypatch.setattr(http_security, "get_settings", lambda: settings)
    return settings


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000",
        "https://169.254.169.254",
        "https://[::1]",
        "https://user:password@example.com",
        "http://example.com",
    ],
)
async def test_probe_rejects_unsafe_target_before_http(url):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"data": []})

    with pytest.raises(LLMConfigError):
        await probe_api_base_url(
            api_base_url=url,
            api_key="synthetic",
            timeout_seconds=10,
            transport=httpx.MockTransport(handler),
        )
    assert calls == []


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"]
)
async def test_dns_answer_cannot_reach_private_targets(monkeypatch, address):
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
            ]
        ),
    )
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200)

    async with http_security.provider_client(
        transport=http_security.ProviderTransport(httpx.MockTransport(handler))
    ) as client:
        with pytest.raises(LLMConfigError):
            await client.get(
                "https://provider.example/models",
                headers={"Authorization": "Bearer synthetic"},
            )
    assert calls == []


async def test_connection_is_pinned_to_validated_ip_with_original_tls_hostname(
    monkeypatch,
):
    dns = AsyncMock(
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200)

    async with http_security.provider_client(
        transport=http_security.ProviderTransport(httpx.MockTransport(handler))
    ) as client:
        response = await client.get("https://provider.example/models")
    assert response.status_code == 200
    assert calls[0].url.host == "8.8.8.8"
    assert calls[0].headers["Host"] == "provider.example"
    assert calls[0].extensions["sni_hostname"] == "provider.example"
    assert dns.await_count == 1


async def test_private_provider_requires_exact_operational_origin(egress_policy):
    egress_policy.LLM_ALLOWED_PRIVATE_API_ORIGINS = "http://127.0.0.1:11434"
    assert http_security.validate_provider_url("http://127.0.0.1:11434/v1")
    for url in ["http://127.0.0.1:8000/v1", "https://127.0.0.1:11434/v1"]:
        with pytest.raises(LLMConfigError):
            http_security.validate_provider_url(url)
    egress_policy.LLM_ALLOWED_PRIVATE_API_ORIGINS = "http://169.254.169.254"
    with pytest.raises(LLMConfigError):
        http_security.validate_provider_url("http://169.254.169.254")


async def test_redirect_does_not_send_credentials_to_second_target():
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"location": "http://127.0.0.1/secret"})

    async with http_security.provider_client(
        transport=httpx.MockTransport(handler)
    ) as client:
        response = await client.post(
            "https://provider.example/chat/completions",
            headers={"Authorization": "Bearer synthetic"},
        )
    assert response.status_code == 307
    assert len(calls) == 1


async def test_mixed_public_and_private_dns_answers_fail_before_connect(monkeypatch):
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
            ]
        ),
    )
    send = AsyncMock()
    transport = http_security.ProviderTransport()
    monkeypatch.setattr(transport._inner, "handle_async_request", send)
    async with http_security.provider_client(transport=transport) as client:
        with pytest.raises(LLMConfigError):
            await client.post("https://provider.example/chat/completions")
    send.assert_not_awaited()


async def test_invalid_dns_and_timeout_are_sanitized(monkeypatch):
    for error in (OSError("internal sensitive detail"), TimeoutError("sensitive")):
        monkeypatch.setattr(
            asyncio.get_running_loop(), "getaddrinfo", AsyncMock(side_effect=error)
        )
        async with http_security.provider_client() as client:
            with pytest.raises(LLMConfigError) as raised:
                await client.get("https://provider.example/models")
        assert "sensitive" not in str(raised.value)
