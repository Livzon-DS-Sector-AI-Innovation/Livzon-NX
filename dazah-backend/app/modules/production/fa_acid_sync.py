"""FA 酸化过滤 — 飞书同步脚本（独立运行）"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
logger = logging.getLogger(__name__)

BASE_URL = "https://open.feishu.cn/open-apis"
SPREADSHEET = "V4KTwREpaipPBZkJJiNc2HlDn6g"
SHEET = "1ijZSR"
COLS = [
    ("日期", 0),
    ("批号", 1),
    ("发酵液体积（kl)", 2),
    ("发酵液含量（g/L）", 3),
    ("发酵液罐产（kg）", 4),
    ("用酸量（95-98%浓硫酸）", 5),
    ("PH（酸化后）", 6),
    ("酸化液体积（kl)", 7),
    ("理论酸化液含量（g/L）", 8),
    ("PH", 9),
    ("膜滤液体积（KL）", 10),
    ("膜滤液含量（g/L）", 11),
    ("膜滤液产品量（kg）", 12),
    ("膜滤液产品总量（kg）", 13),
    ("本批低单位含量（g/L）", 14),
    ("本批低单位体积（KL）", 15),
    ("本批低单位苯产品（kg）", 16),
    ("本批低单位量（kg）", 17),
    ("上批套用低单位量（kg）", 18),
    ("批收率", 19),
    ("顶洗前体积（kl）", 20),
    ("尾液含量（g/L）", 21),
    ("渣含量（g/L）", 22),
    ("体积（罐渣+膜渣（kl）", 23),
    ("渣产品量（kg）", 24),
    ("渣损失率（渣苯丙量/罐产）", 25),
    ("渣体积/发酵液体积", 26),
    ("酸化液/发酵液体积", 27),
    ("滤液体积/发酵液体积", 28),
    ("平衡率", 29),
    ("消泡剂使用量（L）", 30),
]
PCT_COLS = {
    "批收率",
    "渣损失率（渣苯丙量/罐产）",
    "渣体积/发酵液体积",
    "酸化液/发酵液体积",
    "滤液体积/发酵液体积",
    "平衡率",
}


async def _read(app_id: str, app_secret: str) -> list[list[Any]]:
    from app.platform.integrations.feishu.auth import FeishuAuth

    t = await FeishuAuth.get_tenant_access_token(app_id, app_secret)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as c:
        r = await c.get(
            f"/sheets/v2/spreadsheets/{SPREADSHEET}/values/{SHEET}",
            params={
                "valueRenderOption": "ToString",
                "dateTimeRenderOption": "FormattedString",
            },
            headers={"Authorization": f"Bearer {t}"},
        )
        r.raise_for_status()
    vals = r.json().get("data", {}).get("valueRange", {}).get("values", [])
    return [[str(c) if c is not None else "" for c in row] for row in vals]


def _g(row: Any, i: Any) -> Any:
    return str(row[i]).strip() if i < len(row) else ""


def _pd(raw: str) -> str | None:
    m = re.match(r"(\d+)月(\d+)日", raw.strip())
    if not m:
        return None
    return f"{2025 if int(m.group(1)) == 12 else 2026}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"  # noqa: E501


def _n(v: str) -> str:
    v = v.strip().rstrip("%")
    if not v or v in ("-", "#DIV/0!"):
        return "NULL"
    try:
        return str(float(v))
    except Exception:
        return "NULL"


def _p(v: str) -> str:
    v = v.strip()
    if not v or v == "-":
        return "NULL"
    try:
        n = float(v)
        if 0 < n < 1:
            return f"'{round(n * 100)}%'"
        if n > 1:
            return f"'{round(n)}%'"
        return f"'{v}'"
    except Exception:
        return f"'{v}'"


async def run(session: AsyncSession) -> Any:
    from app.modules.production.fa_feishu_scheduler import _get_fa_spreadsheet_config

    cfg = await _get_fa_spreadsheet_config(session)
    rows = await _read(cfg["app_id"], cfg["app_secret"])
    logger.info(f"Read {len(rows)} rows from feishu")

    records: list[dict[str, Any]] = []
    cur_date: str | None = None
    cur_batch: str | None = None
    in_data = False
    for row in rows:
        c0, c1 = _g(row, 0), _g(row, 1)
        if not in_data:
            if re.match(r"\d+月\d+日", c0) and re.match(r"FA-EX\d+", c1):
                in_data = True
            else:
                continue
        if re.match(r"\d+月$|26年\d+月$", c0):
            continue
        if re.search(r"年.*月平均值|年年平均值", " ".join(row)):
            continue
        if not c0 and not c1 and not _g(row, 2):
            continue

        if c0 and re.match(r"\d+月\d+日", c0):
            cur_date = c0
        if c1 and re.match(r"FA-EX\d+$", c1):
            cur_batch = c1

        rec: dict[str, Any] = {}
        for name, idx in COLS:
            v = _g(row, idx)
            if name in PCT_COLS:
                rec[name] = _p(v) if v else "NULL"
            elif name == "日期":
                rec[name] = f"'{_pd(cur_date)}'" if cur_date else "NULL"
            elif name == "批号":
                rec[name] = f"'{cur_batch}'" if cur_batch else "NULL"
            else:
                rec[name] = _n(v) if v else "NULL"
        records.append(rec)

    # Mark _is_first
    lb = ""
    for r in records:
        bv = r["批号"].strip("'")
        r["_is_first"] = bv != lb
        lb = bv

    # DELETE + INSERT
    await session.execute(text("DELETE FROM production.fa_acidification_records"))
    await session.flush()
    col_names = [c[0] for c in COLS]
    for r in records:
        vals = ", ".join(r[c] for c in col_names)
        await session.execute(
            text(
                f'INSERT INTO production.fa_acidification_records ("{'", "'.join(col_names)}") VALUES ({vals})'  # noqa: E501
            )
        )
    await session.commit()
    logger.info(f"Done: {len(records)} rows")

    # Count batches
    batches = sum(1 for r in records if r["_is_first"])
    return {"total_rows": len(records), "batches": batches}


async def main() -> Any:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    db_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/dazah"
    )
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as s:
        r = await run(s)
        print(f"\n[DONE] {r}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
