"""成品检验镜像全量回拉脚本（换 Base 后初始化/对账用）。

对全部 qc_finished_* 实体逐个全量回拉本地镜像
（quality.quality_items_page_snapshots / quality_items_page_rows）：
- 换 Base（c9d400000032）或首次启用镜像后执行一次，建立初始快照；
- 日常对账可重跑（全量含删除对账，幂等）。

用法（容器内）：
    .venv/bin/python scripts/sync_finished_inspection_mirror.py
    .venv/bin/python scripts/sync_finished_inspection_mirror.py --entity qc_finished_pf
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_app_root = Path(__file__).resolve().parents[1]
if not (_app_root / "app" / "core").is_dir():
    _app_root = Path.cwd()
sys.path.insert(0, str(_app_root))

from app.core.database import async_session_factory  # noqa: E402
from app.modules.quality.service.inspection_finished_mirror import (  # noqa: E402
    FINISHED_MIRROR_ENTITIES,
    sync_finished_page,
)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="成品检验镜像全量回拉（全部实体或指定实体）"
    )
    parser.add_argument(
        "--entity",
        action="append",
        help="仅同步指定实体（可多次传入）；缺省同步全部成品实体",
    )
    args = parser.parse_args()

    entities = list(args.entity) if args.entity else list(FINISHED_MIRROR_ENTITIES)
    unknown = [e for e in entities if e not in FINISHED_MIRROR_ENTITIES]
    if unknown:
        print(f"未知成品实体: {unknown}")
        sys.exit(2)

    ok = failed = 0
    for index, entity_code in enumerate(entities, start=1):
        try:
            async with async_session_factory() as db:
                result = await sync_finished_page(db, entity_code, incremental=False)
            ok += 1
            print(
                f"[{index}/{len(entities)}] {entity_code} "
                f"synced={result['synced']} total={result['total']}"
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[{index}/{len(entities)}] {entity_code} FAILED: {exc}")
    print(f"done: ok={ok} failed={failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
