"""Authenticated download proxy for module-scoped uploaded files.

The old public ``/uploads`` static mount made every local upload enumerable by
URL.  Files are now served only after validating the storage key and the
requesting user's module read permission.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.storage import get_object, is_enabled
from app.platform.identity.deps import RequiredUser
from app.platform.identity.rbac import resolve_user_permissions
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


async def _require_module_read(
    module: str,
    user: RequiredUser,
    db: AsyncSession,
) -> None:
    settings = get_settings()
    if settings.effective_module_access_mode == "all" or user.role == "admin":
        return
    permissions = await resolve_user_permissions(db, user.id)
    if "*" not in permissions and f"{module}:read" not in permissions:
        raise HTTPException(status_code=403, detail="无权读取该模块文件")


@router.get("/{module}/{object_key:path}", summary="授权下载模块文件")
async def download_module_file(
    module: str,
    object_key: str,
    user: RequiredUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    safe_key = _validate_key(module, object_key)
    await _require_module_read(module, user, db)

    content: bytes | None = None
    content_type = mimetypes.guess_type(safe_key)[0] or "application/octet-stream"
    if is_enabled():
        stored = get_object(module, safe_key)
        if stored is not None:
            content, content_type = stored
    if content is None:
        root = Path(get_settings().UPLOAD_DIR).resolve()
        candidate = (root / module / safe_key).resolve()
        try:
            candidate.relative_to(root / module)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="文件路径非法") from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        content = candidate.read_bytes()

    filename = Path(safe_key).name.replace("\r", "").replace("\n", "")
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
