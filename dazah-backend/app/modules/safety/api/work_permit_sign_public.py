"""作业票免登签名与 PDF 下载端点（HMAC token 保护，不走登录登录）。

- ``GET  /work-permit-sign/{token}``  免登手写板自包含页（HTMLResponse）
- ``POST /work-permit-sign``          提交签名 PNG dataURL
- ``GET  /work-permit-file/{token}``  审批结束后下载票据 PDF

token 为 HMAC 签名 payload（act=sign/download + 过期时间），路由已在
``rbac.PUBLIC_PATH_PREFIXES`` 登记。业务处理在 chat_flow / signatures 服务。
"""

from __future__ import annotations

import logging
import uuid as uuid_module
from base64 import b64decode
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.modules.safety.models import WorkPermit
from app.modules.safety.service.work_permit_pdf import render_permit_pdf
from app.modules.safety.service.work_permit_signatures import (
    render_signature_page,
    save_signature_row,
    store_signature_image,
    verify_token,
)

logger = logging.getLogger(__name__)

work_permit_sign_public_router = APIRouter()


def _reject(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": status_code, "message": message, "data": None},
    )


def _sign_payload(token: str) -> dict[str, Any] | None:
    return verify_token(token, expected_act="sign")


async def _save_and_refresh(
    session: AsyncSession,
    payload: dict[str, Any],
    image_key: str,
) -> None:
    """落库签名并刷新相关卡片。"""
    from app.modules.safety.service.work_permit_chat_flow import (
        ChatFlowService,
    )

    open_id = str(payload.get("oid") or "")
    permit_type = str(payload.get("ptype") or "")
    pid_raw = str(payload.get("pid") or "")
    is_form = pid_raw == str(uuid_module.UUID(int=0))

    if is_form:
        # 发起行签名：存 Redis 状态 + 按汇总卡原消息 PATCH 刷新
        flow = ChatFlowService(session, open_id=open_id)
        await flow.save_initiator_signature(
            permit_type, sign_key_from(payload), image_key
        )
        await flow.refresh_summary_card(permit_type)
    else:
        # 节点签名：落库 + 刷新已推的审批卡（无缓存卡时退回推送新卡）
        permit_id = uuid_module.UUID(pid_raw)
        round_no = int(payload.get("rnd") or 1)
        node_id_raw = payload.get("nid")
        node_id = uuid_module.UUID(str(node_id_raw)) if node_id_raw else None
        signer_user_id_raw = payload.get("uid")
        signer_user_id = (
            uuid_module.UUID(str(signer_user_id_raw))
            if signer_user_id_raw
            else None
        )
        signer_name = str(payload.get("nm") or "")
        await save_signature_row(
            session,
            permit_id=permit_id,
            round_no=round_no,
            sign_key=sign_key_from(payload),
            node_id=node_id,
            signer_user_id=signer_user_id,
            signer_name=signer_name,
            image_key=image_key,
        )
        await session.commit()
        from app.modules.safety.service.work_permit_notify import (
            refresh_or_push_approval_card,
        )

        await refresh_or_push_approval_card(session, permit_id)


def sign_key_from(payload: dict[str, Any]) -> str:
    return str(payload.get("sk") or "")


@work_permit_sign_public_router.get(
    "/work-permit-sign/{token}",
    summary="免登手写签名页（token 保护）",
    response_class=HTMLResponse,
)
async def work_permit_sign_page(token: str) -> HTMLResponse:
    payload = _sign_payload(token)
    if payload is None:
        return HTMLResponse(
            content=(
                "<html><body style='font-family:sans-serif;text-align:center;"
                "padding:40px'><h2>链接已失效</h2>"
                "<p>请回到聊天窗口重新获取签名链接。</p></body></html>"
            ),
            status_code=410,
        )
    sign_key = sign_key_from(payload)
    row_name = str(payload.get("nm") or sign_key)
    permit_no = str(payload.get("pid") or "")
    if permit_no and permit_no != str(uuid_module.UUID(int=0)):
        from sqlalchemy import select

        from app.modules.safety.models import WorkPermit

        async with async_session_factory() as session:
            permit = (
                await session.execute(
                    select(WorkPermit.permit_no).where(
                        WorkPermit.id == uuid_module.UUID(permit_no)
                    )
                )
            ).scalar_one_or_none()
            permit_no = permit or ""
    page_html = render_signature_page(
        permit_no=permit_no or "作业票", row_name=row_name, token=token
    )
    return HTMLResponse(content=page_html)


@work_permit_sign_public_router.post(
    "/work-permit-sign",
    summary="提交手写签名 PNG（token 保护）",
)
async def submit_work_permit_signature(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _reject("请求体格式错误")
    token = str(body.get("token") or "")
    image_data = str(body.get("image") or "")
    if not token or not image_data:
        return _reject("参数缺失")
    payload = _sign_payload(token)
    if payload is None:
        return _reject("签名链接已过期，请回聊天重新获取", 410)
    prefix = "data:image/png;base64,"
    if not image_data.startswith(prefix):
        return _reject("签名图片格式错误")
    try:
        png_bytes = b64decode(image_data.removeprefix(prefix))
    except Exception:
        return _reject("签名图片解码失败")
    image_key = store_signature_image(png_bytes)
    if image_key is None:
        return _reject("签名图片无效或过大")

    async with async_session_factory() as session:
        await _save_and_refresh(session, payload, image_key)
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "签名成功，请回到聊天窗口继续",
            "data": None,
        },
    )


@work_permit_sign_public_router.get(
    "/work-permit-file/{token}",
    summary="下载票据 PDF（token 保护，审批结束后可用）",
    response_class=Response,
)
async def download_work_permit_pdf(token: str) -> Response:
    from app.modules.safety.service.work_permit_signatures import (
        verify_token as verify_download_token,
    )

    payload = verify_download_token(token, expected_act="download")
    if payload is None:
        return _reject("下载链接已过期，请回聊天重新获取", 410)
    try:
        permit_id = uuid_module.UUID(str(payload.get("pid") or ""))
    except ValueError:
        return _reject("参数错误")
    async with async_session_factory() as session:
        permit = (
            await session.execute(
                select(WorkPermit).where(
                    WorkPermit.id == permit_id,
                    WorkPermit.is_deleted.is_(False),
                )
            )
        ).scalar_one_or_none()
        if permit is None:
            return _reject("作业票不存在", 404)
        if permit.status != "completed":
            return _reject("作业票尚未完工，审批结束后可下载", 409)
        pdf_bytes = await render_permit_pdf(session, permit_id)
        if pdf_bytes is None:
            return _reject("PDF 渲染服务暂不可用，请稍后重试", 503)
        filename = quote(permit.permit_no + ".pdf")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{filename}"
                )
            },
        )
