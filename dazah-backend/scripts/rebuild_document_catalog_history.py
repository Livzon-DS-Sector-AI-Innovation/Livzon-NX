"""历史文件目录附件重建（旧线环境 dazah_sync 原地更新）。

背景：历史导入的 md 附件是早期转换产物，无表格、无图片引用；桌面
`莫小张` 目录是新版脚本（保留表格+图片）的验证产物。本脚本：

1. md 附件（约 2287 个）：按归一化文件名匹配桌面产物 → 上传其 `*_images`
   图片为独立对象 → md 内图片引用改写为附件内容接口 URL → 新 md 落存储
   （原 md 保留为可下载原件，converted_md_key 指向新 md）；
2. docx 附件（约 18 个）：直接用存储中的原始 docx 走平台 v2 管线重转
   （python-docx，无需 LibreOffice），替换旧转换产物并清理旧 md；
3. 每条目独立提交；更新前把受影响条目备份到 JSON；支持 --dry-run。

使用方法（宿主机，新线 venv）：
    .venv/Scripts/python.exe scripts/rebuild_document_catalog_history.py --dry-run
    .venv/Scripts/python.exe scripts/rebuild_document_catalog_history.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm.attributes import flag_modified

from app.modules.quality.models.document_catalog import DocumentEntry
from app.modules.quality.service.document_catalog_md import convert_word_attachment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rebuild_document_catalog")

DEFAULT_ENV_FILE = r"E:\工厂平台\dazah-backend\.env"
DEFAULT_STORAGE_ROOT = r"E:\工厂平台\dazah-backend\uploads\quality\document_catalog"
DEFAULT_SOURCE_DIR = r"C:\Users\Administrator\Desktop\莫小张"
BACKUP_DIR = Path(__file__).resolve().parent.parent / "data"

TEXT_MD_MIME = "text/markdown; charset=utf-8"
IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".emf": "application/octet-stream",
    ".wmf": "application/octet-stream",
}
# 桌面产物图片引用：![image](<base>_images/img_000.png)
SOURCE_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\(([^()]*)_images/([^()/]+)\)")
# v2 管线占位引用：![image](img_000.png)
PLACEHOLDER_IMAGE_REF_RE = re.compile(r"!\[image\]\((img_\d+\.[A-Za-z0-9]+)\)")


def normalize_name(name: str) -> str:
    """归一化文件名（去空白、统一全半角括号、小写），用于跨目录匹配。"""
    base = os.path.splitext(name.strip())[0]
    base = base.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", base).lower()


def load_database_url(env_file: Path) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(f"{env_file} 中未找到 DATABASE_URL")


def index_source_mds(source_dir: Path) -> dict[str, Path]:
    """归一化名 → 桌面产物 md 路径（重名取修改时间最新）。"""
    index: dict[str, Path] = {}
    for root, _dirs, files in os.walk(source_dir):
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            path = Path(root) / name
            key = normalize_name(name)
            existing = index.get(key)
            if existing is None or path.stat().st_mtime > existing.stat().st_mtime:
                index[key] = path
    return index


def object_path(storage_root: Path, key: str) -> Path:
    root = storage_root.resolve()
    path = (root / key).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"非法存储 key: {key}") from exc
    return path


def read_object(storage_root: Path, key: str) -> bytes | None:
    path = object_path(storage_root, key)
    if not path.is_file():
        return None
    return path.read_bytes()


def write_object(storage_root: Path, key: str, data: bytes) -> None:
    path = object_path(storage_root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def delete_object(storage_root: Path, key: str) -> None:
    path = object_path(storage_root, key)
    if path.is_file():
        path.unlink()


def image_url(entry_id: Any, key: str) -> str:
    from urllib.parse import quote

    return (
        f"/api/v1/quality/document-entries/{entry_id}"
        f"/attachments/{quote(key, safe='/')}/content"
    )


def upload_images(
    storage_root: Path,
    entry_id: Any,
    images: list[tuple[str, bytes]],
) -> tuple[list[str], dict[str, str]]:
    """上传图片对象，返回 (asset_keys, 图片名→URL 映射)。"""
    asset_keys: list[str] = []
    name_to_url: dict[str, str] = {}
    for name, data in images:
        key = f"document-catalog/attachments/{uuid.uuid4().hex}_{name}"
        write_object(storage_root, key, data)
        asset_keys.append(key)
        name_to_url[name] = image_url(entry_id, key)
    return asset_keys, name_to_url


def collect_source_images(images_dir: Path) -> list[tuple[str, bytes]]:
    images: list[tuple[str, bytes]] = []
    for path in sorted(images_dir.iterdir()):
        if path.is_file():
            images.append((path.name, path.read_bytes()))
    return images


def rewrite_md_images(
    md_text: str, name_to_url: dict[str, str], pattern: re.Pattern[str]
) -> str:
    def _sub(match: re.Match[str]) -> str:
        name = match.group(2) if pattern.groups >= 2 else match.group(1)
        url = name_to_url.get(name)
        return f"![image]({url})" if url else match.group(0)

    return pattern.sub(_sub, md_text)


async def rebuild_md_attachment(
    storage_root: Path,
    entry: DocumentEntry,
    attachment: dict[str, Any],
    source_index: dict[str, Path],
    *,
    dry_run: bool,
) -> tuple[str, str]:
    """md 附件：匹配桌面产物，上传图片并改写引用。"""
    file_name = attachment.get("file_name") or ""
    source_md = source_index.get(normalize_name(file_name))
    if source_md is None:
        return "unmatched", "桌面产物中未找到同名 md"
    if attachment.get("pipeline") == "v2":
        return "skip", "已处理过"

    md_text = source_md.read_text(encoding="utf-8", errors="replace")
    images_dir = source_md.parent / f"{source_md.stem}_images"
    images = collect_source_images(images_dir) if images_dir.is_dir() else []

    if dry_run:
        return "dry", f"将上传 {len(images)} 张图片（{len(md_text)} 字符）"

    asset_keys, name_to_url = upload_images(storage_root, entry.id, images)
    md_text = rewrite_md_images(md_text, name_to_url, SOURCE_IMAGE_REF_RE)

    new_md_key = (
        f"document-catalog/attachments/{uuid.uuid4().hex}_"
        f"{os.path.splitext(file_name)[0]}.md"
    )
    write_object(storage_root, new_md_key, md_text.encode("utf-8"))
    attachment["converted_md_key"] = new_md_key
    attachment["asset_keys"] = asset_keys
    attachment["pipeline"] = "v2"
    return "rebuilt", f"{len(asset_keys)} 张图片"


async def rebuild_docx_attachment(
    storage_root: Path,
    entry: DocumentEntry,
    attachment: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[str, str]:
    """docx 附件：用存储中的原始 docx 走 v2 管线重转。"""
    file_name = attachment.get("file_name") or ""
    storage_key = attachment.get("storage_key") or ""
    content = read_object(storage_root, storage_key)
    if content is None:
        return "fail", "原始 docx 在存储中缺失"

    try:
        md_text, images = await asyncio.to_thread(
            convert_word_attachment, file_name, content
        )
    except Exception as exc:  # noqa: BLE001 转换失败保持原样
        return "fail", f"转换失败：{exc}"

    if dry_run:
        return "dry", f"将重转并提取 {len(images)} 张图片"

    old_md_key = attachment.get("converted_md_key")
    images_data = [(image.name, image.data) for image in images]
    asset_keys, name_to_url = upload_images(storage_root, entry.id, images_data)
    md_text = rewrite_md_images(md_text, name_to_url, PLACEHOLDER_IMAGE_REF_RE)

    new_md_key = (
        f"document-catalog/attachments/{uuid.uuid4().hex}_"
        f"{os.path.splitext(file_name)[0]}.md"
    )
    write_object(storage_root, new_md_key, md_text.encode("utf-8"))
    attachment["converted"] = True
    attachment["converted_md_key"] = new_md_key
    attachment["asset_keys"] = asset_keys
    attachment["pipeline"] = "v2"
    attachment["_stale_md_key"] = (
        old_md_key if old_md_key and old_md_key != storage_key else ""
    )
    return "rebuilt", f"{len(asset_keys)} 张图片"


async def run(args: argparse.Namespace) -> int:
    storage_root = Path(args.storage_root)
    source_index = index_source_mds(Path(args.source_dir))
    logger.info("桌面产物索引：%d 个 md", len(source_index))

    database_url = load_database_url(Path(args.env_file))
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    stats = {"rebuilt": 0, "dry": 0, "skip": 0, "unmatched": 0, "fail": 0}
    unmatched_names: list[str] = []
    failed_names: list[str] = []
    backup: dict[str, Any] = {}
    processed = 0

    async with session_factory() as db:  # type: AsyncSession
        result = await db.execute(
            select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
        )
        entries = list(result.scalars().all())
        logger.info("未删除条目共 %d 个", len(entries))

        for entry in entries:
            attachments = list(entry.attachments or [])
            if not attachments:
                continue
            original = json.loads(json.dumps(entry.attachments))
            entry_touched = False
            for attachment in attachments:
                file_name = attachment.get("file_name") or ""
                ext = os.path.splitext(file_name)[1].lower()
                if ext == ".md":
                    status, note = await rebuild_md_attachment(
                        storage_root, entry, attachment, source_index,
                        dry_run=args.dry_run,
                    )
                elif ext in {".docx", ".doc", ".wps"}:
                    status, note = await rebuild_docx_attachment(
                        storage_root, entry, attachment, dry_run=args.dry_run
                    )
                else:
                    status, note = "skip", "非 md/word 附件"

                if status == "rebuilt":
                    entry_touched = True
                    processed += 1
                stats[status] = stats.get(status, 0) + 1
                if status == "unmatched":
                    unmatched_names.append(file_name)
                if status == "fail":
                    failed_names.append(f"{file_name}（{note}）")
                if status in {"rebuilt", "dry"}:
                    logger.info(
                        "[%s] entry=%s file=%s (%s)",
                        status, entry.code or entry.name, file_name, note,
                    )
                if args.limit is not None and processed >= args.limit:
                    break

            if entry_touched:
                backup[str(entry.id)] = original
                entry.attachments = attachments
                # 原地修改嵌套 dict 时新旧值相等，SQLAlchemy 不会发 UPDATE，
                # 必须显式标记 JSON 列为已修改
                flag_modified(entry, "attachments")
                await db.commit()
                for attachment in attachments:
                    stale = attachment.pop("_stale_md_key", "")
                    if stale:
                        try:
                            delete_object(storage_root, stale)
                        except Exception:  # noqa: BLE001 遗留孤儿不影响记录
                            logger.warning("清理旧 md 失败: key=%s", stale)
                if args.limit is not None and processed >= args.limit:
                    logger.info("达到 --limit=%d，提前结束", args.limit)
                    break

    await engine.dispose()
    if backup:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_DIR / f"document_catalog_attachments_backup_{stamp}.json"
        backup_path.write_text(
            json.dumps(backup, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        logger.info("已备份 %d 个条目的原始附件到 %s", len(backup), backup_path)
    logger.info("完成：%s", stats)
    if unmatched_names:
        logger.warning("未匹配（%d）：%s", len(unmatched_names), unmatched_names[:10])
    if failed_names:
        logger.warning("失败（%d）：%s", len(failed_names), failed_names[:10])
    return 0 if stats["fail"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只统计不写")
    parser.add_argument("--limit", type=int, default=None, help="最多处理 N 个附件")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--storage-root", default=DEFAULT_STORAGE_ROOT)
    parser.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
    args = parser.parse_args()

    if not args.dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("备份目录：%s", BACKUP_DIR)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
