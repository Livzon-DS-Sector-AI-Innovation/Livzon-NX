"""Quality 模块上传文件读取工具：先校验声明大小、分块读取，防止超大文件全量入内存。"""

from fastapi import UploadFile

from app.core.upload_security import read_upload_secure


async def read_upload_with_limit(
    file: UploadFile,
    max_bytes: int,
    what: str = "文件",
    *,
    allowed_extensions: set[str] | None = None,
    allowed_mimes: set[str] | None = None,
) -> bytes:
    """读取上传内容；声明大小或实际大小超限立即拒绝（413）。"""
    _, content = await read_upload_secure(
        file,
        max_bytes=max_bytes,
        allowed_extensions=allowed_extensions,
        allowed_mimes=allowed_mimes,
        what=what,
    )
    return content
