"""作业票免登签名与 PDF 下载端点测试（token 校验与外部服务全 stub）。

覆盖：签名页失效/渲染、签名提交参数校验全分支、发起行与节点两条
签名落库路径、PDF 下载的 token/404/409/503/成功分支。
"""

from __future__ import annotations

import base64
import uuid as uuid_module
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.modules.safety.api.work_permit_sign_public as sign_mod
from app.modules.safety.api.work_permit_sign_public import (
    work_permit_sign_public_router,
)
from app.modules.safety.models import WorkPermit

_TOKEN = "hmac-token-1"

_SIGN_PAYLOAD = {
    "act": "sign",
    "oid": "ou-signer",
    "ptype": "blind_plate",
    "pid": str(uuid_module.UUID(int=0)),
    "sk": "initiator",
    "nm": "张三",
}


def _png_data_url() -> str:
    return "data:image/png;base64," + base64.b64encode(
        b"\x89PNG fake-signature"
    ).decode()


def _verify_payload(token: str, *, expected_act: str) -> dict[str, Any]:
    payload = {**_SIGN_PAYLOAD, "act": expected_act}
    if token.endswith("download"):
        payload["act"] = "download"
        payload["pid"] = str(uuid4())
    return payload


@pytest.fixture
async def sign_client(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    """挂公共签署路由；token 校验放行；session factory 指向测试会话。"""

    @asynccontextmanager
    async def _session_factory() -> AsyncIterator[Any]:
        yield db_session

    def _verify_ok_stub(
        token: str, *, expected_act: str
    ) -> dict[str, Any]:
        return _verify_payload(token, expected_act=expected_act)

    monkeypatch.setattr(sign_mod, "async_session_factory", _session_factory)
    monkeypatch.setattr(sign_mod, "verify_token", _verify_ok_stub)
    monkeypatch.setattr(
        sign_mod, "render_signature_page", lambda **_k: "<html>签名板</html>"
    )
    monkeypatch.setattr(
        sign_mod, "store_signature_image", lambda _b: "signs/probe.png"
    )
    application = FastAPI()
    application.include_router(
        work_permit_sign_public_router, prefix="/api/v1/safety"
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def expired_client(
    sign_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    def _verify_none(token: str, *, expected_act: str) -> None:
        return None

    monkeypatch.setattr(sign_mod, "verify_token", _verify_none)
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify_none,
    )
    return sign_client


async def _post_sign(
    client: Any, token: str = _TOKEN, image: str | None = None
) -> Any:
    body: dict[str, Any] = {"token": token}
    if image is not None:
        body["image"] = image
    return await client.post("/api/v1/safety/work-permit-sign", json=body)


async def test_sign_page_invalid_token_returns_410(expired_client: Any) -> None:
    response = await expired_client.get("/api/v1/safety/work-permit-sign/bad")
    assert response.status_code == 410
    assert "链接已失效" in response.text


async def test_sign_page_renders_with_permit_no(
    sign_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    permit_id = uuid4()
    payload = {**_SIGN_PAYLOAD, "pid": str(permit_id)}

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(sign_mod, "verify_token", _verify)
    captured: dict[str, str] = {}

    def _render(**kwargs: str) -> str:
        captured.update(kwargs)
        return "<html>签名板</html>"

    monkeypatch.setattr(sign_mod, "render_signature_page", _render)
    response = await sign_client.get(
        "/api/v1/safety/work-permit-sign/hmac-token-1"
    )
    assert response.status_code == 200
    assert captured.get("token") == "hmac-token-1"


async def test_submit_missing_params_returns_400(sign_client: Any) -> None:
    response = await sign_client.post("/api/v1/safety/work-permit-sign", json={})
    assert response.status_code == 400
    assert "参数缺失" in response.json()["message"]


async def test_submit_expired_token_returns_410(expired_client: Any) -> None:
    response = await _post_sign(expired_client, image=_png_data_url())
    assert response.status_code == 410


async def test_submit_non_dataurl_rejected(sign_client: Any) -> None:
    response = await _post_sign(sign_client, image="not-a-dataurl")
    assert response.status_code == 400
    assert "格式错误" in response.json()["message"]


async def test_submit_empty_png_payload_rejected(
    sign_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空 PNG 载荷（b64decode 忽略非法字符得 b''）：store 判无效。"""
    monkeypatch.setattr(sign_mod, "store_signature_image", lambda _b: None)
    response = await _post_sign(sign_client, image="data:image/png;base64,!!!!")
    assert response.status_code == 400
    assert "无效或过大" in response.json()["message"]


async def test_store_failure_returns_400(
    sign_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sign_mod, "store_signature_image", lambda _b: None)
    response = await _post_sign(sign_client, image=_png_data_url())
    assert response.status_code == 400
    assert "无效或过大" in response.json()["message"]


async def test_node_signature_saves_row_and_refreshes(
    sign_client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """节点签名：save_signature_row 落库 + 审批卡刷新触发。"""
    permit_id = uuid4()
    node_id = uuid4()
    payload = {
        **_SIGN_PAYLOAD,
        "pid": str(permit_id),
        "nid": str(node_id),
        "uid": "",
    }
    save_calls: list[dict[str, Any]] = []
    refresh_calls: list[str] = []

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return {**payload, "act": expected_act}

    monkeypatch.setattr(sign_mod, "verify_token", _verify)

    async def _save_signature_row(db: Any, **kwargs: Any) -> None:
        save_calls.append(kwargs)

    async def _refresh_or_push(db: Any, permit_id_arg: Any) -> None:
        refresh_calls.append(str(permit_id_arg))

    # 落库逻辑已收敛到 work_permit_signatures.apply_signature_submission
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.save_signature_row",
        _save_signature_row,
    )
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_notify.refresh_or_push_approval_card",
        _refresh_or_push,
    )
    response = await _post_sign(sign_client, image=_png_data_url())
    assert response.status_code == 200
    assert save_calls and save_calls[0]["sign_key"] == "initiator"
    assert refresh_calls == [str(permit_id)]
    assert response.json()["message"] == "签名成功，请回到聊天窗口继续"


async def test_form_signature_saves_state_and_refreshes_summary(
    sign_client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """发起行签名（pid=全零 UUID）：写 Redis 状态 + 刷新汇总卡。"""
    saved: list[tuple[str, str, str]] = []
    refreshed: list[str] = []

    class _FlowStub:
        def __init__(self, db: Any, *, open_id: str) -> None:
            self.open_id = open_id

        async def save_initiator_signature(
            self, permit_type: str, sign_key: str, image_key: str
        ) -> None:
            saved.append((permit_type, sign_key, image_key))

        async def refresh_summary_card(self, permit_type: str) -> None:
            refreshed.append(permit_type)

    payload = {**_SIGN_PAYLOAD, "pid": str(uuid_module.UUID(int=0))}

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return payload

    monkeypatch.setattr(sign_mod, "verify_token", _verify)
    # ChatFlowService 在 _save_and_refresh 内为函数级 import：patch 源模块
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_chat_flow.ChatFlowService",
        _FlowStub,
    )
    response = await _post_sign(sign_client, image=_png_data_url())
    assert response.status_code == 200
    assert saved and saved[0] == ("blind_plate", "initiator", "signs/probe.png")
    assert refreshed == ["blind_plate"]


async def test_download_invalid_token_returns_410(expired_client: Any) -> None:
    response = await expired_client.get("/api/v1/safety/work-permit-file/bad")
    assert response.status_code == 410
    assert "过期" in response.json()["message"]


async def test_download_bad_pid_returns_400(
    sign_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return {"act": "download", "pid": "not-a-uuid"}

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify,
    )
    response = await sign_client.get("/api/v1/safety/work-permit-file/bad")
    assert response.status_code == 400
    assert "参数错误" in response.json()["message"]


async def test_download_missing_permit_returns_404(
    sign_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_id = uuid4()

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return {"act": "download", "pid": str(missing_id)}

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify,
    )
    response = await sign_client.get(
        f"/api/v1/safety/work-permit-file/{missing_id}"
    )
    assert response.status_code == 404
    assert "不存在" in response.json()["message"]


async def test_download_not_completed_returns_409(
    sign_client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:

    permit_id = uuid4()
    permit = WorkPermit(
        id=permit_id,
        permit_no="WP-DL-1",
        permit_type="blind_plate",
        permit_level="none",
        status="pending_approval",
    )
    db_session.add(permit)
    await db_session.flush()

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return {"act": "download", "pid": str(permit_id)}

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify,
    )
    response = await sign_client.get(
        f"/api/v1/safety/work-permit-file/{permit_id}"
    )
    assert response.status_code == 409
    assert "尚未完工" in response.json()["message"]


async def test_download_render_failure_returns_503(
    sign_client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:

    permit_id = uuid4()
    permit = WorkPermit(
        id=permit_id,
        permit_no="WP-DL-2",
        permit_type="blind_plate",
        permit_level="none",
        status="completed",
    )
    db_session.add(permit)
    await db_session.flush()

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return {"act": "download", "pid": str(permit_id)}

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify,
    )

    async def _render_none(db: Any, pid: Any) -> None:
        return None

    monkeypatch.setattr(sign_mod, "render_permit_pdf", _render_none)
    response = await sign_client.get(
        f"/api/v1/safety/work-permit-file/{permit_id}"
    )
    assert response.status_code == 503
    assert "暂不可用" in response.json()["message"]


async def test_download_completed_returns_pdf(
    sign_client: Any, db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:

    permit_id = uuid4()
    permit = WorkPermit(
        id=permit_id,
        permit_no="WP-DL-3",
        permit_type="blind_plate",
        permit_level="none",
        status="completed",
    )
    db_session.add(permit)
    await db_session.flush()

    def _verify(token: str, *, expected_act: str) -> dict[str, Any]:
        return {"act": "download", "pid": str(permit_id)}

    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_signatures.verify_token",
        _verify,
    )

    async def _render_ok(db: Any, pid: Any) -> bytes:
        return b"%PDF-fake"

    monkeypatch.setattr(sign_mod, "render_permit_pdf", _render_ok)
    response = await sign_client.get(
        f"/api/v1/safety/work-permit-file/{permit_id}"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "WP-DL-3.pdf" in response.headers.get("content-disposition", "")
