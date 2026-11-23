"""
Feishu → seed_cultures sync service.
Maps Feishu field names to seed_cultures columns using predefined mapping.
"""

import json
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

# 飞书成员类型字段：同步解析 open_id → 姓名+头像，入库为 JSONB 数组
PERSON_FIELDS = {
    "prepare_operator",
    "sterilization_operator",
    "shaker_setup_operator",
    "inoculation_operator",
    "tank_setup_operator",
    "merge_operator",
    "workshop_inoculation_operator",
}


def _extract_person_ids(field_value: Any) -> list[str]:
    """人员字段值 → open_id 列表（bitable records: [{"id": "ou_x"}]）。"""
    if isinstance(field_value, dict):
        open_id = field_value.get("id")
        return [str(open_id)] if open_id else []
    if isinstance(field_value, list):
        return [
            str(entry["id"])
            for entry in field_value
            if isinstance(entry, dict) and entry.get("id")
        ]
    return []


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


async def _resolve_people(
    client: ProductionFeishuClient,
    open_ids: list[str],
    cache: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """批量把飞书成员 open_id 解析为姓名+头像；失败保留 open_id。"""
    people: list[dict[str, Any]] = []
    for open_id in open_ids:
        cached = cache.get(open_id)
        if cached is not None:
            people.append(dict(cached))
            continue
        info: dict[str, Any] = {"open_id": open_id, "name": "", "avatar_url": None}
        try:
            data = await client._request(
                "GET",
                f"/contact/v3/users/{open_id}",
                params={"user_id_type": "open_id"},
            )
            user = data.get("user") or {}
            info["name"] = str(user.get("name") or "")
            avatar = user.get("avatar") or {}
            info["avatar_url"] = (
                avatar.get("avatar_240") or avatar.get("avatar_72") or None
            )
        except Exception:  # noqa: BLE001 —— 通讯录权限缺失等，降级保留 open_id
            logger.warning("seed culture contact resolve failed: %s", open_id)
        cache[open_id] = dict(info)
        people.append(info)
    return people


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

    # Fetch all records from feishu（分页拉全量）
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        records_data = await client.list_records(
            config.table_id, page_size=500, page_token=page_token
        )
        raw_items = records_data.get("items") or []
        items.extend(i for i in raw_items if isinstance(i, dict))
        if not records_data.get("has_more"):
            break
        page_token = records_data.get("page_token")
        if not page_token:
            break

    person_cache: dict[str, dict[str, Any]] = {}
    unresolved_people = 0
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
            if db_col in PERSON_FIELDS:
                open_ids = _extract_person_ids(raw)
                if not open_ids:
                    continue
                people = await _resolve_people(client, open_ids, person_cache)
                unresolved_people += sum(1 for p in people if not p.get("name"))
                mapped[f"{db_col}_people"] = people
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

    # 飞书表可能存在同批号多行（历史编辑遗留）：按 (批号, 产品) 去重，
    # 保留靠后的行（视为最新编辑），避免批量 upsert 同行二冲突
    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        dedup[(row["batch_no"], row.get("product_name") or "")] = row
    duplicate_count = len(rows) - len(dedup)
    if duplicate_count:
        logger.warning(
            "seed culture sync: %d duplicate batch rows deduped", duplicate_count
        )
    rows = list(dedup.values())

    if not rows:
        return {
            "created": 0,
            "updated": 0,
            "person_unresolved": 0,
            "duplicates_deduped": duplicate_count,
        }

    # 收集所有行中的列名（第一行可能字段不全）
    all_cols_set: set[Any] = set()
    for row in rows:
        all_cols_set.update(row.keys())
    cols = sorted(all_cols_set)  # 确保每次查询顺序一致

    # Re-structure: one flat dict with indexed param names；
    # JSONB 人员列以 json.dumps 传参 + 显式 ::jsonb cast
    person_columns = {f"{field}_people" for field in PERSON_FIELDS}
    params: dict[str, Any] = {}
    for i, row in enumerate(rows):
        for c in cols:
            value = row.get(c)
            if c in person_columns and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            params[f"{c}_{i}"] = value

    values_clauses = []
    for i in range(len(rows)):
        vals = ", ".join(
            f"CAST(:{c}_{i} AS jsonb)" if c in person_columns else f":{c}_{i}"
            for c in cols
        )
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
    return {
        "created": len(rows),
        "updated": 0,
        "person_unresolved": unresolved_people,
        "duplicates_deduped": duplicate_count,
    }
