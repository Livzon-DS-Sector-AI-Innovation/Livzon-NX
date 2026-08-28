"""
Feishu → seed_cultures sync service.
Maps Feishu field names to seed_cultures columns using predefined mapping.
"""
import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

# 飞书字段名 → seed_cultures 数据库列名
FIELD_MAPPING = {
    "摇瓶批号": "batch_no",
    "配置日期": "prepare_date",
    "葡萄糖/批号": "glucose_batch",
    "玉米淀粉/批号": "corn_starch_batch",
    "玉米浆/批号": "corn_syrup_batch",
    "硫酸铵/批号": "ammonium_sulfate_batch",
    "黄豆饼粉/批号": "soybean_meal_batch",
    "碳酸钙/批号": "calcium_carbonate_batch",
    "配制操作人/复核人": "prepare_operator",
    "种子消毒人员": "sterilization_operator",
    "调前PH": "ph_before_adjust",
    "调后PH": "ph_after_adjust",
    "消后PH": "ph_after_sterilization",
    "还原糖": "reducing_sugar",
    "总糖": "total_sugar",
    "氨基氮": "amino_nitrogen",
    "冻管菌号": "strain_tube_no",
    "上摇床摆东西人员": "shaker_setup_operator",
    "摇床编号": "shaker_no",
    "上摇床日期": "shaker_start_date",
    "接种人员/复核人": "inoculation_operator",
    "用具编号": "tool_no",
    "并瓶时间": "merge_time",
    "并瓶数量(瓶）": "merge_count",
    "并瓶周期": "merge_cycle",
    "并瓶PH": "merge_ph",
    "并瓶菌浓": "merge_bacteria_density",
    "并瓶总糖": "merge_total_sugar",
    "并瓶还原糖": "merge_reducing_sugar",
    "并瓶氨基氮": "merge_amino_nitrogen",
    "进罐摆东西人员": "tank_setup_operator",
    "钢瓶编号": "cylinder_no",
    "并瓶操作人/复核人": "merge_operator",
    "车间接种人员": "workshop_inoculation_operator",
    "备注（罐号）": "tank_remarks",
    "罐产": "tank_yield",
    "备注": "remarks",
}

TYPE_CONVERTERS = {
    "prepare_date": lambda v: _parse_date(v),
    "shaker_start_date": lambda v: _parse_date(v),
    "merge_time": lambda v: _parse_date(v),
    "merge_count": lambda v: int(v) if v else None,
    "ph_before_adjust": lambda v: float(v) if v else None,
    "ph_after_adjust": lambda v: float(v) if v else None,
    "ph_after_sterilization": lambda v: float(v) if v else None,
    "reducing_sugar": lambda v: float(v) if v else None,
    "total_sugar": lambda v: float(v) if v else None,
    "amino_nitrogen": lambda v: float(v) if v else None,
    "merge_ph": lambda v: float(v) if v else None,
    "merge_bacteria_density": lambda v: float(v) if v else None,
    "merge_total_sugar": lambda v: float(v) if v else None,
    "merge_reducing_sugar": lambda v: float(v) if v else None,
    "merge_amino_nitrogen": lambda v: float(v) if v else None,
    "tank_yield": lambda v: float(v) if v else None,
}

STRING_FIELDS = {k for k in FIELD_MAPPING.values() if k not in TYPE_CONVERTERS}
DATE_FIELDS = {"prepare_date", "shaker_start_date", "merge_time"}


def _parse_date(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 0 and v < 1e15:
        return datetime.fromtimestamp(v / 1000).date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return v


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
            # 人员字段: {"name": "张三"} 或文本字段: {"text": "xxx"}
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


async def sync_seed_culture_to_table(
    config: ProductionFeishuConfig, session: AsyncSession
) -> dict[str, Any]:
    """Sync feishu records to seed_cultures table using bulk upsert."""
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(
        app_id=config.app_id,
        app_secret=app_secret,
        app_token=config.bitable_app_token,
    )

    # Fetch all records from feishu
    records_data = await client.list_records(config.table_id, page_size=500)
    raw_items = records_data.get("items") or []
    items = [i for i in raw_items if isinstance(i, dict)]

    rows = []
    for item in items:
        fields = item.get("fields", {})
        mapped: dict[str, Any] = {"product_name": config.product_name or ""}
        for feishu_name, db_col in FIELD_MAPPING.items():
            raw = fields.get(feishu_name)
            if raw is None:
                continue
            if db_col in DATE_FIELDS:
                # 日期字段：数字（时间戳）直接解析，文本先提取再解析
                if isinstance(raw, (int, float)):
                    mapped[db_col] = _parse_date(raw)
                else:
                    date_value = _extract_text(raw)
                    if date_value is not None:
                        mapped[db_col] = _parse_date(date_value)
                continue
            val: Any
            if db_col in STRING_FIELDS:
                val = _extract_text(raw)
            else:
                val = _extract_number(raw)
            if val is not None:
                conv: Any = TYPE_CONVERTERS.get(db_col)
                mapped[db_col] = conv(val) if conv else val
        if not mapped.get("batch_no"):
            continue
        rows.append(mapped)

    if not rows:
        return {"created": 0, "updated": 0}

    # 收集所有行中的列名（第一行可能字段不全）
    all_cols_set: set[Any] = set()
    for row in rows:
        all_cols_set.update(row.keys())
    cols = sorted(all_cols_set)  # 确保每次查询顺序一致
    ", ".join(f":{c}_{i}" for i in range(len(rows)) for c in cols)
    # Re-structure: one flat dict with indexed param names
    params: dict[str, Any] = {}
    for i, row in enumerate(rows):
        for c in cols:
            params[f"{c}_{i}"] = row.get(c)

    values_clauses = []
    for i in range(len(rows)):
        vals = ", ".join(f":{c}_{i}" for c in cols)
        values_clauses.append(f"(gen_random_uuid(), {vals})")

    all_cols = "id, " + ", ".join(cols)
    update_set = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in cols if c not in ("batch_no", "product_name")
    )

    sql = (
        f"INSERT INTO production.seed_cultures ({all_cols}) VALUES "
        + ", ".join(values_clauses)
        + f" ON CONFLICT (batch_no, product_name) WHERE is_deleted = false DO UPDATE SET {update_set}"  # noqa: E501
    )

    await session.execute(text(sql), params)
    return {"created": len(rows), "updated": 0}
