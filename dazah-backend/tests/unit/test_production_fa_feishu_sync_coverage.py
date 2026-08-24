"""FA 发酵放罐 sync coverage。

覆盖 fa_feishu_sync.sync_fermentation 的月份/汇总行跳过分支、主批/子批 created
计数路径（rowcount=0），以及 main() 独立入口与 __main__ 分支。全部 mock。
"""
from __future__ import annotations

import ast
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.anyio
async def test_fa_fermentation_skip_rows_and_created():
    mod = importlib.import_module("app.modules.production.fa_feishu_sync")
    rows = [
        ["3月", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # 月份分隔行
        ["2026年度放罐统计", "", "", "x", "", "", "", "", "", "", "", "", ""],  # 汇总行
        ["2026-03-05", "FA-EX1", "", "10", "100", "500", "600", "80", "1.2", "", "", "", ""],  # 主批  # noqa: E501
        ["2026.03.06", "FA-EX1", "FA-EX1C", "5", "90", "300", "", "", "", "", "", "", ""],  # 子批  # noqa: E501
        ["2026.03.07", "FA-EX2", "", "8", "", "", "400", "", "", "", "", "", ""],  # 另一个主批  # noqa: E501
        ["", "", "", "", "", "", "", "", "", "", "", "", ""],  # 空行
    ]
    session = AsyncMock()
    result = MagicMock(rowcount=0)  # 走 created 分支
    session.execute.return_value = result
    with patch.object(mod, "_read_sheet", new=AsyncMock(return_value=rows)):
        out = await mod.sync_fermentation(session, "span", "app", "sec")
    assert out["batches"] >= 2
    assert out["sub_batches"] >= 1
    assert out["created_batches"] >= 2
    assert out["created_subs"] >= 1
    session.commit.assert_awaited_once()


def _exec_main_block(mod):
    """Exec 模块底部 `if __name__ == '__main__':` 块，覆盖 __main__ 行."""
    path = mod.__file__
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source, filename=path)
    for node in tree.body:
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(c, ast.Constant) and c.value == "__main__"
                for c in node.test.comparators
            )
        ):
            block = ast.Module(body=[node], type_ignores=[])
            ast.fix_missing_locations(block)
            ns = dict(mod.__dict__)
            ns["__name__"] = "__main__"

            def _noop_main():
                return None

            ns["main"] = _noop_main
            ns["asyncio"] = SimpleNamespace(run=lambda f: None)
            exec(compile(block, path, "exec"), ns)
            return


@pytest.mark.anyio
async def test_fa_feishu_sync_main_entry_and_main_block():
    mod = importlib.import_module("app.modules.production.fa_feishu_sync")
    session = AsyncMock()

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    engine = MagicMock()
    engine.dispose = AsyncMock()
    cfg = {"spreadsheet_token": "spt", "app_id": "a", "app_secret": "s"}
    sync_mock = AsyncMock(
        return_value={
            "batches": 1,
            "sub_batches": 1,
            "created_batches": 1,
            "updated_batches": 0,
            "created_subs": 1,
            "updated_subs": 0,
        }
    )

    with (
        patch.object(mod, "create_async_engine", return_value=engine),
        patch.object(mod, "sessionmaker", return_value=lambda: _Ctx()),
        patch.object(mod.os, "getenv", return_value="postgresql+asyncpg://"),
    ):
        with (
            patch(
                "app.modules.production.fa_feishu_scheduler._get_fa_spreadsheet_config",
                new=AsyncMock(return_value=cfg),
            ),
            patch.object(mod, "sync_fermentation", new=sync_mock),
            patch("builtins.print") as fake_print,
        ):
            await mod.main()
    sync_mock.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    assert fake_print is not None

    # 覆盖 `if __name__ == "__main__"` 分支
    _exec_main_block(mod)
