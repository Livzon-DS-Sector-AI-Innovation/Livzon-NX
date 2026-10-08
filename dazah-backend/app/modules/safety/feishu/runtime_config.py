"""安全模块飞书运行时配置（数据库单一事实源）。

设置页（安全管理 → 系统配置 → 飞书设置）维护 safety.feishu_app_settings，
本模块为安全模块飞书客户端链（client / bitable_client / event_client /
notification / bitable_handler / 卡片链接）提供统一的运行时读取入口。

放在 feishu/ 包内、仅依赖 core 与模块模型，避免与 service 层形成导入环。
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.core import database as core_database
from app.core.llm.encryption import decrypt_api_key
from app.core.llm.exceptions import LLMConfigError
from app.modules.safety.models import SafetyFeishuAppSettings

_CONFIG_MISSING_HINT = (
    "安全模块飞书配置缺失：请在 安全管理 → 系统配置 → 飞书设置 中保存应用凭证"
)


class SafetyFeishuConfigError(RuntimeError):
    """安全模块飞书配置缺失、未启用或密文无法解密。"""


@dataclass(frozen=True)
class SafetyFeishuRuntimeConfig:
    """解密后的运行时凭证快照（仅供进程内使用，禁止日志或响应输出）。"""

    app_id: str
    app_secret: str
    bitable_app_token: str
    bitable_hazard_table_id: str


def decrypt_stored_secret(encrypted: str | None) -> str:
    """解密存量 App Secret；密钥轮换导致解密失败时抛出可定位错误。"""
    if not encrypted:
        return ""
    try:
        return decrypt_api_key(encrypted)
    except LLMConfigError as exc:
        raise SafetyFeishuConfigError(
            "安全模块飞书 App Secret 无法解密（加密密钥已轮换），"
            "请在 安全管理 → 系统配置 → 飞书设置 中重新保存"
        ) from exc


def build_runtime_config(model: SafetyFeishuAppSettings) -> SafetyFeishuRuntimeConfig:
    """把配置行转换为解密后的运行时快照。"""
    return SafetyFeishuRuntimeConfig(
        app_id=(model.app_id or "").strip(),
        app_secret=decrypt_stored_secret(model.app_secret),
        bitable_app_token=(model.bitable_app_token or "").strip(),
        bitable_hazard_table_id=(model.bitable_hazard_table_id or "").strip(),
    )


async def load_safety_feishu_runtime_config(
    *, include_disabled: bool = False
) -> SafetyFeishuRuntimeConfig | None:
    """读取当前生效的飞书配置；未配置时返回 None。

    默认跳过 is_enabled=false 的配置（运行链路视为未配置）；
    include_disabled=True 供设置页诊断使用。
    """
    async with core_database.async_session_factory() as session:
        result = await session.execute(
            select(SafetyFeishuAppSettings)
            .where(SafetyFeishuAppSettings.is_deleted.is_(False))
            .order_by(SafetyFeishuAppSettings.updated_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
    if model is None:
        return None
    if not include_disabled and not model.is_enabled:
        return None
    return build_runtime_config(model)


async def require_safety_feishu_runtime_config() -> SafetyFeishuRuntimeConfig:
    """读取当前生效的飞书配置；缺失或未启用时抛 SafetyFeishuConfigError。"""
    config = await load_safety_feishu_runtime_config()
    if config is None:
        raise SafetyFeishuConfigError(_CONFIG_MISSING_HINT)
    if not config.app_id or not config.app_secret:
        raise SafetyFeishuConfigError(
            "安全模块飞书配置不完整（缺少 App ID / App Secret），"
            "请在 安全管理 → 系统配置 → 飞书设置 中补全后保存"
        )
    return config
