"""质量模块附件存储 / 编号共享 helper。

历史偏差（historical_deviations）与偏差工作台（deviation_workbench_reports）两个
service 共用同一套 doc/docx/wps → 标准 MD（保留表格/图片）转换与存储约定。本模块
收敛重复的文件存取、图片引用改写、编号生成与附件存储 key 计算，两个 service 通过
各自的存储子目录（subdir）与对象前缀复用，避免 Duplicated Code。
"""

from __future__ import annotations

import io
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.storage import (
    delete_object,
    get_object,
    upload_object,
)
from app.core.storage import (
    is_enabled as minio_enabled,
)

MD_IMAGE_REF_RE = re.compile(r"!\[image\]\((img_\d+\.[A-Za-z0-9]+)\)")
TEXT_MD_MIME = "text/markdown; charset=utf-8"


def local_upload_dir(subdir: str) -> Path:
    upload_dir = Path(get_settings().UPLOAD_DIR) / "quality" / subdir
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _safe_path(subdir: str, storage_key: str) -> str:
    root = local_upload_dir(subdir).resolve()
    path = (root / storage_key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AppException(message="非法文件路径") from exc
    if path == root:
        raise AppException(message="非法文件路径")
    return str(path)


def store_file(
    subdir: str, storage_key: str, content: bytes, content_type: str
) -> str:
    if minio_enabled():
        upload_object("quality", storage_key, content, len(content), content_type)
        return storage_key
    path = _safe_path(subdir, storage_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file_obj:
        file_obj.write(content)
    return storage_key


def read_file(subdir: str, storage_key: str) -> tuple[bytes, str] | None:
    if minio_enabled():
        return get_object("quality", storage_key)
    path = _safe_path(subdir, storage_key)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as file_obj:
        return file_obj.read(), "application/octet-stream"


def delete_file(subdir: str, storage_key: str) -> None:
    if minio_enabled():
        delete_object("quality", storage_key)
        return
    path = _safe_path(subdir, storage_key)
    if os.path.exists(path):
        os.remove(path)


def persisted_user_id(user_id: str) -> uuid.UUID | None:
    if user_id == "system":
        return None
    try:
        return uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return None


async def generate_code(db: AsyncSession, model: Any, prefix: str) -> str:
    """生成编号 {prefix}-YYYYMM###：按当月已存在编号递增（沿用 quality 惯例）。"""
    month = datetime.now(UTC).strftime("%Y%m")
    pattern = re.compile(rf"^{prefix}-{month}(\d{{3}})$")
    code_col = getattr(model, "code")
    result = await db.execute(
        select(code_col).where(
            code_col.like(f"{prefix}-{month}%"),
            getattr(model, "is_deleted").is_(False),
        )
    )
    max_seq = 0
    for code in result.scalars().all():
        match = pattern.match(code or "")
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return f"{prefix}-{month}{max_seq + 1:03d}"


def attachment_storage_keys(attachment: dict[str, Any]) -> list[str]:
    """附件涉及的全部存储 key（原件 + 转换 md + 图片资产），供删除/清理。"""
    keys = [attachment.get("storage_key") or ""]
    converted_key = attachment.get("converted_md_key")
    if converted_key and converted_key not in keys:
        keys.append(converted_key)
    for asset_key in attachment.get("asset_keys") or []:
        if asset_key and asset_key not in keys:
            keys.append(asset_key)
    return [key for key in keys if key]


def read_md_text(subdir: str, storage_key: str) -> str:
    """读取转换后标准 MD 文本（供 AI 上下文等）。"""
    stored = read_file(subdir, storage_key)
    if stored is None:
        return ""
    data, _ = stored
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


# ── 忠实 docx→Markdown 转换器（保留全部正文，用于历史偏差/偏差工作台附件预览）──
#
# 说明：文件目录使用的 convert_docx_content_to_md 面向公司 SOP 模板（首页仅留
# 名称/编号，正文按"序号列"表格 + 关键词进入），偏差报告类文档不符合该结构会被
# 判为首页而丢弃正文，导致预览无内容。这里提供通用逐块转换：按文档顺序遍历段落与
# 表格，标题按样式转 Markdown 标题层级，正文表格转 Markdown 表格，内嵌图片抽取为
# 独立对象（占位名 img_NNN.ext，由调用方存储并改写 URL）。.doc/.wps 先转 .docx。

_LEGACY_WORD_EXTS = {".doc", ".wps"}


@dataclass(slots=True)
class RenderedImage:
    name: str
    data: bytes
    content_type: str


_HEADING_RE = re.compile(r"heading\s*(\d)", re.IGNORECASE)


def _heading_level(style_name: str) -> int:
    """从段落样式名解析标题层级（Heading 1..9 / 标题 1..9）；非标题返回 0。"""
    if not style_name:
        return 0
    m = _HEADING_RE.search(style_name)
    if m:
        return min(int(m.group(1)), 6)
    m2 = re.search(r"标题\s*(\d)", style_name)
    if m2:
        return min(int(m2.group(1)), 6)
    return 0


def _cell_text(cell: Any) -> str:
    return re.sub(r"\s+", " ", (cell.text or "").strip()).replace("|", r"\|")


def _table_to_md(table: Table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [_cell_text(c) for c in row.cells]
        # 合并单元格去重相邻重复
        dedup: list[str] = []
        for val in cells:
            if not dedup or dedup[-1] != val:
                dedup.append(val)
        if any(dedup):
            rows.append(dedup)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(padded[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for r in padded[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def render_word_to_md(
    file_name: str, content: bytes
) -> tuple[str, list[RenderedImage]]:
    """将 word（.doc/.docx/.wps）忠实转为 Markdown，并返回内嵌图片。"""
    ext = Path(file_name).suffix.lower()
    if ext in _LEGACY_WORD_EXTS:
        from app.modules.quality.service.document_catalog_md import (
            convert_legacy_to_docx,
        )

        content = convert_legacy_to_docx(content, file_name)
    document = Document(io.BytesIO(content))
    images: list[RenderedImage] = []

    def para_images(para_el: Any) -> list[str]:
        names: list[str] = []
        for blip in para_el.iter(qn("a:blip")):
            r_id = blip.get(qn("r:embed"))
            part = document.part.related_parts.get(r_id) if r_id else None
            if part is None:
                continue
            suffix = Path(str(getattr(part, "partname", "img.png"))).suffix or ".png"
            name = f"img_{len(images):03d}{suffix}"
            images.append(
                RenderedImage(
                    name=name,
                    data=part.blob,
                    content_type=getattr(part, "content_type", "") or "image/png",
                )
            )
            names.append(name)
        return names

    blocks: list[str] = []
    for child in document.element.body.iterchildren():
        tag = child.tag
        if tag == qn("w:tbl"):
            table_md = _table_to_md(Table(child, document))
            if table_md:
                blocks.append(table_md)
        elif tag == qn("w:p"):
            para = Paragraph(child, document)
            text = (para.text or "").strip()
            style_name = para.style.name if para.style is not None else ""
            level = _heading_level(style_name or "")
            line = ("#" * level + " " if level else "") + text
            img_refs = " ".join(f"![image]({n})" for n in para_images(child))
            chunk = "\n\n".join(x for x in (line, img_refs) if x.strip())
            if chunk.strip():
                blocks.append(chunk)
    return "\n\n".join(blocks).strip(), images


# 偏差编号 PC-YYMMNNN（前 4 位=YYMM，后 3 位流水号）；兼容 PC2508001 / PC_2508001
_PC_CODE_RE = re.compile(r"PC[-_ ]?(\d{4})(\d{3})(?=\D|$)", re.IGNORECASE)


def parse_deviation_code_from_text(text: str | None) -> str | None:
    """从文本（文件名或正文）解析偏差编号，规范化为 PC-YYMMNNN；未命中返回 None。"""
    if not text:
        return None
    match = _PC_CODE_RE.search(text)
    if not match:
        return None
    return f"PC-{match.group(1)}{match.group(2)}"


def parse_deviation_code_from_filename(filename: str | None) -> str | None:
    return parse_deviation_code_from_text(filename)
