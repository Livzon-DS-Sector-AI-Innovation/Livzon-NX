"""作业票手写签名：免登 token、签名图存储、复用查询、自包含手写板页。

- token：HMAC-SHA256 签名的 base64url(payload).hex(digest)，payload 含
  permit_id/round/sign_key/node_id/open_id/exp/act，不可伪造、短时效。
- 签名图：PNG bytes 经 ``store_object("work-permit-signatures", ...)`` 存储
  （MinIO 优先、本地回退），(permit_id, round, sign_key) 重签覆盖。
- 复用：按签署人取最近一张签名图（个人默认签名，跨签字行/跨票可用）。
- 手写板页：后端自包含 HTML（canvas 手写 + fetch 提交），无需登录平台，
  与 quality 免登确认页同机制（路由在 PUBLIC_PATH_PREFIXES 登记）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.safety.models import WorkPermitSignature
from app.modules.safety.service.work_permit_files import store_object

logger = logging.getLogger(__name__)

SIGN_TOKEN_TTL_SECONDS = 30 * 60
# 完工票 PDF 下载链接（HMAC 防伪；归档件需要长期可点，7 天足够覆盖
# 审批后存档场景，过期可在平台重新生成）
_DOWNLOAD_TOKEN_TTL_SECONDS = 7 * 24 * 3600
_MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _secret() -> bytes:
    return get_settings().SECRET_KEY.encode()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign_payload(payload: dict[str, Any]) -> str:
    body = _b64url(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    digest = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{digest}"


def _load_payload(token: str) -> dict[str, Any] | None:
    try:
        body, digest = token.split(".", 1)
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, expected):
            return None
        payload = json.loads(_b64url_decode(body))
        if not isinstance(payload, dict):
            return None
    except Exception:
        return None
    return payload


def create_sign_token(
    *,
    permit_id: UUID,
    round_no: int,
    sign_key: str,
    node_id: UUID | None,
    open_id: str,
    signer_name: str = "",
    permit_type: str = "",
    ttl_seconds: int = SIGN_TOKEN_TTL_SECONDS,
) -> str:
    payload = {
        "act": "sign",
        "pid": str(permit_id),
        "rnd": round_no,
        "sk": sign_key,
        "nid": str(node_id) if node_id else None,
        "oid": open_id,
        "nm": signer_name,
        "ptype": permit_type,
        "exp": int((datetime.now(UTC) + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return _sign_payload(payload)


def create_download_token(permit_id: UUID, ttl_seconds: int | None = None) -> str:
    ttl = ttl_seconds or _DOWNLOAD_TOKEN_TTL_SECONDS
    payload = {
        "act": "download",
        "pid": str(permit_id),
        "exp": int((datetime.now(UTC) + timedelta(seconds=ttl)).timestamp()),
    }
    return _sign_payload(payload)


def verify_token(token: str, *, expected_act: str) -> dict[str, Any] | None:
    payload = _load_payload(token)
    if payload is None or payload.get("act") != expected_act:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < datetime.now(UTC).timestamp():
        return None
    return payload


def build_sign_url(token: str) -> str:
    """手写签名页链接：配置公网网关（SIGN_RELAY_GATEWAY_BASE）时指向
    网关中转页（手机可达），否则指向本环境直连页。"""
    settings = get_settings()
    gateway = (settings.SIGN_RELAY_GATEWAY_BASE or "").rstrip("/")
    if gateway:
        return f"{gateway}/api/v1/safety/sign-relay/{token}"
    return (
        f"{(settings.FRONTEND_URL or settings.BACKEND_PUBLIC_URL).rstrip('/')}"
        f"/api/v1/safety/work-permit-sign/{token}"
    )


async def apply_signature_submission(
    session: AsyncSession, payload: dict[str, Any], image_key: str
) -> None:
    """签名提交共用处理（直连端点与中转轮询共用）。

    发起行（表单态，pid=UUID(int=0)）：写入聊天表单状态并 PATCH 汇总卡；
    审批节点：落库 + 提交 + 刷新已推审批卡。
    """
    from app.modules.safety.service.work_permit_chat_flow import (
        ChatFlowService,
    )

    open_id = str(payload.get("oid") or "")
    permit_type = str(payload.get("ptype") or "")
    pid_raw = str(payload.get("pid") or "")
    is_form = pid_raw == str(uuid_module.UUID(int=0))

    if is_form:
        flow = ChatFlowService(session, open_id=open_id)
        await flow.save_initiator_signature(
            permit_type, str(payload.get("sk") or ""), image_key
        )
        await flow.refresh_summary_card(permit_type)
        return

    permit_id = uuid_module.UUID(pid_raw)
    round_no = int(payload.get("rnd") or 1)
    node_id_raw = payload.get("nid")
    node_id = (
        uuid_module.UUID(str(node_id_raw)) if node_id_raw else None
    )
    sign_key = str(payload.get("sk") or "")
    signer_user_id_raw = payload.get("uid")
    signer_user_id = (
        uuid_module.UUID(str(signer_user_id_raw)) if signer_user_id_raw else None
    )
    await save_signature_row(
        session,
        permit_id=permit_id,
        round_no=round_no,
        sign_key=sign_key,
        node_id=node_id,
        signer_user_id=signer_user_id,
        signer_name=str(payload.get("nm") or ""),
        image_key=image_key,
    )
    await session.commit()
    from app.modules.safety.service.work_permit_notify import (
        on_brief_signature_landed,
        refresh_or_push_approval_card,
    )

    if sign_key.startswith("brief_worker_"):
        # 交底作业人签名：PATCH 本人卡 + 刷新申请人转发卡（不影响审批卡）
        await on_brief_signature_landed(session, permit_id, sign_key)
        return
    await refresh_or_push_approval_card(session, permit_id)


def decode_signature_data_url(image: str) -> bytes | None:
    """data URL → PNG bytes；非法/超限/非 PNG 魔数返回 None（中转共用）。"""
    raw = _decode_data_url(image)
    if raw is None:
        return None
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return raw


# ── 签名图存储与落库 ──


def _decode_data_url(image: str) -> bytes | None:
    prefix = "data:image/png;base64,"
    alt = "data:image/jpeg;base64,"
    if image.startswith(prefix):
        image = image.removeprefix(prefix)
    elif image.startswith(alt):
        image = image.removeprefix(alt)
    else:
        return None
    try:
        content = base64.b64decode(image)
    except Exception:
        return None
    if not content or len(content) > _MAX_IMAGE_BYTES:
        return None
    return content


def store_signature_image(png_bytes: bytes) -> str | None:
    """签名 PNG 存储为对象并返回 image_key；非法/超限返回 None。"""
    if not png_bytes or len(png_bytes) > _MAX_IMAGE_BYTES:
        return None
    image_key = f"signatures/{uuid_module.uuid4().hex}.png"
    store_object("work-permit-signatures", image_key, png_bytes, "image/png")
    return image_key


async def save_signature_row(
    db: AsyncSession,
    *,
    permit_id: UUID,
    round_no: int,
    sign_key: str,
    node_id: UUID | None,
    signer_user_id: UUID | None,
    signer_name: str,
    image_key: str,
) -> WorkPermitSignature:
    """落库签名行（同 (permit, round, sign_key) 覆盖重签）。"""
    result = await db.execute(
        select(WorkPermitSignature).where(
            WorkPermitSignature.permit_id == permit_id,
            WorkPermitSignature.round == round_no,
            WorkPermitSignature.sign_key == sign_key,
            WorkPermitSignature.is_deleted.is_(False),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = WorkPermitSignature(
            permit_id=permit_id,
            round=round_no,
            sign_key=sign_key,
            node_id=node_id,
            signer_user_id=signer_user_id,
            signer_name=signer_name or "",
            image_key=image_key,
        )
        db.add(row)
    else:
        row.node_id = node_id
        row.signer_user_id = signer_user_id
        if signer_name:
            row.signer_name = signer_name
        row.image_key = image_key
        row.signed_at = datetime.now(UTC)
    await db.flush()
    return row


async def latest_person_signature(
    db: AsyncSession,
    *,
    signer_user_id: UUID,
) -> WorkPermitSignature | None:
    """取该签署人最近一次手写签名行（个人默认签名，跨节点/跨票复用）。"""
    result = await db.execute(
        select(WorkPermitSignature)
        .where(
            WorkPermitSignature.signer_user_id == signer_user_id,
            WorkPermitSignature.is_deleted.is_(False),
        )
        .order_by(WorkPermitSignature.signed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def reuse_or_none(
    db: AsyncSession,
    *,
    signer_user_id: UUID,
    sign_key: str | None = None,
) -> str | None:
    """取该签署人最近一张签名图（默认复用）。

    手写签名是个人笔迹：按签署人取最近一次，同一签名跨签字行/跨票
    默认可用；``sign_key`` 仅为兼容旧调用保留，不参与过滤。
    """
    row = await latest_person_signature(db, signer_user_id=signer_user_id)
    return row.image_key if row else None


async def get_permit_signatures(
    db: AsyncSession, permit_id: UUID, round_no: int
) -> dict[str, WorkPermitSignature]:
    result = await db.execute(
        select(WorkPermitSignature).where(
            WorkPermitSignature.permit_id == permit_id,
            WorkPermitSignature.round == round_no,
            WorkPermitSignature.is_deleted.is_(False),
        )
    )
    return {row.sign_key: row for row in result.scalars().all()}


async def read_signature_image(image_key: str) -> tuple[bytes, str] | None:
    from app.modules.safety.service.work_permit_files import read_object

    return read_object("work-permit-signatures", image_key)


# ── 免登手写板自包含页 ──

_SIGNATURE_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1,
 maximum-scale=1, user-scalable=no">
<title>作业票手写签名</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
        margin: 0; background: #f5f6f8; color: #222; }}
  .wrap {{ max-width: 720px; margin: 0 auto; padding: 16px; }}
  h2 {{ font-size: 18px; margin: 8px 0 4px; }}
  .sub {{ color: #888; font-size: 13px; margin-bottom: 12px; }}
  .pad {{ background: #fff; border: 1px solid #ddd; border-radius: 12px;
        touch-action: none; width: 100%; height: 260px; display: block; }}
  .row {{ display: flex; gap: 10px; margin-top: 12px; }}
  button {{ flex: 1; padding: 12px; font-size: 16px; border: 0;
          border-radius: 10px; }}
  .clear {{ background: #eee; color: #444; }}
  .ok {{ background: #2f7ef7; color: #fff; }}
  .tip {{ margin-top: 12px; font-size: 14px; min-height: 20px; }}
  .tip.ok {{ color: #2aa05a; }}
  .tip.err {{ color: #e5544b; }}
</style>
</head>
<body>
<div class="wrap">
  <h2>{title}</h2>
  <div class="sub">{sub}</div>
  <canvas id="pad" class="pad"></canvas>
  <div class="row">
    <button class="clear" id="clear">清除重写</button>
    <button class="ok" id="ok">确认签名</button>
  </div>
  <div class="tip" id="tip">请用手指在白板上写名字</div>
</div>
<script>
const POST_URL = {post_url_json};
const TOKEN = {token_json};
const canvas = document.getElementById("pad");
const tip = document.getElementById("tip");
const ctx = canvas.getContext("2d");
let dirty = false;

function resize() {{
  const data = dirty ? canvas.toDataURL("image/png") : null;
  canvas.width = canvas.clientWidth * window.devicePixelRatio;
  canvas.height = 260 * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  ctx.lineWidth = 3; ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.strokeStyle = "#1a1a1a";
  if (data) {{
    const img = new Image();
    img.onload = () => ctx.drawImage(img, 0, 0, canvas.clientWidth, 260);
    img.src = data;
  }}
}}
window.addEventListener("resize", resize);
resize();

function pos(e) {{
  const rect = canvas.getBoundingClientRect();
  return [e.clientX - rect.left, e.clientY - rect.top];
}}
canvas.addEventListener("pointerdown", (e) => {{
  canvas.setPointerCapture(e.pointerId);
  const [x, y] = pos(e);
  ctx.beginPath(); ctx.moveTo(x, y);
  dirty = true;
}});
canvas.addEventListener("pointermove", (e) => {{
  if (!dirty || e.buttons === 0) return;
  const [x, y] = pos(e);
  ctx.lineTo(x, y); ctx.stroke();
}});
window.addEventListener("pointerup", () => {{ if (dirty) ctx.stroke(); }});

document.getElementById("clear").addEventListener("click", () => {{
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  dirty = false;
  tip.className = "tip"; tip.textContent = "已清空，请重新书写";
}});

document.getElementById("ok").addEventListener("click", async () => {{
  if (!dirty) {{ tip.className = "tip err"; tip.textContent = "请先手写签名"; return; }}
  tip.className = "tip"; tip.textContent = "正在提交签名…";
  try {{
    const resp = await fetch(POST_URL, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ token: TOKEN, image: canvas.toDataURL("image/png") }}),
    }});
    const json = await resp.json().catch(() => null);
    if (resp.ok && json && json.code === 200) {{
      tip.className = "tip ok";
      tip.textContent = "签名成功 ✔ 请回到聊天窗口继续操作";
      document.getElementById("ok").disabled = true;
    }} else {{
      tip.className = "tip err";
      tip.textContent = (json && json.message) || "签名提交失败，请重试";
    }}
  }} catch (err) {{
    tip.className = "tip err"; tip.textContent = "网络异常，请重试";
  }}
}});
</script>
</body>
</html>
"""


def render_signature_page(
    *,
    permit_no: str,
    row_name: str,
    token: str,
    post_url: str = "/api/v1/safety/work-permit-sign",
) -> str:
    """免登手写板自包含页（canvas 手写 → POST 提交）。

    ``post_url`` 供公网中转模式使用（180 网关页提交到网关收件端点）；
    默认提交到本环境直连端点。
    """
    return _SIGNATURE_PAGE_TEMPLATE.format(
        title=f"{permit_no} · 手写签名",
        sub=f"签字行：{row_name}（签名将存档到作业票，可重新手写覆盖）",
        token_json=json.dumps(token, ensure_ascii=False),
        post_url_json=json.dumps(post_url, ensure_ascii=False),
    )


__all__ = [
    "SIGN_TOKEN_TTL_SECONDS",
    "create_download_token",
    "create_sign_token",
    "get_permit_signatures",
    "latest_person_signature",
    "read_signature_image",
    "render_signature_page",
    "reuse_or_none",
    "save_signature_row",
    "store_signature_image",
    "verify_token",
]


