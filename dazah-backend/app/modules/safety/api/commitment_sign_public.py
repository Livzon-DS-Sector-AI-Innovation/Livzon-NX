"""Safety API — 企业安全承诺签署免登端点（无需登录，token 自鉴权）。

与作业票免登签名同构：GET 渲染手写板页，POST 提交签名图。路径在
``rbac.PUBLIC_PATH_PREFIXES`` 放行。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.modules.safety.service.commitment_signatures import (
    render_sign_page,
    save_signature,
    store_signature_image,
    verify_token,
)

commitment_sign_public_router = APIRouter()

_EXPIRED_HTML = (
    "<!DOCTYPE html><html lang='zh-CN'><meta charset='utf-8'>"
    "<body style='font-family:sans-serif;text-align:center;padding:48px'>"
    "<h2>链接已失效</h2><p>签署链接有效期为 30 分钟，"
    "请在飞书聊天窗口重新打开，或联系安全员重新推送。</p></body></html>"
)


@commitment_sign_public_router.get(
    "/commitment-sign/{token}",
    response_class=HTMLResponse,
    summary="企业安全承诺签署手写板（免登）",
)
async def render_commitment_sign_page(token: str) -> HTMLResponse:
    payload = verify_token(token)
    if payload is None:
        return HTMLResponse(_EXPIRED_HTML, status_code=410)
    return HTMLResponse(
        render_sign_page(
            report_date=str(payload.get("rdate") or ""),
            signer_name=str(payload.get("nm") or ""),
            token=token,
            post_url="/api/v1/safety/commitment-sign",
        )
    )


@commitment_sign_public_router.post(
    "/commitment-sign",
    summary="提交企业安全承诺手写签名（免登）",
)
async def submit_commitment_signature(request: Request) -> JSONResponse:
    import base64
    import binascii

    from app.core.database import async_session_factory

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "请求体格式错误"},
        )
    token = str(body.get("token") or "")
    image = str(body.get("image") or "")
    payload = verify_token(token)
    if payload is None:
        return JSONResponse(
            status_code=410,
            content={"code": 410, "message": "签署链接已失效，请重新获取"},
        )
    if not image.startswith("data:image/png;base64,"):
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "签名图格式错误"},
        )
    try:
        png_bytes = base64.b64decode(image.split(",", 1)[1])
    except (binascii.Error, ValueError):
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "签名图解码失败"},
        )
    image_key = store_signature_image(png_bytes)
    if not image_key:
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "签名图过大（限制 2MB），请重写"},
        )

    async with async_session_factory() as db:
        await save_signature(
            db,
            report_date=str(payload.get("rdate") or ""),
            signer_open_id=str(payload.get("oid") or ""),
            signer_name=str(payload.get("nm") or ""),
            image_key=image_key,
            reused=False,
        )
    return JSONResponse(content={"code": 200, "message": "签名成功，承诺公告已生效"})
