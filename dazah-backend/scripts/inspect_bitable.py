"""Inspect Feishu Bitable table schema and sample data."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.platform.integrations.feishu.client import FeishuClient


APP_TOKEN = "RfEmb1WyzasCg4sn6tsc4LbWnjf"
TABLE_ID = "tbllxa1JInvTuEoD"


async def inspect_table():
    client = FeishuClient()

    # 1. Fields
    print("=" * 60)
    print(f"Fields (app={APP_TOKEN}, table={TABLE_ID})")
    print("=" * 60)
    fields_data = await client.request(
        "GET",
        f"/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/fields",
        params={"page_size": 100},
    )
    fields = fields_data.get("items", [])
    for f in fields:
        print(f"  - {f['field_name']:12s} | type={str(f['type']):12s} | id={f['field_id']}")

    # 2. Sample records
    print()
    print("=" * 60)
    print("First 10 records")
    print("=" * 60)
    records_data = await client.request(
        "POST",
        f"/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/search",
        json={"page_size": 10},
    )
    items = records_data.get("items", [])
    for i, rec in enumerate(items, 1):
        print(f"\n  [{i}] record_id={rec.get('record_id')}")
        for k, v in rec.get("fields", {}).items():
            preview = str(v)[:80] + ("..." if len(str(v)) > 80 else "")
            print(f"      {k}: {preview}")

    # 3. Table meta
    print()
    print("=" * 60)
    print("Table meta")
    print("=" * 60)
    table_data = await client.request(
        "GET",
        f"/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}",
    )
    print(f"  name: {table_data.get('name')}")
    print(f"  is_block: {table_data.get('is_block')}")
    print(f"  field_count: {len(fields)}")
    print(f"  total_records: {records_data.get('total', '?')}")


if __name__ == "__main__":
    if not os.getenv("FEISHU_APP_ID") or not os.getenv("FEISHU_APP_SECRET"):
        print("[!] Please set FEISHU_APP_ID and FEISHU_APP_SECRET")
        sys.exit(1)

    asyncio.run(inspect_table())
