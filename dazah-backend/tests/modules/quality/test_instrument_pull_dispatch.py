"""仪器管理镜像接入全局回拉分派：单实体走镜像全量、全部回拉顺带同步。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service import (
    inspection_instrument_mirror as instrument_mirror,
)
from app.modules.quality.service import quality_feishu_sync as sync_service

pytestmark = pytest.mark.anyio


class _EntityConfig:
    app_token = "tok"
    table_id = "tbl"


class _Runtime:
    def is_enabled(self) -> bool:
        return True

    def get_entity_config(self, code: str, *, direction: str) -> Any:
        return _EntityConfig()


@pytest.mark.anyio
async def test_pull_single_instrument_entity_runs_mirror_full_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve(_db: Any) -> _Runtime:
        return _Runtime()

    monkeypatch.setattr(sync_service.feishu_sync, "_resolve_runtime", fake_resolve)

    calls: list[tuple[str, bool]] = []

    async def fake_sync(
        db: Any, entity_code: str, *, incremental: bool = True
    ) -> dict[str, int]:
        calls.append((entity_code, incremental))
        return {"synced": 3, "removed": 0, "total": 3}

    monkeypatch.setattr(instrument_mirror, "sync_instrument_page", fake_sync)

    result = await sync_service.pull_quality_records_from_feishu(
        SimpleNamespace(), entity_code="qc_instr_equipment"
    )

    assert result == {
        "entity_code": "qc_instr_equipment",
        "entity_label": "设备数据管理",
        "synced": 3,
        "failed": 0,
        "conflicts": 0,
    }
    # 设置页保存后的刷新路径要求全量对账（增量=False）
    assert calls == [("qc_instr_equipment", False)]


@pytest.mark.anyio
async def test_pull_all_entities_includes_instrument_mirrors(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EmptyRuntime:
        def is_enabled(self) -> bool:
            return True

        def get_entity_config(self, code: str, *, direction: str) -> Any:
            return None  # 业务实体未配置：核心回拉为空

    async def fake_resolve(_db: Any) -> _EmptyRuntime:
        return _EmptyRuntime()

    monkeypatch.setattr(sync_service.feishu_sync, "_resolve_runtime", fake_resolve)

    mirror_calls: list[int] = []

    async def fake_mirrors(_db: Any, _runtime: Any) -> int:
        mirror_calls.append(1)
        return 4

    monkeypatch.setattr(sync_service, "_pull_instrument_mirrors", fake_mirrors)

    async def fake_search(
        _db: Any, _entity_code: str, _table_id: str, **_kwargs: Any
    ) -> list[Any]:
        return []

    monkeypatch.setattr(sync_service.feishu_sync, "search_records", fake_search)

    result = await sync_service.pull_quality_records_from_feishu(db_session)

    assert mirror_calls == [1]
    assert result["entity_code"] is None
    assert result["synced"] == 4
