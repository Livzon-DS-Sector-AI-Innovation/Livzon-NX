"""Registration API 公共辅助：认证校验等跨路由复用逻辑。"""

import shutil
import uuid

from app.core.deps import CurrentUser
from app.core.exceptions import AppException


def require_user(current_user: CurrentUser) -> uuid.UUID:
    """要求当前请求已登录，返回用户 ID（后端规范：所有业务 API 默认需要登录）。"""
    if not current_user:
        raise AppException(message="需要登录才能执行此操作", status_code=401)
    return current_user.id


def cleanup_export_dir(path: str) -> None:
    """导出完成后清理服务端临时导出目录（作为 FileResponse background 任务执行）。"""
    shutil.rmtree(path, ignore_errors=True)
