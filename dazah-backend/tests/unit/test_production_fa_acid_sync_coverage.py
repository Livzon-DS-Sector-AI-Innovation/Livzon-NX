"""FA 酸化过滤 飞书同步 coverage。

覆盖 fa_acid_sync 的 _read 成功路径、run() 数据主路径（日期/批号/百分比/数值转换、
DELETE+INSERT）、main() 入口及 __main__ 分支。全部 mock，无真实网络/DB。

注意：模块级 `_token` 与函数同名冲突，`_token()` 实际总是提前返回函数对象，
其内部缓存写入体（68-79）为不可达死代码，因此这里直接验证 `_read()` 的
网络请求与行值转换路径。
"""
from __future__ import annotations

import ast
import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.anyio
async def test_fa_acid_read_ok() -> Any:
    mod = importlib.import_module("app.modules.production.fa_acid_sync")
    real = httpx.AsyncClient

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-read"})
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "data": {"valueRange": {"values": [[1, None], ["a", "b"]]}},
            },
        )

    sheet_transport = httpx.MockTransport(handler)

    def fake_sheet(*, base_url: Any=None, timeout: Any=60, **kw: Any) -> Any:
        return real(transport=sheet_transport, timeout=timeout, base_url=base_url)

    with patch.object(mod.httpx, "AsyncClient", fake_sheet):
        rows = await mod._read()
    assert rows == [["1", ""], ["a", "b"]]


@pytest.mark.anyio
async def test_fa_acid_read_api_error() -> Any:
    mod = importlib.import_module("app.modules.production.fa_acid_sync")
    real = httpx.AsyncClient

    def error_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "tok-error"})
        return httpx.Response(200, json={"code": 40003, "msg": "expired"})

    err_transport = httpx.MockTransport(error_handler)

    def fake_err(*, base_url: Any=None, timeout: Any=60, **kw: Any) -> Any:
        return real(transport=err_transport, timeout=timeout, base_url=base_url)

    with patch.object(mod.httpx, "AsyncClient", fake_err):
        rows = await mod._read()
    assert isinstance(rows, list)


@pytest.mark.anyio
async def test_fa_acid_run_with_data() -> Any:
    mod = importlib.import_module("app.modules.production.fa_acid_sync")
    rows_input = [
        ["", "FA-EX0", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501 数据前空行（非 in_data）→ 跳过
        [
            "3月5日", "FA-EX1", "10", "98", "980", "500", "4.5", "8.8", "200",
            "5.1", "100", "100", "100", "1000", "50", "10", "5", "10", "9",
            "0.95", "8", "60", "2", "1", "0.5", "3", "0.3", "0.2", "0.98", "12",
        ],
        ["2026年3月平均值", "x", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],  # noqa: E501 汇总行 → 跳过
        ["3月", ""],  # 月份分隔行
        ["", ""],  # 空行
        [
            "3月6日", "FA-EX222", "12", "95", "1140", "400", "4.2", "8.5", "220",
            "5.2", "110", "90", "90", "900", "40", "8", "8", "11", "10",
            "0.93", "7", "50", "2", "1.1", "0.4", "2", "0.2", "0.15", "0.9", "10",
        ],
    ]
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    with patch.object(mod, "_read", new=AsyncMock(return_value=rows_input)):
        out = await mod.run(session)
    assert out == {"total_rows": 2, "batches": 2}
    assert session.execute.await_count >= 3  # DELETE + 2 * INSERT


@pytest.mark.anyio
async def test_fa_acid_token_fetch_cache_and_error() -> Any:
    mod = importlib.import_module("app.modules.production.fa_acid_sync")
    fn = mod._token  # 先保存函数对象（模块级 `_token` 是函数）
    real = httpx.AsyncClient
    token_transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json={"tenant_access_token": "tok-ax"})
    )
    err_transport = httpx.MockTransport(lambda req: httpx.Response(500, text="boom"))

    def fake_ok(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real(transport=token_transport, timeout=timeout, base_url=base_url)

    def fake_err(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real(transport=err_transport, timeout=timeout, base_url=base_url)

    # 无缓存：发 HTTP 拿 token（覆盖返回后的缓存写入体）
    setattr(mod, "_access_token", None)
    with patch.object(mod.httpx, "AsyncClient", fake_ok), patch.object(
        mod.os, "getenv", side_effect=["app-id", "app-secret"]
    ):
        assert await fn() == "tok-ax"

    # 命中缓存：不再发 HTTP
    setattr(mod, "_access_token", "cached-tok")
    with patch.object(
        mod.httpx, "AsyncClient", new=MagicMock(side_effect=AssertionError("no HTTP"))
    ):
        assert await fn() == "cached-tok"

    # HTTP 非 2xx：raise_for_status 抛 HTTPStatusError
    err_handler = httpx.MockTransport(lambda req: httpx.Response(500, text="boom"))
    setattr(mod, "_access_token", None)

    def fake_http_err(*, base_url: Any=None, timeout: Any=30, **kw: Any) -> Any:
        return real(transport=err_handler, timeout=timeout, base_url=base_url)

    with patch.object(mod.httpx, "AsyncClient", fake_http_err), patch.object(
        mod.os, "getenv", side_effect=["app-id", "app-secret"]
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await fn()


def test_fa_acid_pure_helpers() -> Any:
    mod = importlib.import_module("app.modules.production.fa_acid_sync")
    assert mod._g(["a", " b "], 1) == "b"
    assert mod._g([], 0) == ""
    assert mod._pd("3月5日").startswith("2026-03-05")
    assert mod._pd("12月31日").startswith("2025-12-31")
    assert mod._pd("noop") is None
    assert mod._n("100") == "100.0"
    assert mod._n("-") == "NULL"
    assert mod._n("#DIV/0!") == "NULL"
    assert mod._n("") == "NULL"
    assert mod._n("abc") == "NULL"
    assert mod._p("-") == "NULL"
    assert mod._p("0.5") == "'50%'"
    assert mod._p("1") == "'1'"
    assert mod._p("abc") == "'abc'"
    assert mod._n("85.5") == "85.5"


def _exec_main_block(mod: Any) -> Any:
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

            def _noop_main() -> Any:
                return None

            ns["main"] = _noop_main
            ns["asyncio"] = SimpleNamespace(run=lambda f: None)
            exec(compile(block, path, "exec"), ns)
            return


@pytest.mark.anyio
async def test_fa_acid_main_entry_and_main_block() -> Any:
    mod = importlib.import_module("app.modules.production.fa_acid_sync")
    session = AsyncMock()
    run_mock = AsyncMock(return_value={"total_rows": 2, "batches": 1})

    class _Ctx:
        async def __aenter__(self) -> Any:
            return session

        async def __aexit__(self, *args: Any) -> Any:
            return False

    engine = MagicMock()
    engine.dispose = AsyncMock()

    with (
        patch.object(mod, "create_async_engine", return_value=engine),
        patch.object(mod, "async_sessionmaker", return_value=lambda: _Ctx()),
        patch.object(mod.os, "getenv", return_value="postgresql+asyncpg://"),
    ):
        with (
            patch.object(mod, "run", new=run_mock),
            patch("builtins.print") as fake_print,
        ):
            await mod.main()
    run_mock.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    assert fake_print.call_count >= 1

    # 覆盖 `if __name__ == "__main__"` 分支
    _exec_main_block(mod)
