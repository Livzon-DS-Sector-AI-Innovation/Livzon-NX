"""Retired key-only downloads: business record APIs own attachment authorization."""

from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.platform.identity.deps import RequiredUser
from app.shared.module_registry import MODULES_BY_CODE

router = APIRouter(prefix="/uploads", tags=["文件访问"])


def _validate_key(module: str, object_key: str) -> str:
    if module not in MODULES_BY_CODE:
        raise HTTPException(status_code=404, detail="文件模块不存在")
    normalized = object_key.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(normalized) > 500
    ):
        raise HTTPException(status_code=400, detail="文件存储键非法")
    return "/".join(path.parts)


@router.get("/{module}/{object_key:path}", summary="拒绝无业务记录上下文的附件下载")
async def download_module_file(
    module: str,
    object_key: str,
    user: RequiredUser,
) -> Response:
    """Object keys never prove ownership; use the owning module's record API.

    This legacy route cannot recover a record/page scope reliably from a key.
    Fail closed for every caller, including admins, before touching storage.
    """
    _validate_key(module, object_key)
    raise HTTPException(status_code=403, detail="请通过附件所属业务记录的下载接口访问")
