"""从本地快照 JSON 初始化仓储 material-page 镜像（首次部署秒开用）。

写入快照 + 行数据后，页面读取默认走本地快照；日常新鲜度由
warehouse.feishu_incremental_sync（10 分钟增量）与
warehouse.feishu_full_sync（每日全量对账）保证。

水线语义：播种会把快照 last_synced_at 盖为当前时间，飞书侧在
"快照导出 → 播种"窗口内发生的变更会被增量水线跳过（要等当日凌晨
全量对账才补齐）。需要播种后立即对账时追加 --full-sync 参数。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import async_session_factory
from app.modules.warehouse.models import MaterialPageRow
from app.modules.warehouse.service import (
    WarehouseService,
    build_material_page_row_search_text,
)

SNAPSHOT_PATH = (
    Path(__file__).resolve().parent / "data" / "warehouse_material_pages_snapshot.json"
)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="从仓储快照 JSON 播种本地 material-page 镜像"
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="播种后立即对全部页面执行一次全量同步，补齐水线窗口内的变更",
    )
    args = parser.parse_args()

    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(f"未找到仓储快照文件: {SNAPSHOT_PATH}")

    payload = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    now = datetime.now(UTC)

    async with async_session_factory() as session:
        service = WarehouseService(session)

        for page_key, page in payload.items():
            columns = list(page.get("columns", []))
            rows = list(page.get("rows", []))
            snapshot = await service.repo.upsert_material_page_snapshot(
                page_key=page_key,
                page_title=str(page.get("page_title", page_key)),
                table_name=str(page.get("table_name", page_key)),
                table_id=str(page.get("table_id", "")),
                columns=columns,
                total_rows=len(rows),
                source=str(page.get("source", "local_snapshot")),
                last_synced_at=now,
                last_error=None,
            )

            row_models = [
                MaterialPageRow(
                    page_snapshot_id=snapshot.id,
                    source_record_id=str(
                        row.get("__record_id") or f"{page_key}-{index}"
                    ),
                    row_order=index,
                    cells={
                        key: value for key, value in row.items() if key != "__record_id"
                    },
                    search_text=build_material_page_row_search_text(row),
                    last_synced_at=now,
                )
                for index, row in enumerate(rows, start=1)
            ]
            await service.repo.replace_material_page_rows(snapshot.id, row_models)

        await session.commit()

    print(f"已写入仓储快照到本地数据库: {SNAPSHOT_PATH}")
    for page_key, page in payload.items():
        print(
            f"- {page_key}: imported_rows={len(page.get('rows', []))}, "
            f"remote_total={page.get('remote_total', len(page.get('rows', [])))}, "
            f"has_more={page.get('has_more', False)}"
        )

    if args.full_sync:
        print("--full-sync：开始逐页全量同步（补齐水线窗口内的变更）...")
        failed = 0
        for page_key in payload:
            try:
                async with async_session_factory() as sync_session:
                    sync_service = WarehouseService(sync_session)
                    await sync_service.sync_material_page_to_local(
                        page_key, incremental=False
                    )
                    await sync_session.commit()
            except Exception as exc:  # noqa: BLE001 - 逐页容错并汇报
                failed += 1
                print(f"- {page_key}: 全量同步失败: {exc}")
        print(f"全量同步完成（失败 {failed} 页）。")


if __name__ == "__main__":
    asyncio.run(main())
