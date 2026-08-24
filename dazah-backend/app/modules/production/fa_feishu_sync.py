"""FA 苯丙氨酸 — 发酵液放罐 飞书表格同步

从飞书电子表格子表读取数据，解析主批/子批两层结构，upsert 到 fa_fermentation_batches +
        fa_fermentation_sub_batches。

spreadsheet_token / app_id / app_secret 由调用方从数据库 production_feishu_configs
        表读取后传入。
"""

import asyncio
import logging
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# 加载 .env（仅用于独立运行时 DATABASE_URL）
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(env_path)

logger = logging.getLogger(__name__)

# ========== 飞书配置 ==========
OPEN_API_BASE_URL = "https://open.feishu.cn/open-apis"
SHEET_ID = "0ZjmOv"

# ========== Token 缓存 ==========
_token_cache: dict[str, str] = {}


async def _get_token(app_id: str, app_secret: str) -> str:
    cache_key = f"fa_sync:{app_id}"
    if cache_key in _token_cache:
        return _token_cache[cache_key]
    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        resp.raise_for_status()
        token = resp.json()["tenant_access_token"]
        _token_cache[cache_key] = str(token)
        return str(token)


async def _read_sheet(
    spreadsheet_token: str, app_id: str, app_secret: str
) -> list[list]:
    """读取整个工作表，返回二维数组（每行是一个 list）"""
    token = await _get_token(app_id, app_secret)

    path = f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{SHEET_ID}"
    params = {
        "valueRenderOption": "ToString",
        "dateTimeRenderOption": "FormattedString",
    }
    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=60) as client:
        resp = await client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()

    value_range = data.get("data", {}).get("valueRange", {})
    values = value_range.get("values", [])
    # 每个 cell 转为字符串，None → ""
    return [[str(c) if c is not None else "" for c in row] for row in values]


def _get(row: list, idx: int) -> str:
    """安全取列值"""
    if idx < len(row):
        return str(row[idx]).strip()
    return ""


def _parse_date(raw: str) -> str | None:
    """中文日期 → ISO 格式：12月27日 → 2025-12-27（年份由上下文确定）"""
    raw = raw.strip()
    m = re.match(r"(\d+)月(\d+)日", raw)
    if not m:
        return None
    month = int(m.group(1))
    day = int(m.group(2))
    # 12 月 → 2025，其余 → 2026
    year = 2025 if month == 12 else 2026
    return f"{year}-{month:02d}-{day:02d}"


def _safe_num(val: str) -> str:
    """安全转数值 → SQL 字面量"""
    val = val.strip().rstrip("%")
    if not val or val == "-":
        return "NULL"
    try:
        return str(float(val))
    except ValueError:
        return "NULL"


def _safe_pct(val: str) -> str:
    """百分比列：飞书 API 返回 0.39 → 转为 39% 字符串"""
    val = val.strip()
    if not val or val == "-":
        return "NULL"
    try:
        n = float(val)
        if 0 < n < 1:
            return f"'{round(n * 100)}%'"
        return f"'{val}'"
    except ValueError:
        return f"'{val}'"


async def sync_fermentation(
    session: AsyncSession, spreadsheet_token: str, app_id: str, app_secret: str
):
    """主同步函数"""
    logger.info("FA 发酵液放罐同步开始...")

    # 1. 读取飞书数据
    rows = await _read_sheet(spreadsheet_token, app_id, app_secret)
    logger.info(f"飞书读取完成，共 {len(rows)} 行")

    # 2. 解析数据
    batches: list[dict] = []  # 主批
    sub_batches: list[dict] = []  # 子批

    current_date: str | None = None  # 继承合并单元格的日期（Row A）
    current_tank: str | None = None  # 继承合并单元格的罐号（Row B）

    for row in rows:
        col_a = _get(row, 0)  # 放罐日期
        col_b = _get(row, 1)  # 发酵罐号
        col_c = _get(row, 2)  # 发酵批号
        col_d = _get(row, 3)  # 放罐体积
        col_e = _get(row, 4)  # 放罐含量
        col_f = _get(row, 5)  # 放罐批总量(kg) — 子批自身重量
        col_g = _get(row, 6)  # 放罐批总量（kg）— 主批汇总
        col_h = _get(row, 7)  # 电导
        col_i = _get(row, 8)  # 调酸量
        col_j = _get(row, 9)  # 滤速
        col_k = _get(row, 10)  # 湿固
        col_l = _get(row, 11)  # 产量
        col_m = _get(row, 12)  # 收率

        # 继承合并单元格
        if col_a:
            current_date = col_a
        if col_b and re.match(r"FA-EX\d+$", col_b):
            current_tank = col_b

        # 跳过：标题行、表头行、月份分隔行、空行、月度汇总行
        if col_a in ("", None) and col_b in ("", None) and col_c in ("", None):
            continue
        if re.match(r"^\d+月$", col_a):
            continue
        if re.search(r"年.*月平均值|年年平均值|放罐统计|放罐日期", " ".join(row)):
            continue

        # 主批行：col_b 匹配 FA-EX 模式且 col_c 为空
        if col_b and re.match(r"FA-EX\d+$", col_b) and not col_c:
            # 检测格式：col_d 有数值 → Format B（有体积/含量）
            vol_d = _safe_num(col_d)
            has_parent_vol = vol_d != "NULL"

            batch = {
                "罐号": col_b,
                "日期": _parse_date(current_date) if current_date else None,
                "体积": _safe_num(col_d) if has_parent_vol else "NULL",
                "含量": _safe_num(col_e) if has_parent_vol else "NULL",
                "自身总量": _safe_num(col_f) if has_parent_vol else "NULL",
                # 汇总总量：Format A 用 col_g，Format B 也用 col_g
                "汇总总量": _safe_num(col_g) if col_g else "NULL",
                "电导": _safe_num(col_h),
                "调酸": _safe_num(col_i),
                "滤速": _safe_num(col_j),
                "湿固": _safe_pct(col_k),
                "产量": _safe_num(col_l),
                "收率": _safe_pct(col_m),
            }
            batches.append(batch)
            continue

        # 子批行：col_c 匹配 FA-EX + C/D 后缀
        if col_c and re.match(r"FA-EX\d+[CD]$", col_c):
            sub = {
                "批号": col_c,
                "父罐号": current_tank or col_c[:-1],
                "后缀": col_c[-1],
                "体积": _safe_num(col_d),
                "含量": _safe_num(col_e),
                "批总量": _safe_num(col_f),
            }
            sub_batches.append(sub)

    logger.info(f"解析完成：{len(batches)} 主批 + {len(sub_batches)} 子批")

    # 3. 写入数据库（UPSERT）
    created_b, updated_b = 0, 0
    for b in batches:
        date_val = f"'{b['日期']}'" if b["日期"] else "NULL"
        sql = text(f"""
            INSERT INTO production.fa_fermentation_batches
                ("发酵罐号", "放罐日期", "放罐体积_kl", "放罐含量_gL",
                 "主批自身总量_kg", "汇总总量_kg", "电导_uscm", "调酸量_L",
                 "酸化液滤速_ml10min", "发酵液湿固", "产量", "收率")
            VALUES ('{b["罐号"]}', {date_val}, {b["体积"]}, {b["含量"]},
                    {b["自身总量"]}, {b["汇总总量"]}, {b["电导"]}, {b["调酸"]},
                    {b["滤速"]}, {b["湿固"]}, {b["产量"]}, {b["收率"]})
            ON CONFLICT ("发酵罐号") DO UPDATE SET
                "放罐日期" = EXCLUDED."放罐日期",
                "放罐体积_kl" = EXCLUDED."放罐体积_kl",
                "放罐含量_gL" = EXCLUDED."放罐含量_gL",
                "主批自身总量_kg" = EXCLUDED."主批自身总量_kg",
                "汇总总量_kg" = EXCLUDED."汇总总量_kg",
                "电导_uscm" = EXCLUDED."电导_uscm",
                "调酸量_L" = EXCLUDED."调酸量_L",
                "酸化液滤速_ml10min" = EXCLUDED."酸化液滤速_ml10min",
                "发酵液湿固" = EXCLUDED."发酵液湿固",
                "产量" = EXCLUDED."产量",
                "收率" = EXCLUDED."收率",
                updated_at = now()
        """)
        result = await session.execute(sql)
        if result.rowcount and result.rowcount > 0:
            updated_b += 1
        else:
            created_b += 1

    created_s, updated_s = 0, 0
    for s in sub_batches:
        sql = text(f"""
            INSERT INTO production.fa_fermentation_sub_batches
                ("发酵批号", "父发酵罐号", "子批后缀", "放罐体积_kl", "放罐含量_gL",
        "批总量_kg")
            VALUES ('{s["批号"]}', '{s["父罐号"]}', '{s["后缀"]}',
                    {s["体积"]}, {s["含量"]}, {s["批总量"]})
            ON CONFLICT ("父发酵罐号", "子批后缀") DO UPDATE SET
                "发酵批号" = EXCLUDED."发酵批号",
                "放罐体积_kl" = EXCLUDED."放罐体积_kl",
                "放罐含量_gL" = EXCLUDED."放罐含量_gL",
                "批总量_kg" = EXCLUDED."批总量_kg",
                updated_at = now()
        """)
        result = await session.execute(sql)
        if result.rowcount and result.rowcount > 0:
            updated_s += 1
        else:
            created_s += 1

    await session.commit()
    logger.info(
        f"同步完成 — 主批: 新增{created_b}, 更新{updated_b} | "
        f"子批: 新增{created_s}, 更新{updated_s}"
    )
    return {
        "batches": len(batches),
        "sub_batches": len(sub_batches),
        "created_batches": created_b,
        "updated_batches": updated_b,
        "created_subs": created_s,
        "updated_subs": updated_s,
    }


async def main():
    """独立运行入口（从命令行直接执行）"""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    db_url = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/dazah"
    )
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        from app.modules.production.fa_feishu_scheduler import (
            _get_fa_spreadsheet_config,
        )

        cfg = await _get_fa_spreadsheet_config(session)
        result = await sync_fermentation(
            session, cfg["spreadsheet_token"], cfg["app_id"], cfg["app_secret"]
        )
        print(f"\n[DONE] {result}")
        print(
            f"  Parent batches: {result['batches']} (new={result['created_batches']}, updated={result['updated_batches']})"  # noqa: E501
        )
        print(
            f"  Sub batches: {result['sub_batches']} (new={result['created_subs']}, updated={result['updated_subs']})"  # noqa: E501
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
