"""Provider egress policy with DNS pinning, independent of administrator input."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from app.core.config import get_settings

from .exceptions import LLMConfigError


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    port = (
        parsed.port
        if parsed.port is not None
        else (443 if parsed.scheme == "https" else 80)
    )
    return f"{parsed.scheme}://{host}:{port}"


def _private_allowed(url: str) -> bool:
    entries = get_settings().LLM_ALLOWED_PRIVATE_API_ORIGINS.split(",")
    try:
        return _origin(url) in {
            _origin(item.strip()) for item in entries if item.strip()
        }
    except ValueError:
        raise LLMConfigError("Invalid private provider origin policy") from None


def _check_address(address: str, *, allow_private: bool) -> None:
    try:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
    except ValueError:
        raise LLMConfigError("Provider address is invalid") from None
    if (
        ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.is_reserved and not (allow_private and ip.is_loopback))
        or (
            not ip.is_global
            and not (allow_private and (ip.is_private or ip.is_loopback))
        )
    ):
        raise LLMConfigError("Provider target is not permitted by the egress policy")


def validate_provider_url(url: str) -> str:
    """Reject ambiguous URLs and private literals before attaching credentials."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "\\" in url
            or any(ord(char) <= 32 for char in url)
        ):
            raise ValueError()
        if parsed.port is not None and parsed.port < 1:
            raise ValueError()
        allowed = _private_allowed(url)
        if parsed.scheme != "https" and not allowed:
            raise ValueError()
        hostname = parsed.hostname.rstrip(".").lower()
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            if (
                hostname == "localhost" or hostname.endswith(".localhost")
            ) and not allowed:
                raise ValueError()
        else:
            _check_address(hostname, allow_private=allowed)
    except ValueError:
        raise LLMConfigError("Provider URL is invalid or not permitted") from None
    return url.rstrip("/")


class ProviderTransport(httpx.AsyncBaseTransport):
    """Validate each connection and connect to the checked IP, preventing rebinding."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._inner = inner or httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        validate_provider_url(str(request.url))
        host = request.url.host
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        try:
            results = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    host, port, type=socket.SOCK_STREAM
                ),
                timeout=5,
            )
        except (OSError, TimeoutError) as exc:
            raise LLMConfigError("Provider DNS resolution failed") from exc
        addresses = list(dict.fromkeys(str(item[4][0]) for item in results))
        if not addresses:
            raise LLMConfigError("Provider DNS returned no addresses")
        for address in addresses:
            _check_address(address, allow_private=_private_allowed(str(request.url)))
        headers = httpx.Headers(request.headers)
        headers["Host"] = request.url.netloc.decode("ascii")
        pinned = httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=addresses[0]),
            headers=headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        return await self._inner.handle_async_request(pinned)

    async def aclose(self) -> None:
        await self._inner.aclose()


def provider_client(
    *,
    base_url: str = "",
    headers: dict[str, str] | None = None,
    timeout: float | httpx.Timeout = 120,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """The injected transport is reserved for deterministic, network-free tests."""
    if base_url:
        validate_provider_url(base_url)
    return httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        transport=transport or ProviderTransport(),
        trust_env=False,
        follow_redirects=False,
    )
