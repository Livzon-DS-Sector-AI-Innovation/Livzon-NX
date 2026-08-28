"""飞书 → pretreatments 同步服务"""
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
    "批号": "received_batch",
    "进罐发酵液总量": "broth_volume",
    "调酸用酸种类": "acid_type",
    "酸加入体积/重量": "acid_amount",
    "中和终点pH": "neutralize_ph",
    "稀释用水体积": "dilution_water_volume",
    "稀释倍数": "dilution_ratio",
    "升温目标温度": "target_temp",
    "保温时长": "holding_time",
    "升降温曲线": "temp_curve",
    "静置分层时长": "settling_time",
    "静置温度": "settling_temp",
    "搅拌转速": "stirring_speed",
    "搅拌启停时间": "stirring_time",
    "上层清液量": "supernatant_volume",
    "下层菌丝渣重量/体积": "sediment_weight",
    "预处理前效价": "titer_before",
    "预处理后效价": "titer_after",
    "收率": "yield_rate",
    "杂质含量": "impurity_content",
    "预处理损耗": "loss",
    "渣中残留效价": "residue_titer",
}

NUMBER_FIELDS = {
    "seq_no",
    "neutralize_ph",
    "target_temp",
    "settling_temp",
    "titer_before",
    "titer_after",
    "yield_rate",
    "impurity_content",
    "loss",
    "residue_titer",
}
DATE_FIELDS: set[str] = set()


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


async def sync_pretreatment(
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
        f"INSERT INTO production.pretreatments (id, {', '.join(all_cols)}) VALUES "
        + ", ".join(values_clauses)
        + " ON CONFLICT DO NOTHING"
    )
    await session.execute(sql, params)
    return {"created": len(rows), "updated": 0}
