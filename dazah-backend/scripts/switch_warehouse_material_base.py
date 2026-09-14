"""把 warehouse_page_feishu_configs 的页面映射对齐到代码注册表并全量同步。

背景：页面数据源配置 DB 优先、代码注册表回退。原辅料及包材 Base 迁移
（2026-09）只改 feishu_material_pages.py 不够——已播种的 DB 配置行仍指向
旧 Base，需执行本脚本对齐，并对有变化的页面立即全量同步：换表后增量轮的
旧水线会漏拉新表历史数据，只有全量拉取才能软删旧 Base 的镜像行。

默认仅处理原辅料（FEISHU_WAREHOUSE_APP_TOKEN）与液体入库
（FEISHU_LIQUID_WAREHOUSE_APP_TOKEN）两个 Base 的页面，不动五金/成品的
DB 配置，避免覆盖设置页里的人工自定义。默认 dry run 只打印差异；
确认后加 --apply 落库并逐页全量同步。

用法（dev 容器内，脚本可 docker cp 到 /tmp 执行）：
    .venv/bin/python /tmp/switch_warehouse_material_base.py             # dry run
    .venv/bin/python /tmp/switch_warehouse_material_base.py --apply     # 落库+全量同步
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_app_root = Path(__file__).resolve().parents[1]
# 容器内从 /tmp 执行时脚本路径不含 app 包，回退当前工作目录（-w /app）；
# 条件判断使 import 无法位于文件顶部，以下 app 导入需 noqa E402
if not (_app_root / "app" / "core").is_dir():
    _app_root = Path.cwd()
sys.path.insert(0, str(_app_root))

from app.core.database import async_session_factory  # noqa: E402
from app.modules.warehouse.feishu_material_pages import (  # noqa: E402
    FEISHU_LIQUID_WAREHOUSE_APP_TOKEN,
    FEISHU_WAREHOUSE_APP_TOKEN,
    FEISHU_WAREHOUSE_MATERIAL_PAGES,
)
from app.modules.warehouse.service import WarehouseService  # noqa: E402

IN_SCOPE_APP_TOKENS = {FEISHU_WAREHOUSE_APP_TOKEN, FEISHU_LIQUID_WAREHOUSE_APP_TOKEN}


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="对齐仓储页面飞书配置到代码注册表并对变化页全量同步"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写入 DB 并全量同步（缺省 dry run 只打印差异）",
    )
    parser.add_argument(
        "--include-out-of-scope",
        action="store_true",
        help="处理注册表全部页面（缺省仅原辅料+液体入库）",
    )
    parser.add_argument(
        "--sync-all-pages",
        action="store_true",
        help="跳过配置对齐，对注册表全部页面逐页全量同步（初始回填/对账用）",
    )
    parser.add_argument(
        "--pages",
        help="逗号分隔的 page_key 列表，仅处理这些页（配合 --sync-all-pages 断点续跑）",
    )
    args = parser.parse_args()

    only = {k.strip() for k in args.pages.split(",")} if args.pages else None

    async with async_session_factory() as session:
        service = WarehouseService(session)
        if args.sync_all_pages:
            changed = [
                key
                for key in FEISHU_WAREHOUSE_MATERIAL_PAGES
                if only is None or key in only
            ]
            print(
                f"[全量回填] 共 {len(changed)} 页，逐页全量同步（可中断重跑）",
                flush=True,
            )
            failed = 0
            for page_key in changed:
                try:
                    async with async_session_factory() as sync_session:
                        sync_service = WarehouseService(sync_session)
                        result = await sync_service.sync_material_page_to_local(
                            page_key, incremental=False
                        )
                        await sync_session.commit()
                    print(f"- {page_key}: 同步完成 rows={result.total}", flush=True)
                except Exception as exc:  # noqa: BLE001 - 逐页容错并汇报
                    failed += 1
                    print(f"- {page_key}: 全量同步失败: {exc}", flush=True)
            print(f"全量回填完成（失败 {failed} 页）。")
            return

        existing = {
            item["page_key"]: item
            for item in await service.repo.list_page_feishu_configs()
        }

        changed: list[str] = []
        for page_key, page in FEISHU_WAREHOUSE_MATERIAL_PAGES.items():
            in_scope = page.app_token in IN_SCOPE_APP_TOKENS
            if not (args.include_out_of_scope or in_scope):
                continue
            current = existing.get(page_key)
            desired = {
                "app_token": page.app_token,
                "table_id": page.table_id,
                "table_name": page.title,
            }
            if current and all(current.get(k) == v for k, v in desired.items()):
                print(f"- {page_key}: 已一致（{desired['table_id']}）")
            else:
                old_desc = (
                    f"{current.get('app_token')}/{current.get('table_id')}"
                    if current
                    else "无配置"
                )
                print(
                    f"- {page_key}: {old_desc} -> "
                    f"{desired['app_token']}/{desired['table_id']}"
                )
                if args.apply:
                    await service.update_page_feishu_config(
                        page_key,
                        {
                            "page_key": page_key,
                            **desired,
                            "view_id": current.get("view_id") if current else None,
                        },
                    )
                changed.append(page_key)

            # 快照仍指向旧表（上次同步被打断等）：换表后增量水线不可靠，
            # 一并纳入全量同步名单
            if args.apply:
                snapshot = await service.repo.get_material_page_snapshot(page_key)
                if snapshot is not None and snapshot.table_id != page.table_id:
                    if page_key not in changed:
                        changed.append(page_key)
                        print(
                            f"- {page_key}: 快照表 {snapshot.table_id} "
                            "与配置不一致，补全量同步"
                        )

        if not args.apply:
            print("\n[dry run] 未写入任何变更；确认无误后加 --apply 执行。")
            return

        await session.commit()
        print(f"\n已更新 {len(changed)} 页配置，开始逐页全量同步...")
        failed = 0
        for page_key in changed:
            try:
                async with async_session_factory() as sync_session:
                    sync_service = WarehouseService(sync_session)
                    result = await sync_service.sync_material_page_to_local(
                        page_key, incremental=False
                    )
                    await sync_session.commit()
                print(f"- {page_key}: 同步完成 rows={result.total}")
            except Exception as exc:  # noqa: BLE001 - 逐页容错并汇报
                failed += 1
                print(f"- {page_key}: 全量同步失败: {exc}")
        print(f"全量同步完成（失败 {failed} 页）。")


if __name__ == "__main__":
    asyncio.run(main())
