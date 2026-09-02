"""修复 2026-08-31 附件错绑事故：
1. 恢复被误删的 QA"状态标识管理程序"条目，并挂回其正确的 md 附件；
2. SMP-EE-403"计量室设备状态标识管理程序"编号回退 /12→/01，摘除错绑附件。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import async_session_factory
from app.modules.quality.models.document_catalog import DocumentEntry

QA_ENTRY_ID = "560c2fd1-e253-46f4-92d5-cb84e182b538"
EE_ENTRY_ID = "73638b90-7f18-4011-8262-c1b20450b30e"

QA_ATTACHMENT = {
    "converted": True,
    "file_name": "SMP-QA-005-12状态标识管理程序.md",
    "file_size": 13455,
    "storage_key": (
        "document-catalog/attachments/"
        "d6909342f8ca4ac487580f9c79999ae3_SMP-QA-005-12状态标识管理程序.md"
    ),
    "uploaded_at": "2026-08-05T03:51:59.126748+00:00",
    "uploaded_by": "system-import",
    "content_type": "text/markdown; charset=utf-8",
    "converted_md_key": (
        "document-catalog/attachments/"
        "d6909342f8ca4ac487580f9c79999ae3_SMP-QA-005-12状态标识管理程序.md"
    ),
    "asset_keys": [],
    "pipeline": "v2",
}


async def main() -> None:
    async with async_session_factory() as db:
        # 1. 恢复 QA 状态标识条目（含正确附件）
        qa = await db.get(DocumentEntry, QA_ENTRY_ID)
        assert qa is not None, "QA 条目不存在"
        qa.is_deleted = False
        qa.attachments = [QA_ATTACHMENT]
        flag_modified(qa, "attachments")
        print(f"已恢复 QA 条目: {qa.code} {qa.name}")

        # 2. EE-403 编号回退 + 摘除错绑附件
        ee = await db.get(DocumentEntry, EE_ENTRY_ID)
        assert ee is not None, "EE 条目不存在"
        old_code = ee.code
        ee.code = "SMP-EE-403/01"
        attachments = [
            a for a in (ee.attachments or [])
            if not str(a.get("file_name", "")).startswith("SMP-QA-005")
        ]
        ee.attachments = attachments
        flag_modified(ee, "attachments")
        print(f"EE 条目编号 {old_code} → {ee.code}，附件 {len(attachments)} 个")

        await db.commit()

        # 3. 核对
        rows = await db.execute(
            text(
                "SELECT code, left(name,26), is_deleted, "
                "json_array_length(COALESCE(attachments,'[]')) "
                "FROM quality.document_entries "
                "WHERE id IN (:q, :e)"
            ),
            {"q": QA_ENTRY_ID, "e": EE_ENTRY_ID},
        )
        for row in rows:
            print(tuple(row))


asyncio.run(main())
