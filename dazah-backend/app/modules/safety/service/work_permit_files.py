"""作业票附件与证件附件存储：MinIO 优先、本地 uploads/safety 回退。

参照 hazchem.py 的 MSDS 存储策略（app.core.storage 按模块分 bucket），
存储 key 前缀区分业务（work_permit / work_certificate）。
"""

from __future__ import annotations

import logging
import uuid as uuid_module
from pathlib import Path

from app.core import storage
from app.core.config import get_settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

# 票面附图（盲板位置图/简图/示意图/照片）与证件扫描件
WORK_PERMIT_ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg"}
CERTIFICATE_ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg"}
WORK_PERMIT_MAX_BYTES = 30 * 1024 * 1024
CERTIFICATE_MAX_BYTES = 20 * 1024 * 1024

WORK_PERMIT_ATTACHMENT_CATEGORIES = {"blind_map", "sketch", "photo", "other"}


def _local_root(sub: str) -> Path:
    root = (Path(get_settings().UPLOAD_DIR) / "safety" / sub).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _local_path(sub: str, storage_key: str) -> Path:
    normalized = storage_key.replace("\\", "/")
    if normalized.startswith("uploads/"):
        return Path(normalized).resolve()
    root = _local_root(sub)
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AppException(message="非法文件路径") from exc
    if path == root:
        raise AppException(message="非法文件路径")
    return path


def store_object(
    sub: str, storage_key: str, content: bytes, content_type: str
) -> str:
    if storage.is_enabled():
        storage.upload_object(
            "safety", storage_key, content, len(content), content_type
        )
        return storage_key
    path = _local_path(sub, storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as file_obj:
        file_obj.write(content)
    return storage_key


def read_object(sub: str, storage_key: str) -> tuple[bytes, str] | None:
    if storage.is_enabled():
        found = storage.get_object("safety", storage_key)
        if found is not None:
            return found
    path = _local_path(sub, storage_key)
    if not path.exists():
        return None
    return path.read_bytes(), "application/octet-stream"


def delete_object(sub: str, storage_key: str) -> None:
    if storage.is_enabled():
        try:
            storage.delete_object("safety", storage_key)
        except Exception:
            logger.warning(
                "删除 MinIO 安全模块对象失败: key=%s", storage_key, exc_info=True
            )
    path = _local_path(sub, storage_key)
    if path.exists():
        path.unlink()


def build_permit_attachment_key(permit_id: str, file_ext: str) -> str:
    return (
        f"work_permit/{permit_id}_{uuid_module.uuid4().hex}{file_ext}"
    )


def build_certificate_file_key(certificate_id: str, file_ext: str) -> str:
    return (
        f"work_certificate/{certificate_id}_{uuid_module.uuid4().hex}{file_ext}"
    )


__all__ = [
    "CERTIFICATE_ALLOWED_EXTS",
    "CERTIFICATE_MAX_BYTES",
    "WORK_PERMIT_ALLOWED_EXTS",
    "WORK_PERMIT_ATTACHMENT_CATEGORIES",
    "WORK_PERMIT_MAX_BYTES",
    "build_certificate_file_key",
    "build_permit_attachment_key",
    "delete_object",
    "read_object",
    "store_object",
]
