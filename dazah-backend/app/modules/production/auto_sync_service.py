"""Auto-discover Feishu fields and sync generically — no manual field mapping needed."""

import logging
import re
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import decrypt_secret
from app.modules.production.production_feishu_client import ProductionFeishuClient
from app.modules.production.production_feishu_models import ProductionFeishuConfig

logger = logging.getLogger(__name__)

# Feishu type → PG type
TYPE_MAP = {1: "TEXT", 2: "DOUBLE PRECISION", 3: "INTEGER", 4: "TEXT", 5: "DATE", 20: "DOUBLE PRECISION"}


def _safe_col_name(name: str) -> str:
    """Convert Chinese field name to safe PG column name."""
    name = name.strip()
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return name
    return "col_" + name.encode("utf-8").hex()[:12]


async def discover_and_save_mapping(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    """Discover fields from Feishu and save the mapping to config."""
    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(config.app_id, app_secret, config.bitable_app_token)
    fields = await client.list_fields(config.table_id)

    mapping = {}
    cols = []
    seen = set()
    for f in fields:
        fid = f.get("field_id", "")
        fname = f.get("field_name", "")
        ftype = f.get("type", 1)
        col = "f_" + fid  # use field_id as column name (unique)
        if col in seen:
            col = col + "_2"
        seen.add(col)
        pg_type = TYPE_MAP.get(ftype, "TEXT")
        mapping[fid] = {"name": fname, "type": ftype, "db_column": col}
        cols.append({"name": col, "pg_type": pg_type, "feishu_name": fname})

    config.field_mapping = mapping
    # Use config ID as table name suffix to avoid encoding issues
    short_id = str(config.id).replace("-", "_")[:8]
    table_name = f"feishu_sync_{short_id}"
    config.sync_table_name = table_name
    await session.flush()

    # Create the table dynamically
    col_defs = [
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid()",
        "feishu_record_id VARCHAR(128)",
    ]
    for c in cols:
        col_defs.append(f'"{c["name"]}" {c["pg_type"]}')

    col_defs += [
        "created_at TIMESTAMPTZ DEFAULT now()",
        "updated_at TIMESTAMPTZ DEFAULT now()",
        "is_deleted BOOLEAN DEFAULT false",
    ]

    ddl = f"CREATE TABLE IF NOT EXISTS production.{table_name} ({', '.join(col_defs)})"
    await session.execute(text(ddl))
    await session.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_feishu_id ON production.{table_name} (feishu_record_id)"
    ))
    await session.commit()

    return {"table": table_name, "fields": len(cols), "mapping": mapping}


def _extract_value(val, ftype: int):
    """Extract typed value from Feishu field."""
    if val is None:
        return None
    if ftype == 5:  # date (timestamp millis)
        if isinstance(val, (int, float)) and val > 0:
            try:
                return datetime.fromtimestamp(val / 1000).date()
            except (OSError, ValueError):
                return None
        return None
    if ftype in (2, 3, 20):  # number / formula
        if isinstance(val, dict) and val.get("type") == 2:
            v = val.get("value") or []
            return float(v[0]) if v else None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, list) and val:
            try:
                return float(str(val[0].get("text", "")))
            except (ValueError, TypeError):
                pass
        return None
    # text
    if isinstance(val, str):
        return val.strip() or None
    if isinstance(val, list) and val:
        item = val[0]
        if isinstance(item, dict):
            return str(item.get("text", "")).strip() or None
        return str(item).strip() or None
    return str(val) if val else None


async def auto_sync_config(config: ProductionFeishuConfig, session: AsyncSession) -> dict:
    """Generic auto-sync: discover fields, create table, upsert data."""
    if not config.field_mapping:
        await discover_and_save_mapping(config, session)

    mapping = config.field_mapping or {}
    table_name = config.sync_table_name
    if not mapping or not table_name:
        return {"error": "field_mapping or sync_table_name missing"}

    app_secret = decrypt_secret(config.encrypted_app_secret)
    client = ProductionFeishuClient(config.app_id, app_secret, config.bitable_app_token)

    created = 0
    updated = 0
    page_token = None
    # Map by both field_id and field_name (Feishu records use field names as keys)
    lookup = {}
    for fid, info in mapping.items():
        lookup[fid] = (info["db_column"], info["type"])
        lookup[info["name"]] = (info["db_column"], info["type"])

    while True:
        result = await client.list_records(config.table_id, page_token=page_token)
        items = result.get("items") or []
        logger.warning(f'AUTO SYNC: page items={len(items)}, total={result.get("total")}')
        for item in items:
            flds = item.get("fields") or {}
            record_id = item.get("record_id", "")

            row = {}
            for f_key, fval in flds.items():
                entry = lookup.get(f_key)
                if not entry:
                    continue
                col, ftype = entry
                row[col] = _extract_value(fval, ftype)

            if not row:
                continue

            # Upsert
            existing = await session.execute(
                text(f"SELECT id FROM production.{table_name} WHERE feishu_record_id = :rid"),
                {"rid": record_id}
            )
            if existing.scalar_one_or_none():
                sets = ", ".join(f'"{k}" = :{k}' for k in row)
                await session.execute(
                    text(f"UPDATE production.{table_name} SET {sets}, updated_at = now() WHERE feishu_record_id = :rid"),
                    {**row, "rid": record_id}
                )
                updated += 1
            else:
                cols = ", ".join(f'"{k}"' for k in row)
                vals = ", ".join(f":{k}" for k in row)
                await session.execute(
                    text(f"INSERT INTO production.{table_name} (feishu_record_id, {cols}) VALUES (:rid, {vals})"),
                    {**row, "rid": record_id}
                )
                created += 1

        await session.flush()
        if not result["has_more"]:
            break
        page_token = result.get("page_token")

    return {"created": created, "updated": updated, "table": table_name}
