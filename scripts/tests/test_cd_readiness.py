import asyncio
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("readiness", Path(__file__).parents[1] / "cd" / "readiness.py")
ready = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ready)


@pytest.mark.parametrize("failure", [None, "database", "redis", "storage"])
def test_dependency_readiness_and_cleanup(monkeypatch, failure):
    events = []
    class Connection:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def execute(self, _query):
            events.append("database")
            if failure == "database":
                raise RuntimeError("not ready")
    class Engine:
        def connect(self):
            return Connection()
        async def dispose(self):
            events.append("dispose")
    class Redis:
        @classmethod
        def from_url(cls, *args, **kwargs):
            return cls()
        async def ping(self):
            events.append("redis")
            if failure == "redis":
                raise RuntimeError("not ready")
        async def aclose(self):
            events.append("redis-close")
    for name in ("app", "app.core", "redis"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", SimpleNamespace(Redis=Redis))
    monkeypatch.setitem(sys.modules, "sqlalchemy", SimpleNamespace(text=lambda value: value))
    monkeypatch.setitem(sys.modules, "app.core.database", SimpleNamespace(engine=Engine()))
    settings = SimpleNamespace(REDIS_URL="redis://test", MINIO_ENABLED=True,
                               MINIO_SECURE=False, MINIO_ENDPOINT="storage.test:9000")
    monkeypatch.setitem(sys.modules, "app.core.config", SimpleNamespace(get_settings=lambda: settings))
    def storage(*args, **kwargs):
        events.append("storage")
        return nullcontext(SimpleNamespace(status=503 if failure == "storage" else 200))
    monkeypatch.setattr(ready, "urlopen", storage)
    if failure:
        with pytest.raises(RuntimeError):
            asyncio.run(ready.check())
    else:
        asyncio.run(ready.check())
        assert events[:3] == ["database", "redis", "storage"]
    assert events[-2:] == ["redis-close", "dispose"]
