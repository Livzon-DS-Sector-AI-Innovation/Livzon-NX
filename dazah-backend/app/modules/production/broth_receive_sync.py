"""飞书 → broth_receives 同步服务"""
import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

# 飞书字段名 → DB列名
FIELD_MAPPING = {
    "序号": "seq_no",
    "接收批次": "received_batch",
    "发酵罐号": "fermenter_no",
    "发酵批号": "fermentation_batch",
    "接收体积/重量": "received_volume",
    "发酵液OD": "broth_od",
    "效价（u/mL）": "titer_u_ml",
    "效价（mg/L）": "titer_mg_l",
    "发酵液pH": "broth_ph",
    "温度": "temperature",
    "菌丝浓度": "mycelium_concentration",
    "残糖": "residual_sugar",
    "氨基氮": "amino_nitrogen",
    "进厂/接收时间": "receive_time",
    "供方班组": "supplier_team",
    "罐底渣量": "tank_bottom_residue",
    "取样编号": "sample_no",
    "取样时间": "sample_time",
    "检验结果": "inspection_result",
    "合格判定": "qualified",
    "接收损耗量": "receive_loss",
    "输送管路跑冒滴漏记录": "pipeline_leak_record",
}

NUMBER_FIELDS = {
    "seq_no",
    "broth_od",
    "titer_u_ml",
    "titer_mg_l",
    "broth_ph",
    "temperature",
    "mycelium_concentration",
    "residual_sugar",
    "amino_nitrogen",
    "tank_bottom_residue",
    "receive_loss",
}
DATE_FIELDS = {"receive_time", "sample_time"}


def _extract_text(field_value: Any) -> str | None:
    if field_value is None:
        return None
    if isinstance(field_value, str):
        return field_value.strip() or None
    if isinstance(field_value, dict):
        return (
            str(field_value.get("name") or field_value.get("text", "")).strip() or None
        )
    if isinstance(field_value, list) and field_value:
        first = field_value[0]
        if isinstance(first, str):
            return first.strip() or None
        if isinstance(first, dict):
            return str(first.get("name") or first.get("text", "")).strip() or None
    return str(field_value).strip() or None


def _extract_number(field_value: Any) -> float | None:
    if isinstance(field_value, (int, float)):
        return float(field_value)
    text = _extract_text(field_value)
    if text is None:
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


def _parse_date(v: Any) -> Any:
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


async def sync_broth_receive(
    config: ProductionFeishuConfig, session: AsyncSession
) -> dict[str, Any]:
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(config.app_id, app_secret, config.bitable_app_token)

    records_data = await client.list_records(config.table_id, page_size=500)
    items = [i for i in (records_data.get("items") or []) if isinstance(i, dict)]

    rows = []
    for item in items:
        fields = item.get("fields", {})
        mapped: dict[str, Any] = {}
        for feishu_name, db_col in FIELD_MAPPING.items():
            raw = fields.get(feishu_name)
            if raw is None:
                continue
            val: Any
            if db_col in DATE_FIELDS:
                val = _extract_text(raw)
                if val is not None:
                    mapped[db_col] = _parse_date(val)
                continue
            if db_col in NUMBER_FIELDS:
                val = _extract_number(raw)
            else:
                val = _extract_text(raw)
            if val is not None:
                mapped[db_col] = val
        if not mapped.get("received_batch"):
            continue
        rows.append(mapped)

    if not rows:
        return {"created": 0, "updated": 0}

    all_cols = sorted(set().union(*(r.keys() for r in rows)))
    params: dict[str, Any] = {}
    values_clauses = []
    for i, row in enumerate(rows):
        vals = ", ".join(f":{c}_{i}" for c in all_cols)
        values_clauses.append(f"(gen_random_uuid(), {vals})")
        for c in all_cols:
            params[f"{c}_{i}"] = row.get(c)

    ", ".join(
        f"{c} = EXCLUDED.{c}" for c in all_cols if c != "received_batch"
    )

    sql = text(
        f"INSERT INTO production.broth_receives (id, {', '.join(all_cols)}) VALUES "
        + ", ".join(values_clauses)
        + " ON CONFLICT DO NOTHING"
    )
    await session.execute(sql, params)
    return {"created": len(rows), "updated": 0}
