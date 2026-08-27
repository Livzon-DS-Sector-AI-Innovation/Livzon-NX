"""Quality module API shared dependencies."""

import logging
import uuid
from urllib.parse import quote

from app.core.deps import CurrentUser
from app.core.exceptions import AppException
from app.core.redis import acquire_lock, release_lock

logger = logging.getLogger(__name__)

# 台账 Word 导入文件大小上限（与文件管理模块保持一致）
IMPORT_FILE_MAX_SIZE = 20 * 1024 * 1024


def current_user_id(user_id: uuid.UUID | str) -> str:
    """将 require_user 返回的用户 ID 转为字符串（用于审计追踪）。"""
    return str(user_id)


def build_docx_download_headers(
    filename_utf8: str, fallback_ascii: str
) -> dict[str, str]:
    encoded = quote(filename_utf8)
    return {
        "Content-Disposition": (
            f"attachment; filename={fallback_ascii}; filename*=UTF-8''{encoded}"
        )
    }


def require_user(current_user: CurrentUser) -> uuid.UUID:
    """业务接口默认要求登录：已登录返回用户 ID，未登录抛 401。"""
    if not current_user:
        raise AppException(message="需要登录才能执行此操作", status_code=401)
    return current_user.id


async def try_acquire_action_lock(scope: str, timeout: int = 60) -> bool:
    """短期幂等守卫：防止快速连点重复触发同步/生成类操作。

    返回 True 表示拿到锁；Redis 不可用时降级放行（不阻塞业务）。
    """
    try:
        return await acquire_lock(f"quality:{scope}", timeout=timeout)
    except Exception:
        logger.warning(
            "quality action lock unavailable, degrade to pass-through",
            extra={"module_name": "quality", "scope": scope},
        )
        return True


async def release_action_lock(scope: str) -> None:
    try:
        await release_lock(f"quality:{scope}")
    except Exception:
        logger.debug(
            "quality action lock release skipped",
            extra={"module_name": "quality", "scope": scope},
        )
