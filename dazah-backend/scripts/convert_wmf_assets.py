"""将 md 引用的 wmf/emf 图片转换为 png（浏览器不支持的格式），更新引用。

在 app 容器内运行：/app/.venv/bin/python /tmp/convert_wmf_assets.py
"""

import asyncio
import io
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, "/app")

from minio import Minio
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.modules.quality.models.document_catalog import DocumentEntry

URL_KEY_RE = re.compile(
    r"(!\[[^\]]*\]\(/api/v1/quality/document-entries/"
    r"[\w-]+/attachments/)(document-catalog/attachments/[^)/]+)(/content\))"
)


def convert_to_png(data: bytes, name: str) -> bytes | None:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, name)
        with open(src, "wb") as f:
            f.write(data)
        try:
            subprocess.run(
                ["soffice", "--headless",
                 "-env:UserInstallation=file:///tmp/lo_conv",
                 "--convert-to", "png", "--outdir", tmp, src],
                capture_output=True, timeout=60, check=False,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        png = os.path.join(tmp, os.path.splitext(name)[0] + ".png")
        if os.path.exists(png):
            return open(png, "rb").read()
    return None


async def main() -> None:
    s = get_settings()
    mc = Minio(s.MINIO_ENDPOINT, access_key=s.MINIO_ACCESS_KEY,
               secret_key=s.MINIO_SECRET_KEY, secure=False)
    bucket = f"{s.MINIO_BUCKET_PREFIX}-quality"

    converted: dict[str, str] = {}  # 旧 key → 新 png key
    stats = {"converted": 0, "failed": 0}

    async with async_session_factory() as db:
        rows = await db.execute(text(
            "SELECT id::text, attachments::text FROM quality.document_entries "
            "WHERE is_deleted=false AND attachments::text LIKE '%.wmf%' "
            "OR is_deleted=false AND attachments::text LIKE '%.emf%'"
        ))
        entries = rows.all()

    for entry_id, raw in entries:
        attachments = json.loads(raw or "[]")
        changed = False
        md_key = None
        for a in attachments:
            if a.get("converted_md_key"):
                md_key = a["converted_md_key"]
        if not md_key:
            continue
        # 该条目下所有 wmf/emf asset
        for a in attachments:
            keys = a.get("asset_keys") or []
            for i, key in enumerate(keys):
                ext = os.path.splitext(key)[1].lower()
                if ext not in {".wmf", ".emf"}:
                    continue
                if key in converted:
                    keys[i] = converted[key]
                    changed = True
                    continue
                try:
                    resp = mc.get_object(bucket, key)
                    data = resp.read()
                    resp.close()
                    resp.release_conn()
                except Exception:
                    stats["failed"] += 1
                    continue
                png = convert_to_png(data, os.path.basename(key))
                if png is None:
                    stats["failed"] += 1
                    continue
                new_key = (
                    "document-catalog/attachments/"
                    f"{os.urandom(16).hex()}_"
                    f"{os.path.splitext(os.path.basename(key))[0]}.png"
                )
                mc.put_object(bucket, new_key, io.BytesIO(png), len(png),
                              content_type="image/png")
                converted[key] = new_key
                keys[i] = new_key
                changed = True
                stats["converted"] += 1
            a["asset_keys"] = keys
        if not changed:
            continue
        # md 内引用替换
        try:
            resp = mc.get_object(bucket, md_key)
            md = resp.read().decode("utf-8", errors="replace")
            resp.close()
            resp.release_conn()

            def _sub(m: re.Match[str]) -> str:
                return m.group(1) + converted.get(m.group(2), m.group(2)) + m.group(3)

            new_md = URL_KEY_RE.sub(_sub, md)
            if new_md != md:
                encoded = new_md.encode("utf-8")
                mc.put_object(bucket, md_key, io.BytesIO(encoded), len(encoded),
                              content_type="text/markdown; charset=utf-8")
        except Exception:
            pass
        # 用 ORM 更新（flag_modified 语义）
        entry = await db.get(DocumentEntry, entry_id)
        entry.attachments = attachments
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(entry, "attachments")
        await db.commit()
        print("条目已更新:", entry.code or entry_id)

    print("完成:", stats, "| 转换映射:", len(converted))


asyncio.run(main())
