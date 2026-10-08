"""安全模块专属飞书客户端。

凭证来自数据库配置（safety.feishu_app_settings，由
安全管理 → 系统配置 → 飞书设置 页面维护），与全局飞书集成完全隔离。
"""

import json as _json
import logging

import lark_oapi as lark  # type: ignore[import-untyped]

from app.modules.safety.feishu.runtime_config import (
    SafetyFeishuConfigError,
    require_safety_feishu_runtime_config,
)

logger = logging.getLogger(__name__)


async def get_safety_feishu_client() -> lark.Client:
    """获取安全模块专属的飞书客户端（每次调用读取当前生效配置）。"""
    config = await require_safety_feishu_runtime_config()
    return (
        lark.Client.builder()
        .app_id(config.app_id)
        .app_secret(config.app_secret)
        .domain(lark.FEISHU_DOMAIN)
        .app_type(lark.AppType.SELF)
        .build()
    )


async def get_safety_tenant_token(client: lark.Client | None = None) -> str:
    """获取安全模块飞书应用的 tenant_access_token。"""
    from lark_oapi.api.auth.v3 import (  # type: ignore[import-untyped]
        InternalTenantAccessTokenRequest,
        InternalTenantAccessTokenRequestBody,
    )

    config = await require_safety_feishu_runtime_config()
    if client is None:
        client = (
            lark.Client.builder()
            .app_id(config.app_id)
            .app_secret(config.app_secret)
            .domain(lark.FEISHU_DOMAIN)
            .app_type(lark.AppType.SELF)
            .build()
        )

    req = (
        InternalTenantAccessTokenRequest.builder()
        .request_body(
            InternalTenantAccessTokenRequestBody.builder()
            .app_id(config.app_id)
            .app_secret(config.app_secret)
            .build()
        )
        .build()
    )
    resp = await client.auth.v3.tenant_access_token.ainternal(req)
    if not resp.success():
        raise SafetyFeishuConfigError(
            f"获取安全模块飞书 tenant token 失败: code={resp.code}, msg={resp.msg}"
        )
    if resp.raw and resp.raw.content:
        data = _json.loads(resp.raw.content.decode("utf-8"))
        token = data.get("tenant_access_token", "")
        if not isinstance(token, str):
            raise SafetyFeishuConfigError("安全模块飞书 tenant token 格式无效")
        logger.debug("安全模块飞书 tenant token 获取成功")
        return token
    raise SafetyFeishuConfigError("安全模块飞书 tenant token 响应为空")
