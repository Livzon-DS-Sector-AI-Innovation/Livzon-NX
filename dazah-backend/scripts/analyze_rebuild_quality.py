"""临时分析：重建附件的图片格式分布 + md 编号与文件名编号错配统计。"""

import asyncio
import json
import os
import re
import sys

sys.path.insert(0, "/app")

from minio import Minio

CODE_RE = re.compile(r"\*\*文件编号\*\*[:：]\s*(\S+)")
NAME_CODE_RE = re.compile(r"([A-Za-z]{2,3}-[A-Za-z0-9（）()]+-\d+)")


def norm_code(c: str) -> str:
    c = re.sub(r"[\s（）()]+", "", c).replace("（", "(").replace("）", ")")
    return c.upper().rstrip("/-_0123456789") if False else c.upper()


async def main() -> None:
    from sqlalchemy import text

    from app.core.config import get_settings
    from app.core.database import async_session_factory

    s = get_settings()
    mc = Minio(
        s.MINIO_ENDPOINT,
        access_key=s.MINIO_ACCESS_KEY,
        secret_key=s.MINIO_SECRET_KEY,
        secure=False,
    )
    bucket = f"{s.MINIO_BUCKET_PREFIX}-quality"

    ext_count: dict[str, int] = {}
    checked = ref_total = no_ref = mismatch = empty_code = 0
    mismatch_samples = []

    async with async_session_factory() as db:
        rows = await db.execute(
            text(
                """
                SELECT e.code, a.file_name, a.converted_md_key, a.asset_keys::text
                FROM quality.document_entries e,
                     jsonb_to_recordset(e.attachments::jsonb) AS
                       a(file_name text, converted_md_key text,
                         asset_keys jsonb, pipeline text)
                WHERE e.is_deleted=false AND a.pipeline='v2'
                """
            )
        )
        for code, fname, md_key, assets_raw in rows:
            checked += 1
            assets = json.loads(assets_raw or "[]")
            for k in assets:
                ext = os.path.splitext(k)[1].lower()
                ext_count[ext] = ext_count.get(ext, 0) + 1
            resp = mc.get_object(bucket, md_key)
            try:
                md = resp.read().decode("utf-8", errors="replace")
            finally:
                resp.close()
                resp.release_conn()
            if "![" in md:
                ref_total += 1
            else:
                no_ref += 1
            m = CODE_RE.search(md)
            md_code = m.group(1) if m else ""
            fm = NAME_CODE_RE.search(fname or "")
            fname_code = fm.group(1) if fm else ""
            if md_code and fname_code:
                if norm_code(md_code) != norm_code(fname_code):
                    mismatch += 1
                    if len(mismatch_samples) < 10:
                        mismatch_samples.append((fname[:44], md_code, fname_code))
            elif not md_code:
                empty_code += 1

    print("v2 附件:", checked)
    print("md 含图片引用:", ref_total, "| 无引用:", no_ref)
    print("图片格式分布:", dict(sorted(ext_count.items(), key=lambda x: -x[1])))
    print("编号不一致(md头 vs 文件名):", mismatch, "| md 无编号头:", empty_code)
    for s2 in mismatch_samples:
        print("  错配样例: 文件=", s2[0], "| md头编号=", s2[1], "| 文件名编号=", s2[2])


asyncio.run(main())
