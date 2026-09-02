"""质量飞书配置补充：变更控制、产品质量、物品管理、仪器管理。"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.database import async_session_factory

CHANGE_TOKEN = "WwXnbkC8waxuzBsEbuWc6DAUnZg"
PQ_TOKEN = "SALAbCZyWarBUTs2AnncdeeynFe"
INSTRUMENT_TOKEN = "O0S2bHK6Ca5UiCsABPLcZtYhn6d"
ITEM_TOKEN = "AApmbavGQaSpjCsCR8uc66fInsd"

# (entity_code, app_token, base_table_id)
UPDATES = [
    ("change_ledger", CHANGE_TOKEN, "tblSDbnr2D7wk2b0"),
    ("change_action_plan", CHANGE_TOKEN, "tblvNkE0DyhOlcd9"),
    ("product_quality_mfn", PQ_TOKEN, "tblv4GEvTTh6yS2T"),
    ("product_quality_dljs", PQ_TOKEN, "tblLQg9dSUj2yqu2"),
    ("product_quality_lftt", PQ_TOKEN, "tblYna85VHNBBkBB"),
    ("product_quality_mftt", PQ_TOKEN, "tblLuitbPHKrgZF1"),
    ("product_quality_yslkms", PQ_TOKEN, "tbl0g9hcd4TYjDiv"),
    ("product_quality_bbas", PQ_TOKEN, "tbl7QUkZwh8JC0ZP"),
    ("product_quality_sas", PQ_TOKEN, "tblYIaVwi1OKkPe8"),
    ("product_quality_ledger", PQ_TOKEN, None),
    ("product_quality_standard_item", PQ_TOKEN, None),
    ("inspection_lab_item", ITEM_TOKEN, None),
    ("inspection_lab_instrument", INSTRUMENT_TOKEN, None),
]


async def main() -> None:
    async with async_session_factory() as db:
        for entity_code, token, table_id in UPDATES:
            r = await db.execute(
                text(
                    "UPDATE quality.quality_feishu_entity_settings "
                    "SET app_token=:tok, is_enabled=true"
                    + (", base_table_id=:tid" if table_id else "")
                    + " WHERE entity_code=:c RETURNING entity_name"
                ),
                (
                    {"tok": token, "c": entity_code}
                    if not table_id
                    else {"tok": token, "c": entity_code, "tid": table_id}
                ),
            )
            name = r.scalar()
            status = "OK " if name else "MISS"
            print(
                f"{status} {entity_code}({name}) "
                f"→ {token[:10]}... table={table_id or '-'}"
            )
        await db.commit()

        r = await db.execute(
            text(
                "SELECT entity_group, count(*), count(app_token), bool_or(is_enabled) "
                "FROM quality.quality_feishu_entity_settings "
                "WHERE entity_group IN ('变更控制','产品质量','检验管理') "
                "GROUP BY entity_group"
            )
        )
        for row in r:
            print(tuple(row))


asyncio.run(main())
