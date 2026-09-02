"""历史 word 附件按 v2 模板管线重转（补表格与图片）。

使用方法（在 app 容器内执行）：
    .venv/bin/python scripts/reconvert_document_catalog_word.py --dry-run
    .venv/bin/python scripts/reconvert_document_catalog_word.py           # 实跑
    .venv/bin/python scripts/reconvert_document_catalog_word.py --force   # 含已 v2 的
    .venv/bin/python scripts/reconvert_document_catalog_word.py --limit 3 # 限量试跑

行为：
- 遍历全部未删除文件目录条目，处理扩展名为 .doc/.docx/.wps 的附件；
- 每个附件重新走模板管线：生成新标准 MD、提取图片对象
  （md 中图片引用改写为附件内容接口 URL），更新 attachment 记录的
  converted_md_key/asset_keys 并打 pipeline=v2 标记；
- 新产物先落存储，条目提交成功后再清理旧转换 MD 与旧图片对象
  （失败仅遗留孤儿对象，不影响记录）；
- 转换失败保持原样（原文件仍可下载/预览），计入失败清单；
- 每个条目独立提交，单条失败不影响其他条目。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from typing import Any

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import async_session_factory
from app.core.storage import is_enabled as minio_enabled
from app.modules.quality.models.document_catalog import DocumentEntry
from app.modules.quality.service import document_catalog_attachment as att
from app.modules.quality.service.document_catalog_md import convert_word_attachment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reconvert_document_catalog")

WORD_EXTS = {".doc", ".docx", ".wps"}
TEXT_MD_MIME = "text/markdown; charset=utf-8"


async def _reconvert_one(
    entry: DocumentEntry, attachment: dict[str, Any], *, dry_run: bool, force: bool
) -> tuple[str, str]:
    """重转单个 word 附件，返回 (状态, 说明)。状态：converted/skip/fail。"""
    file_name = attachment.get("file_name") or ""
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in WORD_EXTS:
        return "skip", "非 word 附件"
    if attachment.get("pipeline") == "v2" and not force:
        return "skip", "已是 v2"
    storage_key = attachment.get("storage_key") or ""
    stored = att._read_file(storage_key)
    if stored is None:
        return "fail", "原文件在存储中缺失"

    try:
        md_text, images = await asyncio.to_thread(
            convert_word_attachment, file_name, stored[0]
        )
    except Exception as exc:  # noqa: BLE001 转换失败保持原样并继续
        return "fail", f"转换失败：{exc}"

    if dry_run:
        return "dry", f"将重转，提取 {len(images)} 张图片"

    stored_new: list[str] = []
    try:
        name_to_url: dict[str, str] = {}
        asset_keys: list[str] = []
        for image in images:
            asset_key = (
                f"document-catalog/attachments/{uuid.uuid4().hex}_{image.name}"
            )
            att._store_file(asset_key, image.data, image.content_type)
            stored_new.append(asset_key)
            asset_keys.append(asset_key)
            name_to_url[image.name] = att._attachment_asset_url(entry.id, asset_key)
        md_text = att._MD_IMAGE_REF_RE.sub(
            lambda m: f"![image]({name_to_url[m.group(1)]})", md_text
        )
        md_key = (
            f"document-catalog/attachments/{uuid.uuid4().hex}_"
            f"{os.path.splitext(file_name)[0]}.md"
        )
        att._store_file(md_key, md_text.encode("utf-8"), TEXT_MD_MIME)
        stored_new.append(md_key)
    except Exception as exc:  # noqa: BLE001 存储失败回滚本轮新对象
        for key in reversed(stored_new):
            try:
                att._delete_file(key)
            except Exception:  # noqa: BLE001
                logger.exception("清理重转新对象失败: object_key=%s", key)
        return "fail", f"存储失败：{exc}"

    old_md_key = attachment.get("converted_md_key")
    old_asset_keys = list(attachment.get("asset_keys") or [])
    # 旧产物标记就地保存在记录上，条目提交成功后由 _cleanup_superseded 删除
    attachment["_old_md_key"] = old_md_key or ""
    attachment["_old_asset_keys"] = old_asset_keys
    attachment["converted"] = True
    attachment["converted_md_key"] = md_key
    attachment["asset_keys"] = asset_keys
    attachment["pipeline"] = "v2"
    return "converted", f"提取 {len(images)} 张图片"


def _cleanup_superseded(attachment: dict[str, Any], storage_key: str) -> None:
    """记录提交成功后，删除被替换的旧转换 MD 与旧图片对象（尽力而为）。"""
    new_md_key = attachment.get("converted_md_key")
    stale: list[str] = []
    old_md_key = str(attachment.pop("_old_md_key", "") or "")
    if old_md_key and old_md_key not in {storage_key, new_md_key}:
        stale.append(old_md_key)
    for old_key in attachment.pop("_old_asset_keys", None) or []:
        ban = {storage_key, new_md_key}
        if old_key and old_key not in stale and old_key not in ban:
            stale.append(old_key)
    for key in stale:
        try:
            att._delete_file(key)
        except Exception:  # noqa: BLE001 遗留孤儿对象不影响记录
            logger.warning("清理旧对象失败（遗留孤儿文件）: object_key=%s", key)


async def run(*, dry_run: bool, force: bool, limit: int | None) -> int:
    if minio_enabled():
        logger.info("存储模式：MinIO")
    else:
        logger.info("存储模式：本地 UPLOAD_DIR")

    async with async_session_factory() as db:
        result = await db.execute(
            select(DocumentEntry).where(DocumentEntry.is_deleted.is_(False))
        )
        entries = list(result.scalars().all())
        logger.info("未删除条目共 %d 个", len(entries))

        converted = skipped = failed = dried = 0
        processed = 0
        for entry in entries:
            attachments = list(entry.attachments or [])
            entry_touched = False
            for attachment in attachments:
                status, note = await _reconvert_one(
                    entry, attachment, dry_run=dry_run, force=force
                )
                if status == "converted":
                    converted += 1
                    processed += 1
                    entry_touched = True
                    logger.info(
                        "已重转 entry=%s file=%s (%s)",
                        entry.code or entry.name,
                        attachment.get("file_name"),
                        note,
                    )
                elif status == "dry":
                    dried += 1
                    processed += 1
                    logger.info(
                        "[dry-run] entry=%s file=%s (%s)",
                        entry.code or entry.name,
                        attachment.get("file_name"),
                        note,
                    )
                elif status == "fail":
                    failed += 1
                    logger.warning(
                        "重转失败 entry=%s file=%s (%s)",
                        entry.code or entry.name,
                        attachment.get("file_name"),
                        note,
                    )
                else:
                    skipped += 1
            if entry_touched:
                # JSON 列整体替换以触发变更跟踪
                entry.attachments = attachments
                await db.commit()
                for attachment in attachments:
                    if "_old_md_key" in attachment or "_old_asset_keys" in attachment:
                        _cleanup_superseded(
                            attachment, attachment.get("storage_key") or ""
                        )
                if limit is not None and processed >= limit:
                    logger.info("达到 --limit=%d，提前结束", limit)
                    break

        logger.info(
            "完成：重转 %d，dry-run %d，跳过 %d，失败 %d",
            converted,
            dried,
            skipped,
            failed,
        )
        return 0 if failed == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="只统计不写存储/数据库")
    parser.add_argument("--force", action="store_true", help="重转已标记 v2 的附件")
    parser.add_argument("--limit", type=int, default=None, help="最多重转 N 个附件")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, force=args.force, limit=args.limit))


if __name__ == "__main__":
    main()
