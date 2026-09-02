"""同名历史附件甄别：对平台内同名附件组，按条目部门 + 桌面候选正文编号
重新选择正确的桌面产物。默认仅分析报告（--apply 才改）。

在宿主机新线 venv 下运行（读桌面树 + 新线 docker 库 + 新线 MinIO）。
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DESKTOP = Path(r"C:\Users\Administrator\Desktop\莫小张")
CODE_RE = re.compile(
    r"\*\*文件编号\*\*[:：]\s*([A-Za-z][A-Za-z0-9()（）\-]*-\d{3}(?:[-/]\d{1,3})?)"
)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\(([^()]*)_images/([^()/]+)\)")


def norm_name(s: str) -> str:
    base = os.path.splitext(s.strip())[0]
    base = base.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", base).lower()


def norm_code(c: str) -> str:
    c = re.sub(r"\s+", "", c).replace("（", "(").replace("）", ")").upper()
    return c


def index_desktop() -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    for root, _dirs, files in os.walk(DESKTOP):
        for name in files:
            if name.lower().endswith(".md"):
                path = Path(root) / name
                index[norm_name(name)].append(path)
    return index


PATH_CODE_RE = re.compile(r"([A-Za-z][A-Za-z0-9()（）\-]*-\d{3}(?:-\d{1,3})?)")


def path_codes(path: Path) -> list[str]:
    """候选相对路径（含父目录与文件名）中提取的全部编号。"""
    try:
        rel = path.relative_to(DESKTOP)
    except ValueError:
        return []
    codes: list[str] = []
    for part in rel.parts:
        for m in PATH_CODE_RE.finditer(part):
            codes.append(norm_code(m.group(1)))
    return codes


def top_folder(path: Path) -> str:
    try:
        rel = path.relative_to(DESKTOP)
        return rel.parts[0] if len(rel.parts) > 1 else ""
    except ValueError:
        return ""


def read_code_and_title(path: Path) -> tuple[str, str]:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return "", ""
    code = CODE_RE.search(head)
    title = TITLE_RE.search(head)
    return (code.group(1) if code else "", title.group(1).strip() if title else "")


def rewrite_md(md_text: str, entry_id: str, images_dir: Path, mc: Minio, bucket: str):
    asset_keys: list[str] = []
    name_to_url: dict[str, str] = {}
    if images_dir.is_dir():
        for img in sorted(images_dir.iterdir()):
            if not img.is_file():
                continue
            key = f"document-catalog/attachments/{os.urandom(16).hex()}_{img.name}"
            data = img.read_bytes()
            mc.put_object(bucket, key, io.BytesIO(data), len(data),
                          content_type="application/octet-stream")
            asset_keys.append(key)
            name_to_url[img.name] = (
                f"/api/v1/quality/document-entries/{entry_id}"
                f"/attachments/{key}/content"
            )

    def _sub(m: re.Match[str]) -> str:
        url = name_to_url.get(m.group(2))
        return f"![image]({url})" if url else m.group(0)

    return IMAGE_REF_RE.sub(_sub, md_text), asset_keys


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    cfg = {}
    for line in open(r"E:\工厂平台1\dazah-backend\.env", encoding="utf-8"):
        if line.startswith("DATABASE_URL="):
            cfg["db"] = line.split("=", 1)[1].strip()
    db_url = cfg["db"].replace("localhost:5432", "localhost:5433")
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine)

    minio_cfg = {}
    for line in open(r"E:\工厂平台1\.env.local", encoding="utf-8"):
        if line.startswith("MINIO_"):
            k, _, v = line.partition("=")
            minio_cfg[k.strip()] = v.strip()
    mc = Minio(
        "localhost:9000",
        access_key=minio_cfg.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=minio_cfg.get("MINIO_SECRET_KEY", "minioadmin"),
        secure=False,
    )
    bucket = f"{minio_cfg.get('MINIO_BUCKET_PREFIX', 'dazah')}-quality"

    index = index_desktop()
    print("桌面 md 总数:", sum(len(v) for v in index.values()),
          "| 归一化名:", len(index))

    async with factory() as db:
        rows = await db.execute(
            text(
                """
                SELECT e.id::text, e.code, e.name, d.name AS dept,
                       a.file_name, a.converted_md_key, a.asset_keys::text,
                       a.storage_key
                FROM quality.document_entries e
                JOIN quality.document_departments d ON d.id = e.department_id
                CROSS JOIN LATERAL jsonb_to_recordset(e.attachments::jsonb) AS
                     a(file_name text, converted_md_key text,
                       asset_keys jsonb, pipeline text, storage_key text)
                WHERE e.is_deleted=false AND a.pipeline='v2'
                """
            )
        )
        all_rows = rows.all()

    by_name: dict[str, list[tuple]] = defaultdict(list)
    for r in all_rows:
        by_name[norm_name(r[4])].append(r)

    dup_groups = {k: v for k, v in by_name.items() if len(v) > 1}
    print("平台同名组:", len(dup_groups),
          "涉及附件:", sum(len(v) for v in dup_groups.values()))

    resolvable = ambiguous = 0
    actions = []
    for norm, items in dup_groups.items():
        candidates = index.get(norm, [])
        if len(candidates) <= 1:
            continue
        for entry_id, code, name, dept, fname, md_key, assets_raw, storage_key in items:
            scored = []
            for cand in candidates:
                score = 0
                # 父目录/路径编号与条目 code 主干一致 → 强信号
                if code:
                    nc = norm_code(code).split("/")[0]
                    nc_full = nc + "-" + code.split("/")[-1] if "/" in code else nc
                    for pc in path_codes(cand):
                        pc_main = re.sub(r"-\d{1,3}$", "", pc)
                        if nc_full and pc == nc_full:
                            score += 8
                            break
                        if pc == nc or pc_main == nc:
                            score += 6
                            break
                if dept and top_folder(cand) and dept in top_folder(cand):
                    score += 2
                cand_code, cand_title = read_code_and_title(cand)
                if code and cand_code:
                    nc, nd = norm_code(cand_code), norm_code(code)
                    if nc == nd or nc[:14] == nd[:14]:
                        score += 3
                if name and cand_title and (
                    name[:6] in cand_title or cand_title[:6] in name
                ):
                    score += 2
                if nc_full and cand.parent.name.startswith(nc_full):
                    score += 2
                scored.append((score, cand, cand_code, cand_title))
            scored.sort(key=lambda x: -x[0])
            best = scored[0]
            rest = scored[1:]
            def _content_key(path: Path) -> str:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return ""
                lines = [
                    line.strip() for line in text.splitlines() if line.strip()
                ]
                return chr(10).join(sorted(lines))

            tied_equal = (
                rest
                and best[0] == rest[0][0]
                and _content_key(best[1]) == _content_key(rest[0][1])
            )
            unique_best = best[0] > 0 and (
                not rest or best[0] > rest[0][0] or tied_equal
            )
            if unique_best:
                resolvable += 1
                actions.append(
                    (entry_id, fname, dept, str(best[1]), best[0])
                )
            else:
                ambiguous += 1
                cand_names = [
                    str(x[1].relative_to(DESKTOP))[:66] for x in scored[:3]
                ]
                print(f"  [歧义] {fname[:40]} 部门={dept} code={code} "
                      f"候选={cand_names}")

    print(f"可自动确定: {resolvable} | 仍歧义: {ambiguous}")
    for a in actions[:10]:
        print("  改绑:", a[1][:40], "部门=", a[2], "→", a[3][:70])

    if args.apply and actions:
        from sqlalchemy.orm.attributes import flag_modified

        from app.modules.quality.models.document_catalog import DocumentEntry

        fixed = 0
        async with factory() as db:
            for entry_id, fname, dept, cand_str, score in actions:
                entry = await db.get(DocumentEntry, entry_id)
                if entry is None:
                    continue
                cand = Path(cand_str)
                md_text = cand.read_text(encoding="utf-8", errors="replace")
                md_text, asset_keys = rewrite_md(
                    md_text, entry_id,
                    cand.parent / f"{cand.stem}_images", mc, bucket
                )
                new_md_key = (
                    "document-catalog/attachments/"
                    f"{os.urandom(16).hex()}_{os.path.splitext(fname)[0]}.md"
                )
                data = md_text.encode("utf-8")
                mc.put_object(bucket, new_md_key, io.BytesIO(data), len(data),
                              content_type="text/markdown; charset=utf-8")
                attachments = list(entry.attachments or [])
                for a in attachments:
                    if a.get("file_name") == fname:
                        a["converted_md_key"] = new_md_key
                        a["asset_keys"] = asset_keys
                        a["pipeline"] = "v2-fixed"
                entry.attachments = attachments
                flag_modified(entry, "attachments")
                await db.commit()
                fixed += 1
        print("已改绑重写:", fixed)

    await engine.dispose()


asyncio.run(main())
