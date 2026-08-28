"""邮箱简历抓取 - IMAP定时扫描收件箱，下载PDF/DOCX附件（含去重）。"""

import email as em
import hashlib
import imaplib
import json
import logging
from datetime import UTC, datetime
from email.header import decode_header
from pathlib import Path
from typing import Any

from app.core.database import async_session_factory
from app.shared.config_reader import get_module_setting, set_module_setting

logger = logging.getLogger(__name__)

# 内存缓存已处理的文件哈希，防止重复处理
_PROCESSED_HASHES: set[str] = set()

# 支持的简历附件类型
SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".doc")

# 去重记录文件名（与 resume_watcher 共享）
HASH_RECORD_FILE = ".processed_hashes.json"


def _load_all_hashes(save_dir: Path) -> set[str]:
    """从 JSON 文件、根目录文件、processed 子文件夹合并加载所有哈希。

    与 resume_watcher 共享同一份去重记录，防止重复下载。
    """
    hashes: set[str] = set()

    # 1. 从 JSON 文件加载（两者共享）
    hash_file = save_dir / HASH_RECORD_FILE
    if hash_file.exists():
        try:
            with open(hash_file, encoding="utf-8") as hash_stream:
                data = json.load(hash_stream)
                if isinstance(data, list):
                    hashes.update(data)
                elif isinstance(data, dict):
                    hashes.update(data.get("hashes", []))
        except Exception:
            logger.exception("failed to load hash record file")

    # 2. 从根目录文件名中提取哈希（兼容旧格式）
    if save_dir.exists():
        for file_path in save_dir.iterdir():
            if not file_path.name.lower().endswith(SUPPORTED_EXTENSIONS):
                continue
            name = file_path.stem
            if name.startswith("简历_"):
                parts = name.split("_", 2)
                if len(parts) >= 2:
                    hashes.add(parts[1])

    # 3. 从 processed 子文件夹加载（resume_watcher 移动过来的文件）
    processed_dir = save_dir / "processed"
    if processed_dir.exists():
        for file_path in processed_dir.iterdir():
            if not file_path.name.lower().endswith(SUPPORTED_EXTENSIONS):
                continue
            # 计算文件哈希
            try:
                file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:12]
                hashes.add(file_hash)
            except Exception as e:
                logger.warning("邮件哈希计算失败: %s", e)
            # 兼容旧格式
            name = file_path.stem
            if name.startswith("简历_"):
                parts = name.split("_", 2)
                if len(parts) >= 2:
                    hashes.add(parts[1])

    return hashes


def _save_processed_hashes(save_dir: Path) -> None:
    """保存已处理哈希到 JSON 文件（与 resume_watcher 共享）"""
    try:
        hash_file = save_dir / HASH_RECORD_FILE
        with open(hash_file, "w", encoding="utf-8") as f:
            json.dump(sorted(_PROCESSED_HASHES), f, ensure_ascii=False)
    except Exception:
        logger.exception("failed to save hash record file")


async def _save_fetch_status(fetched_count: int, status: str = "ok") -> None:
    """保存抓取状态到数据库"""
    try:
        async with async_session_factory() as session:
            await set_module_setting(
                session, "hr", "HR_MAIL_LAST_SCAN_AT", datetime.now(UTC).isoformat()
            )
            await set_module_setting(
                session, "hr", "HR_MAIL_LAST_FETCHED_COUNT", str(fetched_count)
            )
            await set_module_setting(session, "hr", "HR_MAIL_LAST_FETCH_STATUS", status)
            await session.commit()
    except Exception:
        logger.exception("failed to save fetch status")


async def fetch_resumes_from_mail(
    scan_all: bool = False, force_redownload: bool = False
) -> dict[str, Any]:
    """IMAP扫描收件箱，下载PDF/DOCX附件到本地文件夹（去重）。

    Args:
        scan_all: 是否扫描所有邮件（包括已读）。默认 False 只扫描未读邮件。
        force_redownload: 是否强制重新下载（清除去重缓存）。默认 False。
    """
    imap_host = await get_module_setting("hr", "HR_MAIL_IMAP_HOST")
    imap_port = int(await get_module_setting("hr", "HR_MAIL_IMAP_PORT", "993"))
    imap_user = await get_module_setting("hr", "HR_MAIL_IMAP_USER")
    imap_pass_encrypted = await get_module_setting("hr", "HR_MAIL_IMAP_PASS")
    enabled = await get_module_setting("hr", "HR_MAIL_FETCH_ENABLED", "false")

    if enabled.lower() != "true" or not all(
        [imap_host, imap_user, imap_pass_encrypted]
    ):
        await _save_fetch_status(0, "not_configured_or_disabled")
        return {"status": "not_configured_or_disabled", "fetched": 0}

    try:
        from app.core.llm import decrypt_api_key

        imap_pass = decrypt_api_key(imap_pass_encrypted)
    except Exception:
        imap_pass = imap_pass_encrypted

    # 简历存储目录：复用 resume_watcher 的解析逻辑（含旧桌面路径自动迁移为服务器目录）
    from app.modules.hr.resume_watcher import _resolve_watch_dir

    save_dir = await _resolve_watch_dir()
    save_dir.mkdir(parents=True, exist_ok=True)

    # 加载去重哈希（始终从文件+目录重新加载，确保与 resume_watcher 同步）
    global _PROCESSED_HASHES
    if force_redownload:
        _PROCESSED_HASHES.clear()
        logger.info("force_redownload: cleared processed hashes cache")

    # 每次都重新加载，确保包含 resume_watcher 处理的文件哈希
    _PROCESSED_HASHES = _load_all_hashes(save_dir)
    logger.info(
        "loaded %d processed hashes (merged from json + files + processed/)",
        len(_PROCESSED_HASHES),
    )

    fetched = 0
    scanned_emails = 0
    try:
        mail = imaplib.IMAP4_SSL(imap_host, imap_port)
        mail.login(imap_user, imap_pass)
        mail.select("INBOX")

        search_criteria = "ALL" if scan_all else "UNSEEN"
        _, data = mail.search(None, search_criteria)
        uids = data[0].split() if data[0] else []

        for uid in uids:
            uid_str = uid.decode()
            scanned_emails += 1
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                if (
                    not msg_data
                    or not isinstance(msg_data[0], tuple)
                    or len(msg_data[0]) < 2
                    or not isinstance(msg_data[0][1], bytes)
                ):
                    continue
                msg = em.message_from_bytes(msg_data[0][1])

                for part in msg.walk():
                    if part.get_content_maintype() != "application":
                        continue
                    filename = part.get_filename()
                    if not filename:
                        continue
                    decoded = decode_header(filename)[0][0]
                    if isinstance(decoded, bytes):
                        filename = decoded.decode(errors="ignore")
                    else:
                        filename = decoded

                    if filename.lower().endswith(SUPPORTED_EXTENSIONS):
                        payload = part.get_payload(decode=True)
                        if not isinstance(payload, bytes) or not payload:
                            continue
                        file_bytes = payload
                        file_hash = hashlib.sha256(file_bytes).hexdigest()
                        hash_short = file_hash[:12]

                        # 去重检查
                        if hash_short in _PROCESSED_HASHES:
                            logger.info(
                                "skip duplicate resume",
                                extra={"uid": uid_str, "hash": hash_short},
                            )
                            continue

                        # 使用原始附件名称保存
                        file_path = save_dir / filename
                        if file_path.exists():
                            stem = file_path.stem
                            suffix = file_path.suffix
                            counter = 1
                            while file_path.exists():
                                file_path = save_dir / f"{stem}_{counter}{suffix}"
                                counter += 1
                        file_path.write_bytes(file_bytes)

                        _PROCESSED_HASHES.add(hash_short)
                        logger.info(
                            "resume saved from mail",
                            extra={
                                "uid": uid_str,
                                "file": str(file_path),
                                "hash": hash_short,
                            },
                        )
                        fetched += 1

                if not scan_all:
                    mail.store(uid, "+FLAGS", "\\Seen")
            except Exception:
                logger.exception("failed to process email", extra={"uid": uid_str})

        mail.logout()
    except Exception:
        logger.exception("mail fetch failed")
        _save_processed_hashes(save_dir)
        await _save_fetch_status(fetched, "error")
        return {"status": "error", "fetched": fetched, "scanned": scanned_emails}

    _save_processed_hashes(save_dir)
    await _save_fetch_status(fetched, "ok")
    return {"status": "ok", "fetched": fetched, "scanned": scanned_emails}
