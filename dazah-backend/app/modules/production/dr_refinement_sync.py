"""DR 多拉菌素 — 一次精制岗位飞书电子表格同步"""

import logging
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL
from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

REFINEMENT_SHEET = "3eAOFg"  # 一次精制台账
SHEET_RANGE = "A4:U5000"
DATA_START_ROW = 4  # 第1行大标题，第2行分组表头，第3行字段表头，数据从第4行开始

COL = {
    "fl_batch_no": 0,
    "production_date": 1,
    "refinement_batch_no": 2,
    "feed_weight_kg": 3,
    "feed_content": 4,
    "feed_dry_loss": 5,
    "feed_pure_kg": 6,
    "mother_liquor_volume": 7,
    "mother_liquor_unit": 8,
    "mother_liquor_product_kg": 9,
    "impurity_6": 10,
    "impurity_1": 11,
    "impurity_2": 12,
    "impurity_7": 13,
    "impurity_3": 14,
    "impurity_4": 15,
    "impurity_5": 16,
    "rrt_068": 17,
    "unknown_max_single": 18,
    "total_impurities": 19,
    "purity": 20,
}

# 发酵液批号是合并单元格（同一批多行只填一次），生产日期/生产批号每行都有值
MERGE_KEYS = ["fl_batch_no", "production_date", "refinement_batch_no"]

# 字符串类型明细列（按文本读取，不做 float 转换）；本表无额外字符串明细列
STRING_COLS: set[str] = set()

_token_cache: dict[str, str] = {}


async def _get_token(app_id: str, app_secret: str) -> str:
    k = f"dr_refine:{app_id}"
    if k in _token_cache:
        return _token_cache[k]
    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=30) as c:
        r = await c.post(
            "/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        r.raise_for_status()
        token = r.json()["tenant_access_token"]
        _token_cache[k] = token
        return str(token)


async def _read_sheet(token: str, sheet_id: str, spreadsheet_token: str) -> list[list[str]]:
    path = (
        f"/sheets/v2/spreadsheets/{spreadsheet_token}"
        f"/values/{sheet_id}!{SHEET_RANGE}"
    )
    async with httpx.AsyncClient(base_url=OPEN_API_BASE_URL, timeout=60) as c:
        r = await c.get(
            path,
            params={
                "valueRenderOption": "ToString",
                "dateTimeRenderOption": "FormattedString",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise RuntimeError(f"飞书 API HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 API code={data.get('code')}: {data.get('msg')}")
    values = data.get("data", {}).get("valueRange", {}).get("values", [])
    return [[str(c) if c is not None else "" for c in row] for row in values]


def _g(row: list[str], key: str) -> str:
    idx = COL[key]
    return str(row[idx]).strip() if idx < len(row) and row[idx] else ""


def _f(row: list[str], key: str) -> Optional[float]:
    s = _g(row, key)
    if not s or s == "-" or s.startswith("#"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _is_empty(row: list[str]) -> bool:
    return all(not c or c.strip() == "" for c in row)


# ═══════════════════════════════════════════════════════════
# 同步主逻辑
# ═══════════════════════════════════════════════════════════

async def sync_dr_refinement(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    token = await _get_token(config.app_id, app_secret)
    logger.info("[DR一次精制同步] 读取飞书表格...")
    rows = await _read_sheet(token, REFINEMENT_SHEET, config.bitable_app_token)

    stats = {"created": 0, "skipped": 0, "errors": 0}

    # 合并单元格继承
    inherited: dict[str, str] = {}
    data_rows: list[dict] = []

    for ri, row in enumerate(rows):
        if _is_empty(row):
            stats["skipped"] += 1
            continue

        try:
            # 合并单元格继承：空值沿用上一个
            for key in MERGE_KEYS:
                val = _g(row, key)
                if val:
                    inherited[key] = val

            if not inherited.get("refinement_batch_no"):
                stats["skipped"] += 1
                continue

            data = {"row_no": ri + DATA_START_ROW}
            for key in COL:
                if key in MERGE_KEYS:
                    data[key] = inherited.get(key)
                elif key in STRING_COLS:
                    data[key] = _g(row, key) or None
                else:
                    data[key] = _f(row, key)

            data_rows.append(data)
        except Exception as e:
            logger.warning(f"[DR一次精制同步] 行 {ri + DATA_START_ROW}: {e}")
            stats["errors"] += 1

    # 全量重建：先清空旧数据，再按飞书原始行序逐行插入（不做去重，忠实保留每一行）
    if data_rows:
        await session.execute(text("DELETE FROM production.dr_first_refinement"))
        for data in data_rows:
            cols = ", ".join(data.keys())
            vals = ", ".join(f":{k}" for k in data)
            await session.execute(
                text(
                    f"INSERT INTO production.dr_first_refinement "
                    f"(id, {cols}) VALUES (gen_random_uuid(), {vals})"
                ),
                data,
            )
            stats["created"] += 1

    await session.commit()
    logger.info("[DR一次精制同步] 完成: %s", stats)
    return stats
