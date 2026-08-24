"""飞书 → conc2 全量同步"""

import logging
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

FIELD_MAPPING = {
    "批次": "batch_no",
    "二次板框母液合并总量(L)": "feed_volume",
    "真空(MPa)": "vacuum_degree",
    "温度(℃)": "evap_temp",
    "蒸汽压力(MPa)": "steam_pressure",
    "浓缩终点折光(%)": "endpoint_refraction",
    "浓缩终点比重": "endpoint_density",
    "二次浓缩液体积(L)": "conc_volume",
    "二次浓缩液效价(U/mL)": "conc_titer",
    "浓缩倍数": "conc_factor",
    "冷凝水量(L)": "condensate_volume",
    "釜底残液(L)": "bottom_residue",
    "挥发损耗(%)": "evap_loss_rate",
    "浓缩收率(%)": "conc_yield",
    "备注": "remarks",
}
NUMBER_FIELDS = {
    "vacuum_degree",
    "evap_temp",
    "steam_pressure",
    "endpoint_refraction",
    "endpoint_density",
    "conc_titer",
    "conc_factor",
    "evap_loss_rate",
    "conc_yield",
}
DATE_FIELDS = {}
TABLE = "conc2"


def _ext(fv):
    if fv is None:
        return None
    if isinstance(fv, str):
        return fv.strip() or None
    if isinstance(fv, dict):
        return str(fv.get("name") or fv.get("text", "")).strip() or None
    if isinstance(fv, list) and fv:
        f = fv[0]
        if isinstance(f, str):
            return f.strip() or None
        if isinstance(f, dict):
            return str(f.get("name") or f.get("text", "")).strip() or None
    return str(fv).strip() or None


def _num(fv):
    if isinstance(fv, (int, float)):
        return float(fv)
    t = _ext(fv)
    if t is None:
        return None
    try:
        return float(t)
    except (ValueError, TypeError):
        return None


def _pd(v):
    if v is None:
        return None
    if isinstance(v, (int, float)) and 0 < v < 1e15:
        return datetime.fromtimestamp(v / 1000).date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return v


async def sync_conc2(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(config.app_id, app_secret, config.bitable_app_token)
    records_data = await client.list_records(config.table_id, page_size=500)
    items = [i for i in (records_data.get("items") or []) if isinstance(i, dict)]

    feishu_ids = set()
    created, updated = 0, 0
    matched_fields: set = set()

    for item in items:
        rid = item.get("record_id", "")
        feishu_ids.add(rid)
        fields = item.get("fields", {})
        mapped: dict = {"feishu_record_id": rid}
        for fn, db_col in FIELD_MAPPING.items():
            raw = fields.get(fn)
            if raw is None:
                continue
            matched_fields.add(fn)
            if db_col in DATE_FIELDS:
                if isinstance(raw, (int, float)):
                    mapped[db_col] = _pd(raw)
                else:
                    v = _ext(raw)
                    mapped[db_col] = _pd(v) if v else None
                continue
            v = _num(raw) if db_col in NUMBER_FIELDS else _ext(raw)
            if v is not None:
                mapped[db_col] = v
        if not mapped.get("batch_no"):
            continue

        existing = await session.execute(
            text(
                f"SELECT id FROM production.{TABLE} WHERE feishu_record_id = :rid AND is_deleted = false"  # noqa: E501
            ),
            {"rid": rid},
        )
        row = existing.fetchone()
        if row:
            set_clause = ", ".join(
                f"{k} = :{k}" for k in mapped if k != "feishu_record_id"
            )
            await session.execute(
                text(f"UPDATE production.{TABLE} SET {set_clause} WHERE id = :id"),
                {"id": row[0], **mapped},
            )
            updated += 1
        else:
            cols = ", ".join(mapped.keys())
            vals = ", ".join(f":{k}" for k in mapped)
            await session.execute(
                text(
                    f"INSERT INTO production.{TABLE} (id, {cols}) VALUES (gen_random_uuid(), {vals})"  # noqa: E501
                ),
                mapped,
            )
            created += 1

    if feishu_ids:
        await session.execute(
            text(
                f"UPDATE production.{TABLE} SET is_deleted = true WHERE is_deleted = false AND feishu_record_id IS NOT NULL AND feishu_record_id != ALL(:ids)"  # noqa: E501
            ),
            {"ids": list(feishu_ids)},
        )

    unmatched = sorted(set(FIELD_MAPPING.keys()) - matched_fields)
    if unmatched:
        logger.warning("conc2 同步警告：%d 个字段未匹配：%s", len(unmatched), unmatched)
    return {
        "created": created,
        "updated": updated,
        "deleted": 0,
        "unmatched_fields": unmatched if unmatched else [],
    }
