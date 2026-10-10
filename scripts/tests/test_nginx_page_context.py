"""Exercise both production proxy templates against an isolated echo upstream."""

import http.client
import json
import shutil
import ssl
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "nginx:1.27-alpine"
PAGE_PATH = "X-Dazah-Page-Path"
PAGE_KEY = "X-Dazah-Page-Key"
TARGET_PATH = "/warehouse/materials/inbound-ledger"
TARGET_KEY = "warehouse:materials:inbound-ledger"


def _run(*args: str, timeout: int = 30) -> str:
    return subprocess.check_output(
        args, stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=timeout
    ).strip()


def _openssl() -> str | None:
    binary = shutil.which("openssl")
    if binary:
        return binary
    # Git for Windows ships OpenSSL without necessarily adding it to PATH.
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parents[1] / "usr/bin/openssl.exe"
        if candidate.is_file():
            return str(candidate)
    return None


class Proxy:
    def __init__(self, scheme: str, port: int) -> None:
        self.scheme = scheme
        self.port = port

    def request(self, headers: dict[str, str], path: str = "/api/v1/probe") -> dict[str, str]:
        if self.scheme == "https":
            # Only the generated, short-lived certificate in this isolated fixture.
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            connection = http.client.HTTPSConnection(
                "127.0.0.1", self.port, context=context, timeout=5
            )
        else:
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", path, headers={"Host": "example.test", **headers})
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            assert response.status == 200, (response.status, body)
            return json.loads(body)
        finally:
            connection.close()


@pytest.fixture(scope="module", params=["http", "https"])
def proxy(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Proxy]:
    openssl = _openssl()
    if shutil.which("docker") is None or openssl is None:
        pytest.skip("Proxy integration requires Docker and OpenSSL")
    try:
        _run("docker", "info", "--format", "{{.OSType}}", timeout=10)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon is unavailable")
    scheme = request.param
    temporary = tmp_path_factory.mktemp(f"nginx-page-context-{scheme}")
    certificates = temporary / "certificates"
    certificates.mkdir()
    _run(
        openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
        "-subj", "/CN=example.test", "-keyout", str(certificates / "privkey.pem"),
        "-out", str(certificates / "fullchain.pem"),
    )
    template = "nginx.http.conf.template" if scheme == "http" else "nginx.default.conf.template"
    config = (ROOT / "deploy" / template).read_text(encoding="utf-8")
    config = config.replace("__PUBLIC_HOST__", "example.test")
    config = config.replace("server app:8000 resolve;", "server 127.0.0.1:8081;")
    config = config.replace("server frontend:3000 resolve;", "server 127.0.0.1:8081;")
    config += '''
server {
    listen 8081;
    location / {
        default_type application/json;
        return 200 '{"path":"$http_x_dazah_page_path","key":"$http_x_dazah_page_key"}';
    }
}
'''
    configuration = temporary / "default.conf"
    configuration.write_text(config, encoding="utf-8")
    image = subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, timeout=10
    )
    if image.returncode:
        _run("docker", "pull", IMAGE, timeout=120)
    name = f"dazah-page-context-{uuid4().hex}"
    port = "80" if scheme == "http" else "443"
    try:
        _run(
            "docker", "run", "--detach", "--rm", "--name", name,
            "--publish", f"127.0.0.1::{port}",
            "--mount", f"type=bind,source={configuration},target=/etc/nginx/conf.d/default.conf,readonly",
            "--mount", f"type=bind,source={ROOT / 'deploy/nginx-maintenance.conf'},target=/etc/nginx/dazah-maintenance.conf,readonly",
            "--mount", f"type=bind,source={certificates},target=/etc/letsencrypt/live/example.test,readonly",
            IMAGE,
        )
        _run("docker", "exec", name, "nginx", "-t")
        address = _run("docker", "port", name, f"{port}/tcp")
        server = Proxy(scheme, int(address.rsplit(":", 1)[1]))
        deadline = time.monotonic() + 10
        while True:
            try:
                assert server.request({}) == {"path": "", "key": ""}
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        yield server
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name], capture_output=True, timeout=15
        )


@pytest.mark.parametrize(
    ("case", "expected_path", "expected_key"),
    [
        ("explicit_only", TARGET_PATH, ""),
        ("explicit_over_referer", TARGET_PATH, ""),
        ("explicit_with_foreign_referer", TARGET_PATH, ""),
        ("empty_explicit", "/warehouse/materials/dashboard", ""),
        ("same_origin", "/warehouse/materials/dashboard", ""),
        ("same_origin_root", "/", ""),
        ("same_origin_host_case", "/warehouse/materials/dashboard", ""),
        ("same_origin_port", "/warehouse/materials/dashboard", ""),
        ("missing", "", ""),
        ("invalid_referer", "", ""),
        ("foreign_host", "", ""),
        ("host_prefix", "", ""),
        ("foreign_scheme", "", ""),
        ("foreign_port", "", ""),
        ("explicit_key_only", "", TARGET_KEY),
        ("explicit_key_over_referer", "/warehouse/materials/dashboard", TARGET_KEY),
    ],
)
def test_page_context_headers(proxy: Proxy, case: str, expected_path: str, expected_key: str) -> None:
    referer = f"{proxy.scheme}://example.test/warehouse/materials/dashboard?days=30#pending"
    headers = {
        "explicit_only": {PAGE_PATH: TARGET_PATH},
        "explicit_over_referer": {PAGE_PATH: TARGET_PATH, "Referer": referer},
        "explicit_with_foreign_referer": {PAGE_PATH: TARGET_PATH, "Referer": "https://foreign.test/other"},
        "empty_explicit": {PAGE_PATH: "", "Referer": referer},
        "same_origin": {"Referer": referer},
        "same_origin_root": {"Referer": f"{proxy.scheme}://example.test"},
        "same_origin_host_case": {"Referer": referer.replace("example.test", "EXAMPLE.TEST")},
        "same_origin_port": {"Host": "example.test:8443", "Referer": referer.replace("example.test", "example.test:8443")},
        "missing": {},
        "invalid_referer": {"Referer": "not-a-url"},
        "foreign_host": {"Referer": referer.replace("example.test", "foreign.test")},
        "host_prefix": {"Referer": referer.replace("example.test", "example.test.evil.test")},
        "foreign_scheme": {"Referer": referer.replace(proxy.scheme, "https" if proxy.scheme == "http" else "http", 1)},
        "foreign_port": {"Referer": referer.replace("example.test", "example.test:8443")},
        "explicit_key_only": {PAGE_KEY: TARGET_KEY},
        "explicit_key_over_referer": {PAGE_KEY: TARGET_KEY, "Referer": referer},
    }[case]
    assert proxy.request(headers) == {"path": expected_path, "key": expected_key}


@pytest.mark.parametrize("path", ["/uploads/probe", "/mcp/probe", "/health"])
def test_backend_locations_inherit_context(proxy: Proxy, path: str) -> None:
    assert proxy.request({PAGE_PATH: TARGET_PATH, PAGE_KEY: TARGET_KEY}, path) == {
        "path": TARGET_PATH, "key": TARGET_KEY,
    }


def test_frontend_location_keeps_its_own_header_collection(proxy: Proxy) -> None:
    referer = f"{proxy.scheme}://example.test/warehouse/materials/dashboard"
    assert proxy.request({"Referer": referer}, "/login") == {"path": "", "key": ""}
