"""Sync Feishu Bitable data to hr._old / hr._new clone tables.

Usage:
    cd dazah-backend
    uv run python scripts/sync_feishu_to_clone_tables.py

Requires FEISHU_APP_ID and FEISHU_APP_SECRET in environment.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from uuid import uuid4

# Load .env before importing app modules
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.core.database import engine
from app.platform.integrations.feishu.client import FeishuClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

APP_TOKEN = "RfEmb1WyzasCg4sn6tsc4LbWnjf"

# ─── Table configs ───
TABLE_CONFIGS = {
    "employees_old": {
        "feishu_table_id": "tbllxa1JInvTuEoD",
        "db_table": "hr.employees_old",
        "status_default": "在职",
    },
    "employees_new": {
        "feishu_table_id": "tblc0PEd0V1lhIq5",
        "db_table": "hr.employees_new",
        "status_default": "在职",
    },
    "onboarding_old": {
        "feishu_table_id": "tblbyftLfLVlIXKd",
        "db_table": "hr.onboarding_records_old",
    },
    "onboarding_new": {
        "feishu_table_id": "tblFum6xtGF98sti",
        "db_table": "hr.onboarding_records_new",
    },
    "departure_old": {
        "feishu_table_id": "tblGMlpdy6ygPTFG",
        "db_table": "hr.departure_records_old",
    },
    "departure_new": {
        "feishu_table_id": "tbll7T21lbSb0M16",
        "db_table": "hr.departure_records_new",
    },
}


# ─── Field value extractors ───

def _extract_text(value) -> str | None:
    """Extract text from Feishu text / multi-line-text / formula field."""
    if value is None:
        return None
    if isinstance(value, list) and len(value) > 0:
        first = value[0]
        if isinstance(first, dict):
            return first.get("text", "")
        return str(first)
    if isinstance(value, dict):
        # formula with text
        if value.get("type") == 1:
            vals = value.get("value", [])
            if vals and isinstance(vals[0], dict):
                return vals[0].get("text", "")
            if vals:
                return str(vals[0])
        # formula with number -> convert to string
        if value.get("type") == 2:
            vals = value.get("value", [])
            if vals:
                return str(vals[0])
        return str(value)
    return str(value) if value != "" else None


def _extract_number(value) -> int | None:
    """Extract integer from Feishu number / formula field."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, dict):
        if value.get("type") == 2:
            vals = value.get("value", [])
            if vals:
                return int(vals[0])
        # Try to parse from text formula
        if value.get("type") == 1:
            text_val = _extract_text(value)
            if text_val:
                digits = "".join(c for c in text_val if c.isdigit())
                if digits:
                    return int(digits)
    return None


def _extract_date(value) -> date | None:
    """Extract date from Feishu date field (ms timestamp or text)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Feishu returns milliseconds
        ts = value / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.date()
    if isinstance(value, str):
        text = value.strip()
        if text == "" or text == "无":
            return None
        # Try ISO format first
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            pass
        # Try slash format: 2023/11/13 or 2018/7/1
        try:
            parts = text.split("/")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            pass
        # Try Chinese format: 2018年7月1日
        try:
            text = text.replace("年", "-").replace("月", "-").replace("日", "")
            parts = text.split("-")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except (ValueError, IndexError):
            pass
        return None
    return None


def _extract_multi_select_first(value) -> str | None:
    """Extract first value from multi-select as text."""
    if value is None:
        return None
    if isinstance(value, list) and len(value) > 0:
        first = value[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("text", "")
        return str(first)
    return _extract_single_select(value)


def _extract_single_select_as_list(value) -> list[str] | None:
    """Extract single select value and wrap in list for JSON fields."""
    val = _extract_single_select(value)
    return [val] if val else None


def _extract_single_select(value) -> str | None:
    """Extract single select value."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _extract_text(value)
    return str(value)


def _extract_multi_select(value) -> list[str] | None:
    """Extract multi-select values as JSON-compatible list."""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return None


def _extract_phone(value) -> str | None:
    """Extract phone number."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return str(int(value))
    return str(value)


# ─── Field mappings ───

EMPLOYEE_FIELD_MAP = {
    "employee_number": ("工号", _extract_text),
    "name": ("姓名", _extract_text),
    "department": ("部门", _extract_single_select),
    "team": ("班组", _extract_single_select),
    "position": ("职位", _extract_text),
    "phone": ("手机", _extract_phone),
    "email": ("邮箱地址", _extract_text),
    "domain_account": ("域账号", _extract_text),
    "job_category": ("职类", _extract_single_select),
    "level": ("级别", _extract_single_select),
    "qualifications": ("职称／职业资格", _extract_multi_select),
    "qualification_type": ("职称类型", _extract_single_select),
    "gender": ("性别", _extract_single_select),
    "native_place": ("籍贯", _extract_text),
    "political_status": ("政治面貌", _extract_single_select),
    "marital_status": ("婚姻状况", _extract_single_select),
    "household_type": ("户籍类型", _extract_single_select),
    "status_category": ("统计类别", _extract_single_select),
    "birth_year": ("年", _extract_number),
    "birth_month": ("月", _extract_number),
    "birth_day": ("日", _extract_number),
    "age": ("年龄", _extract_number),
    "work_start_date": ("参加工作时间", _extract_date),
    "factory_entry_date": ("进厂时间", _extract_date),
    "livo_entry_date": ("入丽珠时间", _extract_date),
    "hire_date": ("入职时间", _extract_date),
    "graduation_date": ("毕业时间", _extract_date),
    "work_years": ("工作年限", _extract_number),
    "factory_tenure": ("厂龄", _extract_text),
    "company_tenure": ("司龄", _extract_text),
    "classification": ("分类", _extract_single_select),
    "school": ("毕业学校", _extract_text),
    "major": ("专业", _extract_text),
    "education": ("学历", _extract_single_select),
    "id_card": ("身份证号", _extract_text),
    "id_card_expiry": ("身份证到期日", _extract_text),
    "id_card_address": ("身份证地址|家庭地址", _extract_text),
    "current_address": ("现住址", _extract_text),
    "contract_type": ("合同期限", _extract_single_select),
    "contract_start_date": ("第一次合同起点时间", _extract_date),
    "contract_end_date": ("第一次合同终止时间", _extract_date),
    "contract_start_2": ("第二次合同起点时间", _extract_date),
    "contract_end_2": ("第二次合同终止时间", _extract_date),
    "contract_start_3": ("第三次合同起点时间", _extract_date),
    "contract_end_3": ("第三次合同终止时间", _extract_date),
    "contract_start_4": ("第四次合同起点时间", _extract_date),
    "contract_end_4": ("第四次合同终止时间", _extract_date),
    "emergency_contact_relation": ("紧急联系人|关系", _extract_text),
    "bank_account": ("银行卡号", _extract_text),
    "training_id": ("培训档案编号", _extract_text),
    "transfer_history": ("异动（含曾经工作部门、岗位)", _extract_text),
    "remarks": ("备注", _extract_multi_select),
    "feishu_record_id": ("record_id", lambda v: v),  # special, added later
}

ONBOARDING_FIELD_MAP = {
    "employee_number": ("工号", _extract_text),
    "name": ("姓名", _extract_text),
    "department": ("部门", _extract_single_select),
    "team": ("班组", _extract_text),
    "position": ("岗位", _extract_text),
    "domain_account": ("域账号", _extract_text),
    "job_category": ("职类", _extract_single_select),
    "status_category": ("统计类别", _extract_single_select),
    "is_employed": ("是否在职", _extract_single_select),
    "hire_date": ("入职时间", _extract_date),
    "factory_entry_date": ("进厂时间", _extract_date),
    "livo_entry_date": ("入丽珠时间", _extract_date),
    "work_start_date": ("参加工作时间", _extract_date),
    "graduation_date": ("毕业时间", _extract_date),
    "birth_month": ("月", _extract_number),
    "birth_day": ("日", _extract_number),
    "age": ("年龄", _extract_number),
    "work_years": ("工作年限", _extract_number),
    "factory_tenure": ("厂龄", _extract_text),
    "company_tenure": ("司龄", _extract_text),
    "hire_month": ("入职月份", _extract_text),
    "school": ("毕业学校", _extract_text),
    "education": ("学历", _extract_single_select),
    "major": ("专业", _extract_text),
    "classification": ("分类", _extract_single_select),
    "id_card": ("身份证号", _extract_text),
    "id_card_expiry": ("身份证到期日", _extract_text),
    "id_card_address": ("身份证地址|家庭地址", _extract_text),
    "current_address": ("现住址", _extract_text),
    "marital_status": ("婚姻状况", _extract_single_select),
    "household_type": ("户籍类型", _extract_single_select),
    "political_status": ("政治面貌", _extract_single_select),
    "phone": ("手机", _extract_phone),
    "email": ("邮箱地址", _extract_text),
    "emergency_contact_phone": ("紧急联系人电话", _extract_phone),
    "emergency_contact_relation": ("紧急联系人|关系", _extract_text),
    "bank_account": ("银行卡号", _extract_text),
    "bank_account_location": ("银行卡开户地", _extract_single_select),
    "training_id": ("培训档案编号", _extract_text),
    "transfer_history": ("异动", _extract_text),
    "remarks": ("备注", _extract_multi_select),
    "contract_type": ("合同期限", _extract_single_select),
    "contract_start_date": ("第一次合同起点时间", _extract_date),
    "contract_end_date": ("第一次合同终止时间", _extract_date),
    "contract_start_2": ("第二次合同起点时间", _extract_date),
    "contract_end_2": ("第二次合同终止时间", _extract_date),
    "contract_start_3": ("第三次合同起点时间", _extract_date),
    "contract_end_3": ("第三次合同终止时间", _extract_date),
    "contract_start_4": ("第四次合同起点时间", _extract_date),
    "contract_end_4": ("第四次合同终止时间", _extract_date),
    "feishu_record_id": ("record_id", lambda v: v),
}

DEPARTURE_FIELD_MAP = {
    "name": ("姓名", _extract_text),
    "department": ("部门", _extract_text),
    "team": ("班组", _extract_text),
    "position": ("职位", _extract_text),
    "job_category": ("职类", _extract_text),
    "gender": ("性别", _extract_single_select),
    "status_category": ("统计类别", _extract_text),
    "livo_entry_date": ("入丽珠时间", _extract_date),
    "factory_entry_date": ("进厂时间", _extract_date),
    "work_start_date": ("参加工作时间", _extract_date),
    "offboarding_date": ("离职日期", _extract_date),
    "company_tenure_at_leave": ("司龄", _extract_text),
    "education": ("学历", _extract_text),
    "school": ("毕业学校", _extract_text),
    "major": ("专业", _extract_text),
    "classification": ("分类", _extract_single_select),
    "id_card": ("身份证号", _extract_text),
    "native_place": ("籍贯", _extract_text),
    "household_type": ("户籍类型", _extract_single_select),
    "marital_status": ("婚姻状况", _extract_single_select),
    "political_status": ("政治面貌", _extract_single_select),
    "phone": ("手机", _extract_text),
    "emergency_contact_phone": ("紧急联系人电话", _extract_text),
    "emergency_contact_relation": ("紧急联系人|关系", _extract_text),
    "bank_account": ("银行卡号", _extract_text),
    "contract_type": ("合同期限", _extract_single_select),
    "transfer_history": ("异动(含曾经工作部门、岗位)", _extract_text),
    "offboarding_type": ("离职类型", _extract_single_select),
    "offboarding_reason": ("离职原因", _extract_single_select_as_list),
    "remarks": ("备注", _extract_text),
    "feishu_record_id": ("record_id", lambda v: v),
}


# New factory departure table has different field types (text dates, multi-select team, etc.)
DEPARTURE_NEW_FIELD_MAP = {
    "name": ("姓名", _extract_text),
    "department": ("部门", _extract_text),
    "team": ("班组", _extract_multi_select_first),
    "position": ("职位", _extract_text),
    "job_category": ("职类", _extract_single_select),
    "gender": ("性别", _extract_single_select),
    "status_category": ("统计类别", _extract_single_select),
    "livo_entry_date": ("入丽珠时间", _extract_date),
    "factory_entry_date": ("进厂时间", _extract_date),
    "work_start_date": ("参加工作时间", _extract_date),
    "offboarding_date": ("离职日期", _extract_date),
    "company_tenure_at_leave": ("司龄", _extract_text),
    "education": ("学历", _extract_single_select),
    "school": ("毕业学校", _extract_text),
    "major": ("专业", _extract_text),
    "classification": ("分类", _extract_single_select),
    "id_card": ("身份证号", _extract_text),
    "native_place": ("籍贯", _extract_text),
    "household_type": ("户籍类型", _extract_single_select),
    "marital_status": ("婚姻状况", _extract_single_select),
    "political_status": ("政治面貌", _extract_single_select),
    "phone": ("手机", _extract_text),
    "emergency_contact_phone": ("紧急联系人电话", _extract_text),
    "emergency_contact_relation": ("紧急联系人|关系", _extract_text),
    "bank_account": ("银行卡号", _extract_text),
    "contract_type": ("合同期限", _extract_single_select),
    "transfer_history": ("异动(含曾经工作部门、岗位)", _extract_text),
    "offboarding_type": ("离职类型", _extract_single_select),
    "offboarding_reason": ("离职原因", _extract_single_select_as_list),
    "remarks": ("备注", _extract_text),
    "feishu_record_id": ("record_id", lambda v: v),
}


def _build_record(fields: dict, mapping: dict, defaults: dict | None = None) -> dict:
    """Map Feishu fields to DB record using a field mapping."""
    record = {}
    if defaults:
        record.update(defaults)

    for db_col, (fs_name, extractor) in mapping.items():
        if db_col == "feishu_record_id":
            continue  # handled separately
        raw = fields.get(fs_name)
        try:
            val = extractor(raw)
        except Exception as e:
            logger.warning("  Field extract error %s=%r: %s", fs_name, raw, e)
            val = None
        if val is not None:
            # Serialize JSON fields for raw SQL parameter binding
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            record[db_col] = val

    return record


def _build_insert_sql(table: str, record: dict) -> tuple[str, dict]:
    """Build INSERT SQL and parameters."""
    cols = list(record.keys())
    placeholders = [f":{c}" for c in cols]
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
    return sql, record


# ─── Sync logic ───

async def sync_table(
    client: FeishuClient,
    conn,
    feishu_table_id: str,
    db_table: str,
    field_map: dict,
    defaults: dict | None = None,
):
    """Sync all records from a Feishu table to a DB table."""
    logger.info("Syncing %s -> %s", feishu_table_id, db_table)

    # Clear existing data
    await conn.execute(text(f"DELETE FROM {db_table}"))

    # Fetch all records from Feishu
    records_data = await client.request(
        "POST",
        f"/bitable/v1/apps/{APP_TOKEN}/tables/{feishu_table_id}/records/search",
        json={"page_size": 500},
    )
    items = records_data.get("items", [])
    total = records_data.get("total", len(items))
    logger.info("  Feishu records: %d", total)

    inserted = 0
    errors = 0
    for item in items:
        record_id = item.get("record_id")
        fields = item.get("fields", {})

        record = _build_record(fields, field_map, defaults)
        record["feishu_record_id"] = record_id

        # Post-process: employees_old has no "入职时间", use "入丽珠时间" as hire_date
        if db_table == "hr.employees_old" and not record.get("hire_date") and record.get("livo_entry_date"):
            record["hire_date"] = record["livo_entry_date"]

        # Skip records with empty required fields
        if db_table in ("hr.employees_old", "hr.employees_new"):
            if not record.get("employee_number"):
                errors += 1
                logger.warning("  Skipping record %s: missing employee_number", record_id)
                continue
            if not record.get("hire_date"):
                errors += 1
                logger.warning("  Skipping record %s: missing hire_date", record_id)
                continue
        if db_table in ("hr.onboarding_records_old", "hr.onboarding_records_new"):
            if not record.get("employee_number"):
                errors += 1
                logger.warning("  Skipping record %s: missing employee_number", record_id)
                continue
            if not record.get("hire_date"):
                errors += 1
                logger.warning("  Skipping record %s: missing hire_date", record_id)
                continue
        if db_table in ("hr.departure_records_old", "hr.departure_records_new"):
            if not record.get("name"):
                errors += 1
                logger.warning("  Skipping record %s: missing name", record_id)
                continue

        try:
            sql, params = _build_insert_sql(db_table, record)
            await conn.execute(text(sql), params)
            inserted += 1
        except Exception as e:
            errors += 1
            logger.error("  Insert error for record %s: %s", record_id, e)
            if errors <= 3:
                logger.error("  Record data: %s", json.dumps(record, ensure_ascii=False, default=str))
            raise  # re-raise so the per-table transaction can rollback

    logger.info("  Inserted: %d, Errors: %d", inserted, errors)
    return inserted, errors


async def _sync_one_table(client, config_key, field_map, defaults=None):
    """Sync a single table in its own transaction."""
    cfg = TABLE_CONFIGS[config_key]
    try:
        async with engine.begin() as conn:
            return await sync_table(
                client, conn,
                cfg["feishu_table_id"],
                cfg["db_table"],
                field_map,
                defaults=defaults,
            )
    except Exception as e:
        logger.error("Failed to sync %s: %s", cfg["db_table"], e)
        return 0, 0


async def main():
    client = FeishuClient()

    # ─── 在职花名册 ───
    await _sync_one_table(
        client, "employees_old", EMPLOYEE_FIELD_MAP,
        defaults={"status": "在职"},
    )
    await _sync_one_table(
        client, "employees_new", EMPLOYEE_FIELD_MAP,
        defaults={"status": "在职"},
    )

    # ─── 入职 ───
    await _sync_one_table(client, "onboarding_old", ONBOARDING_FIELD_MAP)
    await _sync_one_table(client, "onboarding_new", ONBOARDING_FIELD_MAP)

    # ─── 离职 ───
    await _sync_one_table(
        client, "departure_old", DEPARTURE_FIELD_MAP,
        defaults={"offboarding_type": "辞职"},
    )
    await _sync_one_table(
        client, "departure_new", DEPARTURE_NEW_FIELD_MAP,
    )

    logger.info("Sync completed.")


if __name__ == "__main__":
    if not os.getenv("FEISHU_APP_ID") or not os.getenv("FEISHU_APP_SECRET"):
        print("[!] Please set FEISHU_APP_ID and FEISHU_APP_SECRET")
        sys.exit(1)
    asyncio.run(main())
