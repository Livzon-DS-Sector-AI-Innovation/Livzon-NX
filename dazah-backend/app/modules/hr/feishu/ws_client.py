"""人事模块专属飞书应用 WebSocket 长连接。

人事审批卡片（合同审批/岗位调动）由人事自己的飞书应用发送，
按钮回调也就到达人事应用的事件订阅——本模块为该应用维持独立的
长连接（参照设备/安全模块先例），回调分发到人事卡片处理器。

平台应用的长连接（登录/消息）不受影响：两套连接互不干扰。
"""

import asyncio
import logging

from app.platform.integrations.feishu.ws_client import FeishuWsClient

logger = logging.getLogger(__name__)

_hr_ws_client: FeishuWsClient | None = None
_start_lock = asyncio.Lock()


async def _resolve_hr_ws_credentials() -> tuple[str, str] | None:
    """从人事 DB 配置解析长连接凭证；未配置/未启用时返回 None。"""
    from app.core.database import async_session_factory
    from app.modules.hr.feishu_settings_service import try_get_hr_feishu_app_credentials

    async with async_session_factory() as session:
        return await try_get_hr_feishu_app_credentials(session)


async def start_hr_ws_if_configured() -> bool:
    """读取人事 DB 凭证，已配置则启动/重启人事长连接。

    Returns:
        True 表示连接已（重新）启动；False 表示未配置或启动失败。
    """
    global _hr_ws_client
    async with _start_lock:
        credentials = await _resolve_hr_ws_credentials()
        if credentials is None:
            logger.info("[hr-feishu-ws] 人事飞书应用未配置，跳过长连接启动")
            return False
        app_id, app_secret = credentials

        if _hr_ws_client is not None and _hr_ws_client.running:
            _hr_ws_client.stop()

        from app.modules.hr.feishu.card_handler import handle_card_action

        _hr_ws_client = FeishuWsClient(
            name="hr-feishu-ws", card_action_handler=handle_card_action,
        )
        _hr_ws_client.start(app_id, app_secret)
        return True


def stop_hr_ws() -> None:
    """停止人事飞书长连接（应用关闭时调用）。"""
    if _hr_ws_client is not None:
        _hr_ws_client.stop()
