"""飞书 → centrifuge2 全量同步"""

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
    "二次浓缩结晶悬浮液进料总量(kg)": "feed_volume",
    "离心转速(rpm)": "rotation_speed",
    "分离时间(min)": "sep_duration",
    "进料流速(L/h)": "feed_flow",
    "精制湿晶体总量(kg)": "crystal_wet_weight",
    "废母液总量(L)": "waste_liquor_volume",
    "母液残留效价(U/mL)": "mother_liquor_titer",
    "湿晶含水率(%)": "crystal_moisture",
    "母液回收量(L)": "liquor_recovery",
    "晶体收率(%)": "crystal_yield",
    "备注": "remarks",
}
NUMBER_FIELDS = {
    "rotation_speed",
    "sep_duration",
    "feed_flow",
    "mother_liquor_titer",
    "crystal_moisture",
    "crystal_yield",
}
DATE_FIELDS = {}
TABLE = "centrifuge2"


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


async def sync_centrifuge2(
    config: ProductionFeishuConfig, session: AsyncSession
) -> dict:
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
        logger.warning(
            "centrifuge2 同步警告：%d 个字段未匹配：%s", len(unmatched), unmatched
        )
    return {
        "created": created,
        "updated": updated,
        "deleted": 0,
        "unmatched_fields": unmatched if unmatched else [],
    }
