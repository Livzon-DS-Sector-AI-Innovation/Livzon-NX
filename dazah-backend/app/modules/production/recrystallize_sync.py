"""飞书 → recrystallize 全量同步"""
import logging
from datetime import date, datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

FIELD_MAPPING = {"批次":"batch_no","上清液总量(L)":"feed_volume","上清液效价(U/mL)":"feed_titer","溶剂投加量(L)":"solvent_amount","纯水投加量(L)":"water_amount","溶剂配比(V/V)":"solvent_ratio","脱色炭/树脂投加量(%)":"carbon_dosage","升温溶解温度(℃)":"dissolve_temp","保温时间(min)":"holding_time","降温速率(℃/h)":"cooling_rate","终点结晶温度(℃)":"crystal_temp","养晶时长(h)":"crystal_time","结晶液色度(Hazen)":"color_hazen","透光率(%)":"transmittance","晶体粒度(μm)":"crystal_size","母液效价(U/mL)":"mother_liquor_titer","备注":"remarks"}
NUMBER_FIELDS = {"feed_titer","carbon_dosage","dissolve_temp","holding_time","cooling_rate","crystal_temp","crystal_time","color_hazen","transmittance","crystal_size","mother_liquor_titer"}
DATE_FIELDS = {}
TABLE = "recrystallize"

def _ext(fv):
    if fv is None: return None
    if isinstance(fv, str): return fv.strip() or None
    if isinstance(fv, dict): return str(fv.get("name") or fv.get("text","")).strip() or None
    if isinstance(fv, list) and fv:
        f = fv[0]
        if isinstance(f, str): return f.strip() or None
        if isinstance(f, dict): return str(f.get("name") or f.get("text","")).strip() or None
    return str(fv).strip() or None

def _num(fv):
    if isinstance(fv, (int, float)): return float(fv)
    t = _ext(fv)
    if t is None: return None
    try: return float(t)
    except (ValueError, TypeError): return None

def _pd(v):
    if v is None: return None
    if isinstance(v, (int, float)) and 0 < v < 1e15: return datetime.fromtimestamp(v/1000).date()
    if isinstance(v, str):
        try: return date.fromisoformat(v)
        except ValueError: return None
    return v

async def sync_recrystallize(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
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
            if raw is None: continue
            matched_fields.add(fn)
            if db_col in DATE_FIELDS:
                if isinstance(raw, (int, float)): mapped[db_col] = _pd(raw)
                else: v = _ext(raw); mapped[db_col] = _pd(v) if v else None
                continue
            v = _num(raw) if db_col in NUMBER_FIELDS else _ext(raw)
            if v is not None: mapped[db_col] = v
        if not mapped.get("batch_no"): continue

        existing = await session.execute(
            text(f"SELECT id FROM production.{TABLE} WHERE feishu_record_id = :rid AND is_deleted = false"),
            {"rid": rid})
        row = existing.fetchone()
        if row:
            set_clause = ", ".join(f"{k} = :{k}" for k in mapped if k != "feishu_record_id")
            await session.execute(text(f"UPDATE production.{TABLE} SET {set_clause} WHERE id = :id"), {"id": row[0], **mapped})
            updated += 1
        else:
            cols = ", ".join(mapped.keys())
            vals = ", ".join(f":{k}" for k in mapped)
            await session.execute(text(f"INSERT INTO production.{TABLE} (id, {cols}) VALUES (gen_random_uuid(), {vals})"), mapped)
            created += 1

    if feishu_ids:
        await session.execute(text(f"UPDATE production.{TABLE} SET is_deleted = true WHERE is_deleted = false AND feishu_record_id IS NOT NULL AND feishu_record_id != ALL(:ids)"), {"ids": list(feishu_ids)})

    unmatched = sorted(set(FIELD_MAPPING.keys()) - matched_fields)
    if unmatched:
        logger.warning("recrystallize 同步警告：%d 个字段未匹配：%s", len(unmatched), unmatched)
    return {"created": created, "updated": updated, "deleted": 0, "unmatched_fields": unmatched if unmatched else []}
