"""手写签名公网中转网关（部署在公网可达的环境，如测试服务器 180）。

内网环境（生产/开发机）生成的签名链接指向本网关：
- ``GET  /sign-relay/{token}``  渲染自包含手写板页（无业务密钥，token 仅回传）
- ``POST /sign-relay``          收签名图，暂存 Redis 收件箱（7 天 TTL）
- ``POST /sign-relay/pull``     内网服务器凭共享密钥拉取并清空收件箱
  （纯出站轮询，内网零暴露；本地验签后落库，伪造数据在拉取端被丢弃）

仅当 ``SIGN_RELAY_GATEWAY_ENABLED=true`` 时启用；公网网关自身不验业务
token、不落业务库。
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.core.config import get_settings
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

sign_relay_public_router = APIRouter()

_INBOX_KEY = "safety:signrelay:inbox"
_INBOX_TTL_SECONDS = 7 * 24 * 3600
_PULL_BATCH_MAX = 50
_PDF_TTL_SECONDS = 7 * 24 * 3600


def _disabled_response() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": "签名中转未启用", "data": None},
    )


def _gateway_enabled() -> bool:
    settings = get_settings()
    return bool(settings.SIGN_RELAY_GATEWAY_ENABLED)


@sign_relay_public_router.get(
    "/sign-relay/{token}",
    summary="手写签名中转页（公网网关渲染自包含手写板）",
    response_class=HTMLResponse,
)
async def sign_relay_page(token: str) -> HTMLResponse:
    if not _gateway_enabled():
        return HTMLResponse(
            content=(
                "<html><body style='font-family:sans-serif;text-align:center;"
                "padding:40px'><h2>签名中转未启用</h2></body></html>"
            ),
            status_code=404,
        )
    from app.modules.safety.service.work_permit_signatures import (
        render_signature_page,
    )

    return HTMLResponse(
        content=render_signature_page(
            permit_no="作业票",
            row_name="签名确认",
            token=token,
            post_url="/api/v1/safety/sign-relay/",
        )
    )


@sign_relay_public_router.post(
    # 尾斜杠必须保留：公开白名单前缀为 "/sign-relay/"（带斜杠），
    # 无斜杠路径会被权限中间件拦成 401
    "/sign-relay/",
    summary="手写签名中转提交（暂存收件箱，等待内网拉取）",
)
async def sign_relay_submit(request: Request) -> JSONResponse:
    if not _gateway_enabled():
        return _disabled_response()
    try:
        body = await request.json()
    except Exception:
        return _bad_request("请求体格式错误")
    token = str(body.get("token") or "")
    image = str(body.get("image") or "")
    if not token or not image:
        return _bad_request("参数缺失")

    from app.modules.safety.service.work_permit_signatures import (
        decode_signature_data_url,
    )

    png = decode_signature_data_url(image)
    if png is None:
        return _bad_request("签名图片无效或过大")

    await redis_client.rpush(  # type: ignore[misc]
        _INBOX_KEY,
        json.dumps({"token": token, "image": image}, ensure_ascii=False),
    )
    await redis_client.expire(_INBOX_KEY, _INBOX_TTL_SECONDS)
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "签名成功，请回到聊天窗口继续",
            "data": None,
        },
    )


@sign_relay_public_router.post(
    "/sign-relay/pdf/{pdf_key}",
    summary="内网上传完工 PDF 到公网中转（共享密钥认证，7 天有效）",
)
async def sign_relay_pdf_upload(
    pdf_key: str,
    request: Request,
    x_relay_key: str | None = Header(default=None, alias="X-Relay-Key"),
) -> JSONResponse:
    settings = get_settings()
    if not _gateway_enabled() or not settings.SIGN_RELAY_KEY:
        return _disabled_response()
    if not x_relay_key or x_relay_key != settings.SIGN_RELAY_KEY:
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "中转密钥不匹配", "data": None},
        )
    body = await request.body()
    if not body or body[:5] != b"%PDF-":
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "PDF 内容无效", "data": None},
        )
    if len(body) > 20 * 1024 * 1024:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "PDF 超过大小限制", "data": None},
        )
    await redis_client.set(
        f"safety:signrelay:pdf:{pdf_key}",
        base64.b64encode(body).decode("ascii"),
        ex=_PDF_TTL_SECONDS,
    )
    return JSONResponse(
        status_code=200,
        content={"code": 200, "message": "PDF 已上传", "data": None},
    )


@sign_relay_public_router.get(
    "/sign-relay/pdf/{pdf_key}",
    summary="公网下载完工 PDF（中转 7 天有效）",
    response_class=Response,
)
async def sign_relay_pdf_download(
    pdf_key: str,
    name: str = "permit.pdf",
) -> Response:
    if not _gateway_enabled():
        return _disabled_response()
    data = await redis_client.get(f"safety:signrelay:pdf:{pdf_key}")
    if not data:
        return JSONResponse(
            status_code=404,
            content={
                "code": 404,
                "message": "下载链接已失效（7 天有效），请联系办票人重新分享",
                "data": None,
            },
        )
    pdf_bytes = base64.b64decode(data)
    from urllib.parse import quote

    filename = quote(name if name.endswith(".pdf") else f"{name}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": (f"attachment; filename*=UTF-8''{filename}")},
    )


@sign_relay_public_router.post(
    "/sign-relay/pull",
    summary="内网拉取暂存签名（共享密钥认证，拉取即清空）",
)
async def sign_relay_pull(
    x_relay_key: str | None = Header(default=None, alias="X-Relay-Key"),
) -> JSONResponse:
    settings = get_settings()
    if not _gateway_enabled() or not settings.SIGN_RELAY_KEY:
        return _disabled_response()
    if not x_relay_key or x_relay_key != settings.SIGN_RELAY_KEY:
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "中转密钥不匹配", "data": None},
        )
    items: list[dict[str, Any]] = []
    while len(items) < _PULL_BATCH_MAX:
        raw = await redis_client.rpop(_INBOX_KEY)  # type: ignore[misc]
        if not raw:
            break
        try:
            items.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            logger.warning("中转收件箱存在无法解析的条目，已丢弃")
    return JSONResponse(
        status_code=200,
        content={"code": 200, "message": "ok", "data": {"items": items}},
    )


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"code": 400, "message": message, "data": None},
    )


__all__ = ["sign_relay_public_router"]
