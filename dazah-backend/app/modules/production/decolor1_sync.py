"""飞书 → decolor1 全量同步（INSERT/UPDATE/DELETE）"""

import logging
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

FIELD_MAPPING = {
    "陶瓷膜滤液进料体积/重量": "feed_volume",
    "进料效价": "feed_titer",
    "脱色活性炭/树脂型号": "carbon_type",
    "投加量（料液比例）": "dosage",
    "搅拌转速（rpm）": "stirring_speed",
    "脱色温度（℃）": "decolor_temp",
    "保温吸附时长（min）": "holding_time",
    "终点透光率/色度": "endpoint_transmittance",
    "脱色后料液总量": "decolor_volume",
    "脱色前色度": "color_before",
    "脱色后色度": "color_after",
    "色素去除率": "color_removal_rate",
    "重金属检测数据": "heavy_metal",
    "蛋白杂质检测数据": "protein_impurity",
    "透光率检测数据": "transmittance_data",
    "活性炭残渣量": "carbon_residue",
    "批次号": "batch_no",
}
NUMBER_FIELDS = {
    "feed_titer",
    "stirring_speed",
    "decolor_temp",
    "holding_time",
    "color_removal_rate",
}
DATE_FIELDS = {}
TABLE = "decolor1"


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


async def sync_decolor1(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(config.app_id, app_secret, config.bitable_app_token)

    # 拉取全部飞书记录
    records_data = await client.list_records(config.table_id, page_size=500)
    items = [i for i in (records_data.get("items") or []) if isinstance(i, dict)]

    feishu_ids = set()
    created, updated = 0, 0

    for item in items:
        rid = item.get("record_id", "")
        feishu_ids.add(rid)
        fields = item.get("fields", {})
        mapped: dict = {"feishu_record_id": rid}

        for fn, db_col in FIELD_MAPPING.items():
            raw = fields.get(fn)
            if raw is None:
                continue
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

        # UPSERT: check if exists by feishu_record_id
        existing = await session.execute(
            text(
                f"SELECT id FROM production.{TABLE} WHERE feishu_record_id = :rid AND is_deleted = false"  # noqa: E501
            ),
            {"rid": rid},
        )
        row = existing.fetchone()

        if row:
            # UPDATE
            set_clause = ", ".join(
                f"{k} = :{k}" for k in mapped if k != "feishu_record_id"
            )
            await session.execute(
                text(f"UPDATE production.{TABLE} SET {set_clause} WHERE id = :id"),
                {"id": row[0], **mapped},
            )
            updated += 1
        else:
            # INSERT
            cols = ", ".join(mapped.keys())
            vals = ", ".join(f":{k}" for k in mapped)
            await session.execute(
                text(
                    f"INSERT INTO production.{TABLE} (id, {cols}) VALUES (gen_random_uuid(), {vals})"  # noqa: E501
                ),
                mapped,
            )
            created += 1

    # DELETE: 标记飞书中已删除的记录为软删除
    if feishu_ids:
        # 使用 ANY + 数组参数
        await session.execute(
            text(
                f"UPDATE production.{TABLE} SET is_deleted = true WHERE is_deleted = false AND feishu_record_id IS NOT NULL AND feishu_record_id != ALL(:ids)"  # noqa: E501
            ),
            {"ids": list(feishu_ids)},
        )

    return {"created": created, "updated": updated, "deleted": 0}
