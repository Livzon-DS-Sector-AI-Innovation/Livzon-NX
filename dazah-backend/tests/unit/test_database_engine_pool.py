"""core.database 引擎连接池按环境选择的回归测试。

测试环境（APP_ENV=test）必须使用 NullPool：pytest 每个测试运行在独立事件
循环上，QueuePool 的长连接绑定到已关闭的循环后无法在 Linux 上及时回收，
累积会打满 PostgreSQL max_connections（CI TooManyConnectionsError 根因）。
"""

from __future__ import annotations

from sqlalchemy import pool

from app.core.database import _build_engine_kwargs


class TestBuildEngineKwargs:
    def test_test_env_uses_null_pool(self) -> None:
        kwargs = _build_engine_kwargs("test")
        assert kwargs["poolclass"] is pool.NullPool
        # NullPool 不接受池容量参数
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs
        assert "pool_pre_ping" not in kwargs

    def test_development_env_keeps_queue_pool(self) -> None:
        kwargs = _build_engine_kwargs("development")
        assert "poolclass" not in kwargs
        assert kwargs["pool_size"] == 10
        assert kwargs["max_overflow"] == 20
        assert kwargs["pool_pre_ping"] is True

    def test_production_env_keeps_queue_pool(self) -> None:
        kwargs = _build_engine_kwargs("production")
        assert "poolclass" not in kwargs
        assert kwargs["pool_size"] == 10

    def test_search_path_always_set(self) -> None:
        for env in ("test", "development", "production"):
            kwargs = _build_engine_kwargs(env)
            connect_args = kwargs["connect_args"]
            assert isinstance(connect_args, dict)
            server_settings = connect_args["server_settings"]
            assert "search_path" in server_settings
