"""DR 多拉菌素 — 层析及一次结晶岗位飞书电子表格同步"""

import logging
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.integrations.feishu.utils import OPEN_API_BASE_URL
from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

DR_PRODUCT = "多拉菌素"
CHROMATOGRAPHY_SHEET = "1FecyZ"  # 层析及一次结晶岗位台账
SHEET_RANGE = "A3:Z5000"
DATA_START_ROW = 3  # 第1行标题，第2行表头，数据从第3行开始

COL = {
    "fl_batch_no": 0,
    "production_date": 1,
    "chromatography_batch_no": 2,
    "column_no": 3,
    "extraction_batch_no": 4,
    "volume_kl": 5,
    "potency_mg_l": 6,
    "product_qty_kg": 7,
    "total_product_qty_kg": 8,
    "column_load_vol_kl": 9,
    "column_load_potency_mg_l": 10,
    "column_load_product_kg": 11,
    "column_load_total_product_kg": 12,
    "elution_volume": 13,
    "elution_unit": 14,
    "elution_product_kg": 15,
    "chromatography_yield": 16,
    "wet_powder_batch_no": 17,
    "wet_powder_weight_kg": 18,
    "wet_powder_content": 19,
    "wet_powder_dry_loss": 20,
    "wet_powder_pure_kg": 21,
    "crystallization_yield": 22,
    "mother_liquor_volume": 23,
    "mother_liquor_content": 24,
    "mother_liquor_product_qty": 25,
}

MERGE_KEYS = [
    "fl_batch_no", "production_date",
    "chromatography_batch_no", "column_no", "extraction_batch_no",
]

# 字符串类型明细列（按文本读取，不做 float 转换）
STRING_COLS = {"wet_powder_batch_no"}

_token_cache: dict[str, str] = {}


async def _get_token(app_id: str, app_secret: str) -> str:
    k = f"dr_chrom:{app_id}"
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

async def sync_dr_chromatography(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    token = await _get_token(config.app_id, app_secret)
    logger.info("[DR层析同步] 读取飞书表格...")
    rows = await _read_sheet(token, CHROMATOGRAPHY_SHEET, config.bitable_app_token)

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

            if not inherited.get("chromatography_batch_no"):
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
            logger.warning(f"[DR层析同步] 行 {ri + DATA_START_ROW}: {e}")
            stats["errors"] += 1

    # 全量重建：先清空旧数据，再按飞书原始行序逐行插入（不做去重，忠实保留每一行）
    if data_rows:
        await session.execute(text("DELETE FROM production.dr_chromatography_crystal"))
        for data in data_rows:
            cols = ", ".join(data.keys())
            vals = ", ".join(f":{k}" for k in data)
            await session.execute(
                text(
                    f"INSERT INTO production.dr_chromatography_crystal "
                    f"(id, {cols}) VALUES (gen_random_uuid(), {vals})"
                ),
                data,
            )
            stats["created"] += 1

    await session.commit()
    logger.info("[DR层析同步] 完成: %s", stats)
    return stats
