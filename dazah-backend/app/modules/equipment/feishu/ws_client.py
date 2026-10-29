"""设备模块飞书 WebSocket 客户端 — 原生 WebSocket 实现。

使用 raw websockets 连接飞书长连接，避免 lark-oapi SDK 的全局 loop 冲突。
完整实现飞书 WS 协议：protobuf PING 心跳 + DATA 帧 ACK 回复。
"""

import asyncio
import json
import logging
import re
import ssl
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import websockets

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

FEISHU_DOMAIN = "https://open.feishu.cn"
WS_ENDPOINT_URL = f"{FEISHU_DOMAIN}/callback/ws/endpoint"

_stop: asyncio.Event | None = None
_ping_interval: int = 120


async def _get_ws_url_and_config() -> tuple[str | None, str]:
    """获取 WS URL 并解析 service_id。返回 (url, service_id)。"""
    app_id = settings.EQUIPMENT_FEISHU_APP_ID
    app_secret = settings.EQUIPMENT_FEISHU_APP_SECRET

    if not app_id or not app_secret:
        logger.error("设备机器人 APP_ID/APP_SECRET 未配置")
        return None, ""

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            WS_ENDPOINT_URL,
            json={"AppID": app_id, "AppSecret": app_secret},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                url = data.get("data", {}).get("URL", "")
                # 从 URL 参数中提取 service_id
                q = parse_qs(urlparse(url).query)
                service_id = q.get("service_id", ["0"])[0]
                # 读取 server 下发的 ping 间隔配置
                client_config = data.get("data", {}).get("ClientConfig", {})
                global _ping_interval
                if isinstance(client_config, dict):
                    interval = client_config.get("PingInterval", 0)
                    if interval > 0:
                        _ping_interval = interval
                logger.info(
                    "设备机器人 WS URL 获取成功, service_id=%s, ping_interval=%s",
                    service_id,
                    _ping_interval,
                )
                return url, service_id
            logger.error(
                "设备机器人获取 WS URL 失败: code=%s msg=%s",
                data.get("code"),
                data.get("msg"),
            )
        else:
            logger.error(
                "设备机器人获取 WS URL HTTP 错误: %s",
                resp.status_code,
            )
    return None, ""


def _build_ping_frame(service_id: int) -> bytes:
    """构建 protobuf PING 帧。"""
    from lark_oapi.ws.const import HEADER_TYPE  # type: ignore[import-untyped]
    from lark_oapi.ws.enum import FrameType, MessageType  # type: ignore[import-untyped]
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


async def _ping_loop(ws: Any, service_id: int) -> None:
    """定期发送 protobuf PING 帧保持连接。"""
    stop_event = _stop
    if stop_event is None:
        return
    while not stop_event.is_set():
        try:
            ping_data = _build_ping_frame(service_id)
            await ws.send(ping_data)
            logger.debug("设备机器人 PING 已发送")
        except Exception as e:
            logger.warning("设备机器人 PING 失败: %s", e)
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_ping_interval)
            return
        except TimeoutError:
            pass


def _build_ack_frame(frame: Any, biz_rt: int) -> bytes:
    """构建 DATA 帧的 ACK 回复。"""
    from lark_oapi.ws.const import HEADER_BIZ_RT

    header = frame.headers.add()
    header.key = HEADER_BIZ_RT
    header.value = str(biz_rt)

    ack_resp = json.dumps({"code": 200})
    frame.payload = ack_resp.encode("utf-8")
    return bytes(frame.SerializeToString())


async def start_equipment_ws() -> None:
    """启动设备模块飞书 WebSocket 连接（asyncio task）。"""
    global _stop
    _stop = asyncio.Event()

    if not settings.EQUIPMENT_FEISHU_WS_ENABLED:
        logger.info("设备机器人 WS 已禁用 (EQUIPMENT_FEISHU_WS_ENABLED=false)，跳过")
        return

    app_id = settings.EQUIPMENT_FEISHU_APP_ID
    app_secret = settings.EQUIPMENT_FEISHU_APP_SECRET

    if not app_id or not app_secret:
        logger.warning("设备机器人凭证未配置，跳过 WebSocket 启动")
        return

    logger.info("启动设备模块飞书 WebSocket (app_id=%s)", app_id)

    while not _stop.is_set():
        try:
            ws_url, service_id_str = await _get_ws_url_and_config()
            if not ws_url:
                logger.error("设备机器人无法获取 WS URL，10 秒后重试")
                await asyncio.sleep(10)
                continue

            service_id = int(service_id_str) if service_id_str else 0
            ssl_context = ssl.create_default_context()

            async with websockets.connect(
                ws_url,
                ssl=ssl_context,
                max_size=2**23,
                ping_interval=None,  # 用 protobuf PING 代替 WS ping
                ping_timeout=None,
                close_timeout=5,
            ) as ws:
                logger.info("设备机器人 WebSocket 已连接")

                # 启动 protobuf PING 心跳
                ping_task = asyncio.create_task(
                    _ping_loop(ws, service_id),
                )

                try:
                    while not _stop.is_set():
                        try:
                            message = await asyncio.wait_for(
                                ws.recv(),
                                timeout=180,
                            )
                        except TimeoutError:
                            continue

                        if isinstance(message, bytes):
                            await _handle_binary_message(ws, message)
                finally:
                    ping_task.cancel()

        except asyncio.CancelledError:
            break
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(
                "设备机器人 WebSocket 连接关闭: %s，5 秒后重连",
                e,
            )
            await asyncio.sleep(5)
        except Exception:
            logger.exception("设备机器人 WebSocket 异常，10 秒后重连")
            await asyncio.sleep(10)

        try:
            await asyncio.wait_for(_stop.wait(), timeout=5)
        except TimeoutError:
            pass

    logger.info("设备机器人 WebSocket 客户端已停止")


async def _handle_binary_message(ws: Any, message: bytes) -> None:
    """处理 protobuf 帧（区分 CONTROL 和 DATA）。"""
    try:
        from lark_oapi.ws.client import _get_by_key  # type: ignore[import-untyped]
        from lark_oapi.ws.const import HEADER_TYPE
        from lark_oapi.ws.enum import FrameType, MessageType
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame

        frame = Frame()
        frame.ParseFromString(message)

        ft = FrameType(frame.method)

        if ft == FrameType.CONTROL:
            # CONTROL 帧：PING/PONG，仅记录
            try:
                type_val = _get_by_key(frame.headers, HEADER_TYPE)
                logger.debug("设备机器人 CONTROL 帧: %s", type_val)
            except Exception:
                pass
            return

        if ft == FrameType.DATA:
            import time

            start_ms = int(round(time.time() * 1000))
            type_val = _get_by_key(frame.headers, HEADER_TYPE)
            msg_type = MessageType(type_val)

            if msg_type == MessageType.EVENT:
                event = json.loads(frame.payload.decode("utf-8"))
                await _dispatch_event(event)
            elif msg_type == MessageType.CARD:
                # 派单卡片按钮回调（长连接送达，无需公网地址）
                card_payload = json.loads(frame.payload.decode("utf-8"))
                await _dispatch_card_action(frame, ws, card_payload, start_ms)
                return
            else:
                logger.info("设备机器人 DATA 帧: type=%s", msg_type)

            # 发送 ACK
            end_ms = int(round(time.time() * 1000))
            ack_data = _build_ack_frame(frame, end_ms - start_ms)
            await ws.send(ack_data)

    except Exception:
        logger.exception(
            "设备机器人帧处理失败 (%d bytes) — 完整调用栈:",
            len(message),
        )


async def _dispatch_card_action(
    frame: Any, ws: Any, payload: dict[str, Any], start_ms: int
) -> None:
    """处理派单卡片按钮回调：执行业务后按卡片回调协议 ACK。"""
    import time

    from app.modules.equipment.service.work_order_feishu import handle_card_action

    try:
        response = await handle_card_action(payload)
    except Exception:
        logger.exception("卡片回调处理失败")
        response = {"code": 0}
    # 卡片回调的 ACK payload 即协议响应（toast/card 等）
    end_ms = int(round(time.time() * 1000))
    ack = _build_ack_frame_with_payload(frame, end_ms - start_ms, response)
    await ws.send(ack)


def _build_ack_frame_with_payload(
    frame: Any, biz_rt: int, payload: dict[str, Any]
) -> bytes:
    """构建携带自定义响应 payload 的 DATA 帧 ACK（卡片回调用）。"""
    import json as _json

    from lark_oapi.ws.const import HEADER_BIZ_RT

    header = frame.headers.add()
    header.key = HEADER_BIZ_RT
    header.value = str(biz_rt)
    frame.payload = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return bytes(frame.SerializeToString())


async def _dispatch_event(event: dict[str, Any]) -> None:
    """解析事件并分发给设备模块事件处理器。"""
    header = event.get("header", {})
    event_type = header.get("event_type", "")

    if not event_type:
        inner = event.get("event", {})
        event_type = inner.get("type", event.get("type", ""))

    if event_type == "im.message.receive_v1":
        event_data = event.get("event", event)
        await _handle_message_event(event_data)
    elif event_type == "card.action.trigger":
        # 卡片按钮回调走事件通道（需在事件订阅中添加卡片交互事件）
        event_data = event.get("event", event)
        await _handle_card_trigger_event(event_data)
    else:
        logger.info("设备机器人忽略事件: %s", event_type)


async def _handle_card_trigger_event(event_data: dict[str, Any]) -> None:
    """处理 card.action.trigger：派单卡片按钮点击。

    事件结构映射到统一的 handle_card_action（与 CARD 帧路径共用），
    其 ACK 由外层 EVENT 帧统一回复，按钮交互结果通过更新原卡片呈现。
    """
    from app.modules.equipment.service.work_order_feishu import handle_card_action

    action = event_data.get("action") or {}
    value = action.get("value") or {}
    act = value.get("act", "")
    if act not in ("accept", "complete", "photo_repair", "photo_cancel"):
        logger.info("忽略非维修卡片动作: %s", event_data.get("action", {}).get("tag"))
        return
    try:
        # 事件通道下"被点击卡片"的 message_id 在 context 里；提升到顶层，
        # 让 handle_card_action 更新被点的那张卡（私聊打回卡也有视觉反馈）
        payload = dict(event_data)
        context = event_data.get("context") or {}
        if not payload.get("open_message_id"):
            msg_id = str(context.get("open_message_id") or "")
            if msg_id:
                payload["open_message_id"] = msg_id
        await handle_card_action(payload)
    except Exception:
        logger.exception("卡片按钮处理失败")


def _mentions_bot(event_data: dict[str, Any]) -> bool:
    """群消息是否 @ 了机器人。

    飞书把被 @ 的实体放在 message.mentions，机器人 @ 也在此列。
    以「文本以首个 mention 占位符开头」判定指向机器人（"@机器人 指令"
    的常见形态）；@同事 开头还带指令文本的场景极少，可接受。
    """
    message = event_data.get("message", {})
    mentions = message.get("mentions") or []
    if not mentions:
        return False
    try:
        text = (json.loads(message.get("content") or "{}")).get("text", "")
    except (json.JSONDecodeError, TypeError):
        return False
    first_key = str(mentions[0].get("key", ""))
    return bool(first_key) and text.strip().startswith(first_key)


_GROUP_PHOTO_BUFFER_TTL_SECONDS = 5 * 60
_GROUP_PHOTO_BUFFER_KEY = "repair:photo:gbuf:{chat_id}:{open_id}"


async def _buffer_group_photo(
    chat_id: str, open_id: str, message_id: str, content: str
) -> None:
    """群内未 @机器人 的照片进入短时缓冲（每群每人保留最新一张）。

    照片消息无法携带 @，拍照报修在群里的触发方式为：
    先发照片，随后 @机器人 发「报修」（可带故障描述），两步配对。
    """
    try:
        image_key = json.loads(content).get("image_key", "")
    except (json.JSONDecodeError, TypeError):
        return
    if not image_key:
        return
    from app.core.redis import redis_client

    await redis_client.set(
        _GROUP_PHOTO_BUFFER_KEY.format(chat_id=chat_id, open_id=open_id),
        json.dumps({"message_id": message_id, "image_key": image_key}),
        ex=_GROUP_PHOTO_BUFFER_TTL_SECONDS,
    )


async def _take_buffered_group_photo(
    chat_id: str, open_id: str
) -> dict[str, Any] | None:
    """取出（并清除）群内照片缓冲；无缓冲返回 None。"""
    from app.core.redis import redis_client

    key = _GROUP_PHOTO_BUFFER_KEY.format(chat_id=chat_id, open_id=open_id)
    raw = await redis_client.get(key)
    if not raw:
        return None
    await redis_client.delete(key)
    try:
        data: dict[str, Any] = json.loads(raw)
        return data
    except (json.JSONDecodeError, TypeError):
        return None


_GROUP_TEXT_COMMAND_PREFIXES = ("报修", "拍照报修", "完成")
_GROUP_TEXT_COMMAND_EXACT = {
    "工单", "我的工单", "开始", "开始巡检", "提交", "确认提交",
    "跳过", "进度", "状态", "继续", "下一台", "下一个",
    "取消", "放弃", "退出", "返回", "帮助", "help", "?", "？",
}


async def _group_text_directed(
    event_data: dict[str, Any], open_id: str
) -> bool:
    """群内文字是否指向机器人（方案 Y：指令前缀天然过滤，正常聊天零误触）。

    满足其一即处理：@机器人；以「报修/完成」等指令开头；命中精确指令词；
    或发送人正处于选择会话中（机器人引导的多步对话不能被群门槛打断）。
    """
    if _mentions_bot(event_data):
        return True
    try:
        text = (
            json.loads(event_data.get("message", {}).get("content") or "{}")
        ).get("text", "")
    except (json.JSONDecodeError, TypeError):
        return False
    text = re.sub(r"@_user_\d+", "", text).strip()
    if text.startswith(_GROUP_TEXT_COMMAND_PREFIXES):
        return True
    if text in _GROUP_TEXT_COMMAND_EXACT:
        return True
    from app.modules.equipment.service.inspection_session import get_selection

    return bool(await get_selection(open_id))


async def _handle_message_event(event_data: dict[str, Any]) -> None:
    """处理 im.message.receive_v1 事件。"""
    message = event_data.get("message", {})
    sender = event_data.get("sender", {})
    sender_id = sender.get("sender_id", {})

    msg_type = message.get("message_type", "")
    message_id = message.get("message_id", "")
    open_id = sender_id.get("open_id", "")
    user_id = sender_id.get("user_id", "")
    chat_id = message.get("chat_id", "")
    chat_type = message.get("chat_type", "")
    content = message.get("content", "{}")

    logger.info(
        "设备机器人收到消息: type=%s, user_id=%s, open_id=%s, message_id=%s",
        msg_type,
        user_id,
        open_id,
        message_id,
    )

    # 群消息门槛（方案 Y）：
    # - 图片无法携带 @：一律进 5 分钟缓冲，等发送人「@机器人 报修」配对
    # - 文字由指令前缀天然过滤（报修/完成/工单等），正常聊天零误触、
    #   零消耗；扫码粘贴的「报修 …」文本一步直达，无需再打 @
    if chat_type == "group":
        if msg_type == "image":
            await _buffer_group_photo(chat_id, open_id, message_id, content)
            logger.info("群图片进入配对缓冲: message_id=%s", message_id)
            return
        if msg_type == "text" and not await _group_text_directed(
            event_data, open_id
        ):
            logger.info(
                "群消息非指令且未 @机器人，忽略: message_id=%s", message_id
            )
            return

    # 消息去重
    from app.core.redis import redis_client

    dedup_key = f"feishu:msg:{message_id}"
    is_new = await redis_client.set(dedup_key, "1", ex=120, nx=True)
    if not is_new:
        logger.info("重复消息已忽略: message_id=%s", message_id)
        return

    if msg_type == "image":
        try:
            content_data = json.loads(content)
            image_key = content_data.get("image_key", "")
        except (json.JSONDecodeError, TypeError):
            logger.error("无法解析图片消息内容: %s", content)
            return

        if not image_key:
            logger.error("图片消息缺少 image_key")
            return

        from app.modules.equipment.service.inspection_feishu import (
            process_feishu_image,
        )

        await process_feishu_image(
            user_id=user_id,
            open_id=open_id,
            message_id=message_id,
            image_key=image_key,
            chat_id=chat_id,
            chat_type=chat_type,
        )
    elif msg_type == "text":
        await _handle_text_command(
            user_id=user_id or "",
            open_id=open_id,
            union_id=sender_id.get("union_id", "") or "",
            chat_id=chat_id,
            chat_type=chat_type,
            content=content,
        )
    else:
        logger.info("忽略非图片/文本消息: type=%s", msg_type)


async def _handle_text_command(
    *,
    user_id: str,
    open_id: str,
    union_id: str = "",
    chat_id: str,
    chat_type: str,
    content: str,
) -> None:
    """处理文本消息 — 会话感知路由。"""
    try:
        content_data = json.loads(content)
        text = content_data.get("text", "").strip()
    except (json.JSONDecodeError, TypeError):
        return

    # 群聊中 @机器人 时，文本前缀为 @mention（如 "@_user_1" 或 "@设备助手"），需要去掉
    if text.startswith("@") and " " in text:
        text = text.split(" ", 1)[-1].strip()
    # @ 在消息任意位置（含末尾）都会留下 @_user_N 占位符，剔除避免污染故障描述
    text = re.sub(r"@_user_\d+", "", text).strip()

    # ── 0. 选择状态检查（数字输入匹配任务/工单列表）──
    from app.modules.equipment.service.inspection_session import (
        clear_selection,
        get_selection,
        get_session,
    )

    selection = await get_selection(open_id)
    if selection:
        if text in ("取消", "放弃", "cancel"):
            await clear_selection(open_id)
            from app.modules.equipment.feishu.notification import send_user_card

            await send_user_card(
                open_id=open_id,
                title="💡 提示",
                receive_id_type="open_id",
                content="已取消选择。",
            )
            return
        try:
            num = int(text)
            options = selection.get("options", [])
            opt = next((o for o in options if o.get("index") == num), None)
            if opt:
                select_type = selection.get("select_type", "")
                if select_type == "inspection":
                    # 不在这里 clear_selection — 让 process_feishu_text 自行处理
                    from app.modules.equipment.service.inspection_feishu import (
                        process_feishu_text,
                    )

                    await process_feishu_text(open_id, str(num), user_id=user_id)
                elif select_type == "work_order":
                    wo_no = opt.get("work_order_no", "")
                    wo_status = opt.get("status", "")
                    from app.modules.equipment.feishu.notification import send_user_card

                    if wo_status == "执行中":
                        await send_user_card(
                            open_id=open_id,
                            title=f"📋 工单 {wo_no}",
                            receive_id_type="open_id",
                            content=(
                                f"**{wo_no}** · {opt.get('order_type', '')}\n"
                                f"设备：{opt.get('equipment_name', '')}\n"
                                f"状态：{wo_status}\n\n"
                                f"发送「完成 {opt['index']} 描述」提交完成。"
                            ),
                        )
                    else:
                        await send_user_card(
                            open_id=open_id,
                            title=f"📋 工单 {wo_no}",
                            receive_id_type="open_id",
                            content=(
                                f"**{wo_no}** · {opt.get('order_type', '')}\n"
                                f"设备：{opt.get('equipment_name', '')}\n"
                                f"状态：{wo_status}"
                            ),
                        )
                return
        except ValueError:
            pass
        await send_user_card(
            open_id=open_id,
            title="💡 提示",
            receive_id_type="open_id",
            content="请输入有效数字选择，或回复「取消」放弃。",
        )
        return

    # ── 1. 巡检路由 ──
    _inspection_commands = {
        "开始",
        "开始巡检",
        "start",
        "提交",
        "确认",
        "确认提交",
        "submit",
        "ok",
        "好的",
        "跳过",
        "skip",
        "pass",
        "进度",
        "状态",
        "progress",
        "status",
        "继续",
        "下一台",
        "下一个",
        "next",
        "continue",
        "取消",
        "放弃",
        "取消提交",
        "cancel",
        "abort",
        "退出",
        "返回",
        "exit",
        "quit",
        "back",
        "帮助",
        "help",
        "?",
        "？",
        "修改",
        "修正",
    }

    session = await get_session(open_id)
    is_inspection_cmd = (
        text in _inspection_commands
        or text.startswith("修改")
        or text.startswith("修正")
    )

    if session or is_inspection_cmd:
        from app.modules.equipment.service.inspection_feishu import (
            process_feishu_text,
        )

        await process_feishu_text(open_id, text, user_id=user_id)
        return

    # ── 2. 工单等功能 ──
    from app.modules.equipment.feishu.notification import send_user_card

    if text in ("帮助", "help", "?", "？"):
        await send_user_card(
            open_id=open_id,
            title="🤖 设备助手使用说明",
            receive_id_type="open_id",
            content=(
                "**报修功能**\n"
                "发送「报修 车间 设备 故障情况」直接建单\n"
                "示例：`报修 201一车间 离心泵 密封漏了 紧急`\n"
                "群里先发设备照片，再发「拍照报修 故障情况」即可拍照报修\n\n"
                "**巡检功能**\n"
                "发送巡检照片可直接 AI 分析。\n"
                "发送「开始」进入逐台引导巡检。\n\n"
                "**工单功能**\n"
                "发送「工单」或「我的工单」查看工单列表\n"
                "发送「完成 工单号」提交完成执行中的工单\n"
                "发送「完成 序号 描述」也可按序号完成\n\n"
                "**示例**\n"
                "`报修 201一车间 离心泵 漏了`\n"
                "`完成 WO-20260615-0001`\n"
                "`完成 1 更换了密封圈`"
            ),
        )
    elif text.startswith(("报修", "拍照报修")):
        # 「拍照报修」归一化为「报修」前缀，配对/文字报修共用下游逻辑
        if text.startswith("拍照报修"):
            text = "报修" + text.removeprefix("拍照报修")
        # 群内「照片 + 报修」配对：5 分钟内发过的照片优先走拍照报修，
        # 文字剩余部分作为故障描述提示（视觉未识别到现象时兜底）
        if chat_type == "group":
            photo = await _take_buffered_group_photo(chat_id, open_id)
            if photo is not None:
                from app.modules.equipment.service.repair_photo import (
                    process_repair_photo,
                )

                await process_repair_photo(
                    user_id=user_id,
                    open_id=open_id,
                    message_id=photo["message_id"],
                    image_key=photo["image_key"],
                    chat_id=chat_id,
                    chat_type=chat_type,
                    fault_hint=text.removeprefix("报修").strip(),
                )
                return
        from app.modules.equipment.service.work_order_feishu import (
            create_repair_by_text,
        )

        await create_repair_by_text(
            user_id=user_id, open_id=open_id, text=text, union_id=union_id
        )
    elif text in ("工单", "我的工单"):
        from app.modules.equipment.service.work_order_feishu import (
            list_user_work_orders,
        )

        await list_user_work_orders(user_id=user_id, open_id=open_id)
    elif text.startswith("完成"):
        rest = text[2:].strip()
        if not rest:
            await send_user_card(
                open_id=open_id,
                title="💡 提示",
                receive_id_type="open_id",
                content="请输入工单号或序号，例如：`完成 WO-20260615-0001` 或 `完成 1`",
            )
            return

        parts = rest.split(" ", 1)
        first_arg = parts[0]
        detail = parts[1] if len(parts) > 1 else None

        # 尝试解析为数字索引（需要从 selection 缓存获取）
        try:
            idx = int(first_arg)
            # 查找缓存的工单列表
            wo_selection = await get_selection(open_id)
            if wo_selection and wo_selection.get("select_type") == "work_order":
                opts = wo_selection.get("options", [])
                match = next((o for o in opts if o.get("index") == idx), None)
                if match:
                    first_arg = match.get("work_order_no", first_arg)
        except ValueError:
            pass

        from app.modules.equipment.service.work_order_feishu import (
            complete_work_order_by_no,
        )

        await complete_work_order_by_no(
            user_id=user_id,
            open_id=open_id,
            work_order_no=first_arg,
            repair_detail=detail,
        )
    else:
        await send_user_card(
            open_id=open_id,
            title="💡 提示",
            receive_id_type="open_id",
            content=(
                "发送巡检照片可直接 AI 分析。\n"
                "发送「开始」进入逐台引导巡检。\n"
                "发送「工单」查看您的工单。\n"
                "发送「帮助」查看完整使用说明。"
            ),
        )


async def stop_equipment_ws() -> None:
    """停止设备模块 WebSocket 连接。"""
    global _stop
    if _stop:
        _stop.set()
