"""飞书 → filter1 全量同步（INSERT/UPDATE/DELETE）"""
import logging
from datetime import date, datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

FIELD_MAPPING = {"批次号":"batch_no","脱色液进料总量":"feed_volume","进料 pH 值":"feed_ph","进料温度(℃)":"feed_temp","进料效价(U/mL)":"feed_titer","板框压力(MPa)":"filter_pressure","进料流量(L/h)":"feed_flow","过滤总时长(h)":"filter_duration","滤布编号(-)":"cloth_no","滤清液总量(L)":"filtrate_volume","滤清液效价(U/mL)":"filtrate_titer","滤饼（炭渣）湿重(kg)":"cake_wet_weight","滤饼（炭渣）干重(kg)":"cake_dry_weight","滤饼残留效价(U/g)":"cake_residue_titer","板框管道残留量(L)":"pipe_residue","滤饼含水率(%)":"cake_moisture","过滤收率(%)":"filter_yield","备注":"remarks"}
NUMBER_FIELDS = {"feed_ph","feed_temp","feed_titer","filter_pressure","feed_flow","filter_duration","filtrate_titer","cake_residue_titer","cake_moisture","filter_yield"}
DATE_FIELDS = {}
TABLE = "filter1"

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

async def sync_filter1(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(config.app_id, app_secret, config.bitable_app_token)

    # 拉取全部飞书记录
    records_data = await client.list_records(config.table_id, page_size=500)
    items = [i for i in (records_data.get("items") or []) if isinstance(i, dict)]

    feishu_ids = set()
    created, updated = 0, 0
    matched_fields: set = set()  # 追踪哪些映射键实际匹配到了数据

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

        # UPSERT: check if exists by feishu_record_id
        existing = await session.execute(
            text(f"SELECT id FROM production.{TABLE} WHERE feishu_record_id = :rid AND is_deleted = false"),
            {"rid": rid}
        )
        row = existing.fetchone()

        if row:
            # UPDATE
            set_clause = ", ".join(f"{k} = :{k}" for k in mapped if k != "feishu_record_id")
            await session.execute(
                text(f"UPDATE production.{TABLE} SET {set_clause} WHERE id = :id"),
                {"id": row[0], **mapped}
            )
            updated += 1
        else:
            # INSERT
            cols = ", ".join(mapped.keys())
            vals = ", ".join(f":{k}" for k in mapped)
            await session.execute(
                text(f"INSERT INTO production.{TABLE} (id, {cols}) VALUES (gen_random_uuid(), {vals})"),
                mapped
            )
            created += 1

    # DELETE: 标记飞书中已删除的记录为软删除
    if feishu_ids:
        await session.execute(
            text(f"UPDATE production.{TABLE} SET is_deleted = true WHERE is_deleted = false AND feishu_record_id IS NOT NULL AND feishu_record_id != ALL(:ids)"),
            {"ids": list(feishu_ids)}
        )

    # 检测字段匹配情况
    unmatched = sorted(set(FIELD_MAPPING.keys()) - matched_fields)
    if unmatched:
        logger.warning("filter1 同步警告：以下 %d 个映射字段在飞书中未找到数据：%s", len(unmatched), unmatched)

    return {"created": created, "updated": updated, "deleted": 0,
            "unmatched_fields": unmatched if unmatched else []}
