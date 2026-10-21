from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def isolate_maintenance_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    """Energy HTTP tests exercise real permissions and services without shared Redis.

    Maintenance admission has its own platform tests; business tests must not read
    the running development stack's maintenance state or depend on its sockets.
    """
    from app.core import maintenance_middleware

    @asynccontextmanager
    async def admitted(*args: Any, **kwargs: Any) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(maintenance_middleware, "business_activity", admitted)


@pytest.fixture
def sample_device_config_data() -> Any:
    return {
        "platform_code": "zhiheng",
        "platform_device_code": "WD-001",
        "device_name": "1号水表",
        "energy_type": "water",
        "api_endpoint": "/api/v1/water/hourly",
        "workshop": "发酵车间",
        "production_line": "发酵产线A",
        "monitor_level": "normal",
        "unit": "m3",
        "collection_interval": 60,
        "is_enabled": True,
    }
