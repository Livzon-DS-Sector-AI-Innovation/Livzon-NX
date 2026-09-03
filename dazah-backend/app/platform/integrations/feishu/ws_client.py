"""飞书 WebSocket 长连接客户端。

两种实现并存：
- start_ws_client/stop_ws_client：lark-oapi SDK 的 ws.Client（平台事件订阅）。
- FeishuWsClient：原生 WebSocket + protobuf 实现，支持 card.action.trigger
  卡片按钮回调（2.9 秒同步回包）。以类实例为单元管理连接状态，支持一个
  进程内同时维持多个飞书应用的独立长连接（如平台应用 + 人事模块应用）。
"""

import asyncio
import base64
import json
import logging
import ssl
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import websockets

logger = logging.getLogger(__name__)

FEISHU_DOMAIN = "https://open.feishu.cn"
WS_ENDPOINT_URL = f"{FEISHU_DOMAIN}/callback/ws/endpoint"

CardActionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
OtherEventDispatcher = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

_ws_threads: dict[str, threading.Thread] = {}
_stop_flags: dict[str, threading.Event] = {}


def start_ws_client(
    app_id: str | None = None,
    app_secret: str | None = None,
    event_handler: Any = None,
    name: str = "feishu-ws",
) -> None:
    """启动飞书 WebSocket 长连接（非阻塞，在后台线程运行）。

    Args:
        app_id: 所属模块显式提供的飞书应用 ID
        app_secret: 所属模块显式提供的飞书应用密钥
        event_handler: 事件处理器，默认使用全局 build_event_handler()
        name: 线程名称，用于区分多个 WS 实例
    """
    resolved_app_id = app_id
    resolved_app_secret = app_secret

    if not resolved_app_id or not resolved_app_secret:
        logger.warning(
            "[%s] 飞书 APP_ID/APP_SECRET 未配置，跳过长连接启动",
            name,
        )
        return

    stop_flag = threading.Event()
    _stop_flags[name] = stop_flag

    thread = threading.Thread(
        target=_run_ws_in_thread,
        args=(resolved_app_id, resolved_app_secret, event_handler, name, stop_flag),
        name=name,
        daemon=True,
    )
    _ws_threads[name] = thread
    thread.start()
    logger.info("[%s] 飞书 WebSocket 长连接线程已启动", name)


def stop_ws_client(name: str | None = None) -> None:
    """停止飞书 WebSocket 长连接。

    Args:
        name: 指定实例名称。为 None 时停止所有实例。
    """
    if name:
        flag = _stop_flags.pop(name, None)
        if flag:
            flag.set()
        _ws_threads.pop(name, None)
        logger.info("[%s] 飞书 WebSocket 长连接已请求停止", name)
    else:
        for n, flag in _stop_flags.items():
            flag.set()
            logger.info("[%s] 飞书 WebSocket 长连接已请求停止", n)
        _stop_flags.clear()
        _ws_threads.clear()


def _run_ws_in_thread(
    app_id: str,
    app_secret: str,
    event_handler: Any,
    name: str,
    stop_flag: threading.Event,
) -> None:
    """在独立线程中创建 event loop 并运行 WS client。"""
    import lark_oapi as lark  # type: ignore[import-untyped]
    import lark_oapi.ws as lark_ws  # type: ignore[import-untyped]

    if event_handler is None:
        from app.platform.integrations.feishu.event_handler import (
            build_event_handler,
        )

        event_handler = build_event_handler()

    # SDK 使用模块级 loop 变量，需替换为本线程的 loop
    thread_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(thread_loop)
    lark_ws.client.loop = thread_loop

    ws = lark_ws.Client(
        app_id=app_id,
        app_secret=app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
        auto_reconnect=True,
    )

    try:
        logger.info("[%s] 飞书 WebSocket 客户端正在连接...", name)
        ws.start()
    except Exception:
        logger.exception("[%s] 飞书 WebSocket 客户端异常退出", name)
    finally:
        thread_loop.close()


class FeishuWsClient:
    """单个飞书应用的 WebSocket 长连接（card.action.trigger 同步回调）。"""

    def __init__(
        self,
        name: str = "feishu-ws",
        card_action_handler: CardActionHandler | None = None,
        other_event_dispatcher: OtherEventDispatcher | None = None,
    ) -> None:
        self.name = name
        self._card_action_handler = card_action_handler
        self._other_event_dispatcher = (
            other_event_dispatcher or _default_other_event_dispatcher
        )
        self._stop: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None
        self._ping_interval: int = 90

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, app_id: str, app_secret: str) -> None:
        """启动长连接（非阻塞，在当前 event loop 中运行）。"""
        if not app_id or not app_secret:
            logger.warning("[%s] 飞书 APP_ID/APP_SECRET 未配置，跳过", self.name)
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_ws(app_id, app_secret))
        logger.info("[%s] 飞书 WebSocket 长连接已启动", self.name)

    def stop(self) -> None:
        if self._stop:
            self._stop.set()
        logger.info("[%s] 飞书 WebSocket 长连接已请求停止", self.name)

    async def _get_ws_url(self, app_id: str, app_secret: str) -> tuple[str | None, int]:
        """获取 WebSocket URL + service_id。"""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                WS_ENDPOINT_URL,
                json={"AppID": app_id, "AppSecret": app_secret},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    url = data.get("data", {}).get("URL", "")
                    q = parse_qs(urlparse(url).query)
                    service_id_str = q.get("service_id", ["0"])[0]
                    service_id = int(service_id_str) if service_id_str else 0
                    client_config = data.get("data", {}).get("ClientConfig", {})
                    if isinstance(client_config, dict):
                        interval = client_config.get("PingInterval", 0)
                        if interval > 0:
                            self._ping_interval = interval
                    logger.info(
                        "[%s] 飞书 WS URL 获取成功, service_id=%s, ping=%s",
                        self.name,
                        service_id,
                        self._ping_interval,
                    )
                    return url, service_id
                logger.error(
                    "[%s] 飞书 WS URL 获取失败: code=%s msg=%s",
                    self.name,
                    data.get("code"),
                    data.get("msg"),
                )
        return None, 0

    def _build_ping_frame(self, service_id: int) -> bytes:
        from lark_oapi.ws.const import HEADER_TYPE  # type: ignore[import-untyped]
        from lark_oapi.ws.enum import (  # type: ignore[import-untyped]
            FrameType,
            MessageType,
        )
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame  # type: ignore[import-untyped]

        frame = Frame()
        header = frame.headers.add()
        header.key = HEADER_TYPE
        header.value = MessageType.PING.value
        frame.service = service_id
        frame.method = FrameType.CONTROL.value
        frame.SeqID = 0
        frame.LogID = 0
        return bytes(frame.SerializeToString())

    def _build_ack_frame(self, frame: Any, biz_rt: int) -> bytes:
        from lark_oapi.ws.const import HEADER_BIZ_RT

        header = frame.headers.add()
        header.key = HEADER_BIZ_RT
        header.value = str(biz_rt)
        return bytes(frame.SerializeToString())

    async def _ping_loop(self, ws: Any, service_id: int) -> None:
        while self._stop is not None and not self._stop.is_set():
            try:
                await ws.send(self._build_ping_frame(service_id))
            except Exception:
                return
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._ping_interval)
                return
            except TimeoutError:
                pass

    async def _handle_frame(self, ws: Any, message: bytes) -> None:
        """处理 protobuf 帧。"""
        try:
            from lark_oapi.ws.client import _get_by_key  # type: ignore[import-untyped]
            from lark_oapi.ws.const import HEADER_TYPE
            from lark_oapi.ws.enum import FrameType, MessageType
            from lark_oapi.ws.pb.pbbp2_pb2 import Frame

            frame = Frame()
            frame.ParseFromString(message)

            ft = FrameType(frame.method)
            if ft == FrameType.CONTROL:
                return

            if ft == FrameType.DATA:
                start_ms = int(round(time.time() * 1000))
                type_val = _get_by_key(frame.headers, HEADER_TYPE)
                msg_type = MessageType(type_val)

                if msg_type == MessageType.EVENT:
                    event = json.loads(frame.payload.decode("utf-8"))
                    event_type = event.get("header", {}).get("event_type", "")
                    logger.info("[%s] 飞书收到事件: type=%s", self.name, event_type)

                    resp: dict[str, Any] = {"code": 200}

                    if event_type == "card.action.trigger":
                        # 同步等待处理结果（2.9 秒超时）
                        try:
                            result = None
                            if self._card_action_handler:
                                result = await asyncio.wait_for(
                                    self._card_action_handler(event),
                                    timeout=2.9,
                                )
                        except TimeoutError:
                            logger.warning("[%s] 卡片操作超时", self.name)
                            result = None

                        if result and isinstance(result, dict):
                            card_json = json.dumps(result, ensure_ascii=False)
                            resp = {
                                "code": 200,
                                "data": base64.b64encode(
                                    card_json.encode("utf-8")
                                ).decode("ascii"),
                            }
                    else:
                        # 异步分发其他事件
                        asyncio.create_task(
                            self._other_event_dispatcher(event_type, event)
                        )

                    frame.payload = json.dumps(resp, ensure_ascii=False).encode("utf-8")

                end_ms = int(round(time.time() * 1000))
                ack = self._build_ack_frame(frame, end_ms - start_ms)
                await ws.send(ack)
        except Exception:
            logger.exception("[%s] 飞书帧处理失败", self.name)

    async def _run_ws(self, app_id: str, app_secret: str) -> None:
        """主 WebSocket 连接循环。"""
        attempt = 0
        while self._stop is not None and not self._stop.is_set():
            try:
                ws_url, service_id = await self._get_ws_url(app_id, app_secret)
                if not ws_url:
                    attempt += 1
                    logger.warning(
                        "[%s] 飞书 WS URL 获取失败 (%d/3)",
                        self.name,
                        attempt,
                    )
                    await asyncio.sleep(10)
                    continue

                ssl_context = ssl.create_default_context()
                async with websockets.connect(
                    ws_url,
                    ssl=ssl_context,
                    max_size=2**23,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                ) as ws:
                    logger.info(
                        "[%s] 飞书 WS 已连接 (service_id=%s)",
                        self.name,
                        service_id,
                    )
                    attempt = 0

                    ping_task = asyncio.create_task(self._ping_loop(ws, service_id))
                    try:
                        while self._stop is not None and not self._stop.is_set():
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=180)
                            except TimeoutError:
                                continue
                            if isinstance(msg, bytes):
                                await self._handle_frame(ws, msg)
                    finally:
                        ping_task.cancel()
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed as e:
                attempt += 1
                logger.warning("[%s] 飞书 WS 断开: %s (%d/3)", self.name, e, attempt)
            except Exception:
                attempt += 1
                logger.exception("[%s] 飞书 WS 异常 (%d/3)", self.name, attempt)

            if attempt >= 3:
                logger.error("[%s] 飞书 WS 连续失败 3 次，停止重连", self.name)
                break
            if attempt > 0:
                await asyncio.sleep(5)


async def _default_other_event_dispatcher(
    event_type: str, event: dict[str, Any]
) -> None:
    """异步分发非卡片事件（如消息接收）。"""
    if event_type == "im.message.receive_v1":
        try:
            # 新线平台事件处理器可能未提供原始消息入口（供平台连接使用），
            # 人事专属连接正常只收卡片动作，缺失时静默跳过
            from app.platform.integrations.feishu import event_handler as _eh

            raw_handler = getattr(_eh, "_on_message_receive_raw", None)
            if raw_handler is not None:
                await raw_handler(event)
        except Exception:
            logger.exception("消息事件处理失败")
