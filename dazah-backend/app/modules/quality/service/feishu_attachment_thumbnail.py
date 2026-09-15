"""飞书附件列表缩略图生成。

列表页缩略图端点使用：把原图缩放为小尺寸 JPEG 后返回，避免前端拉取原图
全量字节只为渲染 200×200 的单元格。缩略图字节复用附件两级缓存
（key_suffix 区分派生内容，与原图条目互不干扰）。

非图片附件不支持缩略图（前端对图片附件才会请求缩略图端点）。
生成失败时返回 None，路由转 400，前端回退到原图展示。
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service.inspection_feishu_crud import (
    get_inspection_feishu_attachment_content,
)
from app.platform.integrations.feishu.attachment_cache import get_attachment_cache

logger = logging.getLogger(__name__)

DEFAULT_MAX_WIDTH = 200
DEFAULT_MAX_HEIGHT = 200
_MIN_DIMENSION = 16
_MAX_DIMENSION = 512

THUMBNAIL_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})
JPEG_QUALITY = 80


def _clamp_dimension(value: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(_MIN_DIMENSION, min(_MAX_DIMENSION, number))


def build_thumbnail(
    content: bytes,
    filename: str,
    max_width: int,
    max_height: int,
) -> bytes | None:
    """把图片字节缩放为 max_width×max_height 的 JPEG；非图片或失败返回 None。"""
    ext = Path(filename).suffix.lower()
    if ext not in THUMBNAIL_IMAGE_EXTS:
        return None
    try:
        with Image.open(io.BytesIO(content)) as opened:
            source: Image.Image = opened
            source.thumbnail((max_width, max_height))
            rgb: Image.Image
            if source.mode in ("RGBA", "LA", "P"):
                rgba = source.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                rgb = background
            else:
                rgb = source.convert("RGB")
            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return buf.getvalue()
    except Exception:
        logger.warning("附件缩略图生成失败: %s", filename, exc_info=True)
        return None


async def get_attachment_thumbnail(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
    file_token: str,
    max_width: int = DEFAULT_MAX_WIDTH,
    max_height: int = DEFAULT_MAX_HEIGHT,
) -> tuple[bytes, str, str] | None:
    """返回缩略图 (content, content_type, filename)；非图片/生成失败返回 None。

    原图字节和缩略图字节分别缓存：缩略图 key_suffix 含尺寸，同附件不同
    尺寸各自独立缓存。缓存未命中时回源飞书下载原图（本身走原图缓存）。
    """
    width = _clamp_dimension(max_width, DEFAULT_MAX_WIDTH)
    height = _clamp_dimension(max_height, DEFAULT_MAX_HEIGHT)
    cache = get_attachment_cache()
    key_suffix = f"thumb:{width}x{height}"

    async def _fetch() -> tuple[bytes, str, str] | None:
        content, _content_type, filename = (
            await get_inspection_feishu_attachment_content(
                db, entity_code, record_id, file_token
            )
        )
        thumb = build_thumbnail(content, filename, width, height)
        if thumb is None:
            return None
        stem = Path(filename).stem or "attachment"
        return thumb, "image/jpeg", f"{stem}.jpg"

    return await cache.get_or_fetch(
        entity_code,
        record_id,
        file_token,
        _fetch,
        key_suffix=key_suffix,
    )
