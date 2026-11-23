"""企业安全承诺公告手写签名服务（自包含实现）。

机制与作业票签名同构（HMAC 免登 token + 对象存储 PNG + 自包含手写板
页），但不 import 作业票签名模块（其表结构绑定 permit 语义）：

- token：``base64url(json_payload).hex(hmac_sha256)``，act=``commitment_sign``，
  payload 含 report_id / open_id / signer_name / exp（30 分钟）。
- 签名 PNG 存 bucket ``safety``，key 前缀 ``commitment-signatures/``
  （复用 :mod:`app.modules.safety.service.work_permit_files` 的对象存储
  双通道：MinIO 优先、本地回退）。
- 落库 ``safety.safety_commitment_signatures``（每日一条，重签覆盖）；
  「用上次签名」= 按签署人查最近一张 image_key 直接复用。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid as uuid_module
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.safety.models import SafetyCommitmentSignature
from app.modules.safety.service.work_permit_files import (
    read_object,
    store_object,
)

logger = logging.getLogger(__name__)

SIGN_TOKEN_TTL_SECONDS = 30 * 60
_MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _secret() -> bytes:
    return get_settings().SECRET_KEY.encode()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _sign_payload(payload: dict[str, Any]) -> str:
    body = _b64url(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    digest = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{digest}"


def create_sign_token(
    *, report_id: str, report_date: str, open_id: str, signer_name: str
) -> str:
    payload = {
        "act": "commitment_sign",
        "rid": report_id,
        "rdate": report_date,
        "oid": open_id,
        "nm": signer_name,
        "exp": int(time.time()) + SIGN_TOKEN_TTL_SECONDS,
    }
    return _sign_payload(payload)


def verify_token(token: str) -> dict[str, Any] | None:
    """校验并还原 payload；过期/篡改/act 不符返回 None。"""
    try:
        body, digest = token.split(".", 1)
        expected = hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return None
    if payload.get("act") != "commitment_sign":
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    result: dict[str, Any] = dict(payload)
    return result


def build_sign_url(token: str) -> str:
    """免登手写板链接（与作业票同构：token 为路径参数）。"""
    settings = get_settings()
    relay = getattr(settings, "SIGN_RELAY_GATEWAY_BASE", "") or ""
    if relay:
        return f"{relay.rstrip('/')}/api/v1/safety/sign-relay/{token}"
    base = (settings.FRONTEND_URL or settings.BACKEND_PUBLIC_URL).rstrip("/")
    return f"{base}/api/v1/safety/commitment-sign/{token}"


def store_signature_image(png_bytes: bytes) -> str | None:
    if not png_bytes or len(png_bytes) > _MAX_IMAGE_BYTES:
        return None
    image_key = f"commitment-signatures/{uuid_module.uuid4().hex}.png"
    store_object("safety", image_key, png_bytes, "image/png")
    return image_key


def read_signature_image(image_key: str) -> bytes | None:
    try:
        pair = read_object("safety", image_key)
        if not pair:
            return None
        return pair[0]
    except Exception:
        logger.exception("读取承诺签名图失败: %s", image_key)
        return None


async def latest_signature(
    db: AsyncSession, *, signer_open_id: str
) -> SafetyCommitmentSignature | None:
    """该签署人最近一次承诺签名（「用上次签名」数据源）。"""
    result = await db.execute(
        select(SafetyCommitmentSignature)
        .where(
            SafetyCommitmentSignature.is_deleted.is_(False),
            SafetyCommitmentSignature.signer_open_id == signer_open_id,
        )
        .order_by(SafetyCommitmentSignature.signed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def reuse_or_none(db: AsyncSession, *, signer_open_id: str) -> str | None:
    row = await latest_signature(db, signer_open_id=signer_open_id)
    return row.image_key if row else None


async def get_by_date(
    db: AsyncSession, report_date: date | str
) -> SafetyCommitmentSignature | None:
    from app.modules.safety.service.safety_commitment import _as_date

    result = await db.execute(
        select(SafetyCommitmentSignature)
        .where(
            SafetyCommitmentSignature.is_deleted.is_(False),
            SafetyCommitmentSignature.report_date == _as_date(report_date),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_signature(
    db: AsyncSession,
    *,
    report_date: date | str,
    signer_open_id: str,
    signer_name: str,
    image_key: str,
    reused: bool = False,
) -> SafetyCommitmentSignature:
    """签名落库（当日一条，重签覆盖 image_key/时间与 reused 标记）。"""
    from app.modules.safety.service.safety_commitment import _as_date

    row = await get_by_date(db, report_date)
    if row is None:
        row = SafetyCommitmentSignature(
            id=uuid_module.uuid4(), report_date=_as_date(report_date)
        )
        db.add(row)
    row.signer_open_id = signer_open_id
    row.signer_name = signer_name or row.signer_name
    row.image_key = image_key
    row.reused = reused
    row.signed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


def render_sign_page(
    *, report_date: str, signer_name: str, token: str, post_url: str
) -> str:
    """免登手写板自包含页（承诺签署专用标题；交互同作业票签名板）。"""
    title = "企业安全承诺签署"
    sub = f"{report_date} · 签署人：{signer_name}（请用手指在白板上写名字）"
    return _SIGN_PAGE_TEMPLATE.format(
        title=title,
        sub=sub,
        token_json=json.dumps(token, ensure_ascii=False),
        post_url_json=json.dumps(post_url, ensure_ascii=False),
    )


_SIGN_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1,
 maximum-scale=1, user-scalable=no">
<title>企业安全承诺签署</title>
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
      tip.textContent = "签名成功 ✔ 承诺公告已生效，请关闭本页";
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
