"""手写签名中转轮询（内网部署侧）：主动到公网网关拉取签名并落库。

纯出站连接（内网 → 公网网关），零端口暴露；网关只暂存不透明的
token+签名图，落库前在本环境本地验签（HMAC），伪造/过期数据直接丢弃。
配置 ``SIGN_RELAY_GATEWAY_BASE`` + ``SIGN_RELAY_KEY`` 后由 main lifespan
启动；未配置则不启动。
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PULL_TIMEOUT_SECONDS = 10
_BATCH_MAX = 50


async def _process_item(item: dict) -> bool:
    """处理一条中转签名；返回是否成功落库（失败不重试，等用户重签）。"""
    from app.modules.safety.service.work_permit_signatures import (
        apply_signature_submission,
        decode_signature_data_url,
        store_signature_image,
        verify_token,
    )

    token = str(item.get("token") or "")
    payload = verify_token(token, expected_act="sign")
    if payload is None:
        logger.info("中转签名 token 无效/过期，丢弃")
        return False
    image = str(item.get("image") or "")
    png = decode_signature_data_url(image)
    if png is None:
        logger.warning("中转签名图片解码失败，丢弃: sk=%s", payload.get("sk"))
        return False
    image_key = store_signature_image(png)
    if image_key is None:
        logger.warning("中转签名图片存储失败，丢弃: sk=%s", payload.get("sk"))
        return False
    from app.core.database import async_session_factory

    async with async_session_factory() as session:
        await apply_signature_submission(session, payload, image_key)
    logger.info(
        "中转签名已落库: pid=%s sk=%s",
        payload.get("pid"),
        payload.get("sk"),
    )
    return True


async def poll_once() -> int:
    """拉取一次收件箱并处理，返回成功处理条数。"""
    settings = get_settings()
    base = (settings.SIGN_RELAY_GATEWAY_BASE or "").rstrip("/")
    key = settings.SIGN_RELAY_KEY
    if not base or not key:
        return 0
    async with httpx.AsyncClient(timeout=_PULL_TIMEOUT_SECONDS) as http:
        resp = await http.post(
            f"{base}/api/v1/safety/sign-relay/pull",
            headers={"X-Relay-Key": key},
        )
    if resp.status_code != 200:
        logger.warning("中转拉取失败: %s %s", resp.status_code, resp.text[:120])
        return 0
    data = resp.json() or {}
    items = ((data.get("data") or {}).get("items")) or []
    if not items:
        return 0
    ok = 0
    for item in items[:_BATCH_MAX]:
        try:
            if await _process_item(item):
                ok += 1
        except Exception:
            logger.exception("中转签名处理异常，已丢弃该条")
    logger.info("中转签名拉取完成: 收到=%s 落库=%s", len(items), ok)
    return ok


async def sign_relay_loop() -> None:
    settings = get_settings()
    base = (settings.SIGN_RELAY_GATEWAY_BASE or "").strip()
    key = (settings.SIGN_RELAY_KEY or "").strip()
    if not base or not key:
        logger.info("未配置签名中转网关，轮询不启动")
        return
    interval = max(5, int(settings.SIGN_RELAY_POLL_SECONDS or 10))
    logger.info("签名中转轮询启动: gateway=%s interval=%ss", base, interval)
    while True:
        try:
            await poll_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("签名中转轮询异常，稍后重试")
        await asyncio.sleep(interval)


def start_sign_relay_poller_task() -> asyncio.Task | None:
    """lifespan 启动入口：已配置网关时创建轮询任务，否则返回 None。"""
    settings = get_settings()
    if not (settings.SIGN_RELAY_GATEWAY_BASE and settings.SIGN_RELAY_KEY):
        return None
    return asyncio.create_task(sign_relay_loop())
