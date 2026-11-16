"""企业安全承诺免登签署链路：token 校验/手写板页/提交签名/签名图/下载。"""

from __future__ import annotations

import base64
import io
import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.safety.api.commitment_sign_public import (
    commitment_sign_public_router,
)


def _png_data_url() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "black").save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _make_token(report_date: str = "2026-11-14", nm: str = "张三") -> str:
    from app.modules.safety.service.commitment_signatures import create_sign_token

    return create_sign_token(
        report_id="rid-1",
        report_date=report_date,
        open_id="ou-s",
        signer_name=nm,
    )


@pytest.fixture
async def sign_client() -> AsyncClient:
    application = FastAPI()
    application.include_router(commitment_sign_public_router, prefix="/api/v1/safety")
    return AsyncClient(transport=ASGITransport(app=application), base_url="http://t")


class TestSignToken:
    def test_roundtrip_and_tamper(self) -> None:
        from app.modules.safety.service.commitment_signatures import verify_token

        token = _make_token()
        payload = verify_token(token)
        assert payload is not None
        assert payload["nm"] == "张三"
        assert payload["act"] == "commitment_sign"

        # 篡改 digest → None
        assert verify_token(token[:-4] + "dead") is None
        # 非 token 字符串 → None
        assert verify_token("not-a-token") is None

    def test_expired_token_rejected(self) -> None:
        import time

        from app.modules.safety.service import commitment_signatures as sig

        payload = {
            "act": "commitment_sign",
            "rid": "r",
            "rdate": "2026-11-14",
            "oid": "ou",
            "nm": "x",
            "exp": int(time.time()) - 10,
        }
        import hashlib
        import hmac as hmac_mod

        body = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        digest = hmac_mod.new(sig._secret(), body.encode(), hashlib.sha256).hexdigest()
        assert sig.verify_token(f"{body}.{digest}") is None

    def test_wrong_act_rejected(self) -> None:
        import hashlib
        import hmac as hmac_mod
        import time

        from app.modules.safety.service import commitment_signatures as sig

        payload = {
            "act": "other_act",
            "exp": int(time.time()) + 600,
        }
        body = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        digest = hmac_mod.new(sig._secret(), body.encode(), hashlib.sha256).hexdigest()
        assert sig.verify_token(f"{body}.{digest}") is None

    def test_build_sign_url_relay_and_local(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import commitment_signatures as sig

        relay = SimpleNamespace(
            SIGN_RELAY_GATEWAY_BASE="https://relay.example.com/",
            FRONTEND_URL="http://fe",
            BACKEND_PUBLIC_URL="http://be",
        )
        monkeypatch.setattr(sig, "get_settings", lambda: relay)
        assert sig.build_sign_url("tk").startswith(
            "https://relay.example.com/api/v1/safety/sign-relay/tk"
        )

        local = SimpleNamespace(
            SIGN_RELAY_GATEWAY_BASE="",
            FRONTEND_URL="http://fe/",
            BACKEND_PUBLIC_URL="http://be",
        )
        monkeypatch.setattr(sig, "get_settings", lambda: local)
        assert sig.build_sign_url("tk") == "http://fe/api/v1/safety/commitment-sign/tk"


class TestSignEndpoints:
    async def test_render_page_and_expired(self, sign_client: AsyncClient) -> None:
        async with sign_client as ac:
            ok = await ac.get(f"/api/v1/safety/commitment-sign/{_make_token()}")
            assert ok.status_code == 200
            assert "commitment-sign" in ok.text or "手写" in ok.text

            gone = await ac.get("/api/v1/safety/commitment-sign/bad.token")
            assert gone.status_code == 410
            assert "链接已失效" in gone.text

    async def test_submit_validation_branches(
        self,
        sign_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from contextlib import asynccontextmanager

        saved: list[dict[str, Any]] = []

        async def _save(
            db: Any,
            *,
            report_date: str,
            signer_open_id: str,
            signer_name: str,
            image_key: str,
            reused: bool,
        ) -> None:
            saved.append(
                {
                    "report_date": report_date,
                    "signer_open_id": signer_open_id,
                    "signer_name": signer_name,
                    "image_key": image_key,
                }
            )

        monkeypatch.setattr(
            "app.modules.safety.api.commitment_sign_public.save_signature", _save
        )

        @asynccontextmanager
        async def _factory():
            yield object()

        monkeypatch.setattr("app.core.database.async_session_factory", _factory)
        monkeypatch.setattr(
            "app.modules.safety.api.commitment_sign_public.store_signature_image",
            lambda png: "commitment-signatures/x.png",
        )

        async with sign_client as ac:
            # 坏 JSON
            bad = await ac.post("/api/v1/safety/commitment-sign", content="not-json")
            assert bad.status_code == 400
            # 失效 token
            gone = await ac.post(
                "/api/v1/safety/commitment-sign",
                json={"token": "bad.token", "image": "data:image/png;base64,AA"},
            )
            assert gone.status_code == 410
            # 非法图片前缀
            fmt = await ac.post(
                "/api/v1/safety/commitment-sign",
                json={"token": _make_token(), "image": "data:image/jpeg;base64,AA"},
            )
            assert fmt.status_code == 400
            # 超大（store 返回 None）
            monkeypatch.setattr(
                "app.modules.safety.api.commitment_sign_public.store_signature_image",
                lambda png: None,
            )
            big = await ac.post(
                "/api/v1/safety/commitment-sign",
                json={"token": _make_token(), "image": _png_data_url()},
            )
            assert big.status_code == 400
            # 成功
            monkeypatch.setattr(
                "app.modules.safety.api.commitment_sign_public.store_signature_image",
                lambda png: "commitment-signatures/y.png",
            )
            ok = await ac.post(
                "/api/v1/safety/commitment-sign",
                json={"token": _make_token(), "image": _png_data_url()},
            )
            assert ok.status_code == 200
            assert saved and saved[0]["signer_name"] == "张三"
            assert saved[0]["image_key"] == "commitment-signatures/y.png"


class TestStoreImage:
    def test_store_rejects_empty_and_oversize(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.service import commitment_signatures as sig

        assert sig.store_signature_image(b"") is None
        assert sig.store_signature_image(b"x" * (sig._MAX_IMAGE_BYTES + 1)) is None

        stored: list[tuple[str, bytes]] = []

        monkeypatch.setattr(
            sig,
            "store_object",
            lambda bucket, key, data, ct: stored.append((key, data)),
        )
        key = sig.store_signature_image(b"\x89PNG\r\n\x1a\nrest")
        assert key and key.startswith("commitment-signatures/")
        assert stored[0][1] == b"\x89PNG\r\n\x1a\nrest"
