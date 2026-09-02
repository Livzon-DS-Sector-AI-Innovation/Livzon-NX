"""临时分析2：真实编号错配（修正正则）+ 桌面同名冲突统计。"""

import asyncio
import os
import re
import sys

sys.path.insert(0, "/app")

from minio import Minio

# 完整编号：字母段-段-3位数字 + 可选修订段
CODE_RE = re.compile(
    r"\*\*文件编号\*\*[:：]\s*"
    r"([A-Za-z][A-Za-z0-9()（）\-]*-\d{3}(?:[-/]\d{1,3})?)"
)
NAME_CODE_RE = re.compile(r"([A-Za-z][A-Za-z0-9()（）\-]*-\d{3}(?:-\d{1,3})?)")


def norm(c: str) -> str:
    c = re.sub(r"[\s]+", "", c).replace("（", "(").replace("）", ")").upper()
    # 去掉修订段差异：比较主干
    return c


def norm_name(s: str) -> str:
    base = os.path.splitext(s.strip())[0]
    base = base.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", base).lower()


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

    mismatch = 0
    md_no_code = 0
    fname_no_code = 0
    checked = 0
    samples = []
    name_count: dict[str, int] = {}

    async with async_session_factory() as db:
        rows = await db.execute(
            text(
                """
                SELECT a.file_name, a.converted_md_key
                FROM quality.document_entries e,
                     jsonb_to_recordset(e.attachments::jsonb) AS
                       a(file_name text, converted_md_key text, pipeline text)
                WHERE e.is_deleted=false AND a.pipeline='v2'
                """
            )
        )
        pairs = rows.all()

    for fname, md_key in pairs:
        checked += 1
        name_count[norm_name(fname)] = name_count.get(norm_name(fname), 0) + 1
        resp = mc.get_object(bucket, md_key)
        try:
            md = resp.read().decode("utf-8", errors="replace")
        finally:
            resp.close()
            resp.release_conn()
        m = CODE_RE.search(md)
        md_code = m.group(1) if m else ""
        fm = NAME_CODE_RE.search(fname or "")
        fname_code = fm.group(1) if fm else ""
        if not md_code:
            md_no_code += 1
            continue
        if not fname_code:
            fname_no_code += 1
            continue
        # 主干比较：md 编号应以文件名编号为前缀（文件名编号含修订段时全等）
        md_n, fn_n = norm(md_code), norm(fname_code)
        if not (fn_n.startswith(md_n) or md_n.startswith(fn_n)):
            mismatch += 1
            if len(samples) < 12:
                samples.append((fname[:46], md_code, fname_code))

    dup = {k: v for k, v in name_count.items() if v > 1}
    print("v2 附件:", checked)
    print("真实编号错配(md头 vs 文件名):", mismatch)
    print("md 无编号头:", md_no_code, "| 文件名无编号:", fname_no_code)
    print("同名附件组(平台内重复文件名):", len(dup), "组")
    print("涉及附件数:", sum(dup.values()))
    for k, v in list(dup.items())[:8]:
        print("   重复:", k[:50], "x", v)
    print("--- 错配样例 ---")
    for s2 in samples:
        print("  文件=", s2[0], "| md头=", s2[1], "| 文件名=", s2[2])


asyncio.run(main())
