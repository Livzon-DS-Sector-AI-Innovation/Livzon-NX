from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException
from app.modules.quality.service import quality_feishu_pages as service


class _Result:
    def __init__(self, one: object = None) -> None:
        self.one = one

    def scalar_one_or_none(self) -> object:
        return self.one


class _Db:
    def __init__(self, results: list[_Result] | None = None) -> None:
        self.results = list(results or [])
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, _statement: object) -> _Result:
        return self.results.pop(0) if self.results else _Result()

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _record(record_id: str, fields: dict[str, object]) -> dict[str, object]:
    return {"record_id": record_id, "fields": fields}


@pytest.mark.asyncio
async def test_sync_capas_from_feishu_updates_creates_and_counts_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = object()
    records = [
        _record("missing-code", {}),
        _record(
            "existing",
            {
                "CAPA编号": "CAPA-EXISTING",
                "CAPA状态": "closed",
                "CAPA简述": "更新标题",
                "事件部门": "质量部",
                "涉及产品": "产品A",
                "CAPA效果评估": "有效",
                "QA质量员": "张三",
                "关闭日期": "2026-08-20T08:00:00Z",
                "QA质量员确认日期": "2026-08-21",
                "启动日期": "2026-08-01",
            },
        ),
        _record(
            "new",
            {
                "CAPA编号": "CAPA-NEW",
                "CAPA简述": "新 CAPA",
                "事件部门": "生产部",
                "涉及产品": "产品B",
            },
        ),
        _record("broken", {"CAPA编号": "CAPA-BROKEN"}),
    ]
    existing = SimpleNamespace(status="draft", is_deleted=False)
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(runtime, object())),
    )
    monkeypatch.setattr(
        service, "_search_entity_records", AsyncMock(return_value=records)
    )
    monkeypatch.setattr(
        service.repository,
        "get_capa_by_code",
        AsyncMock(side_effect=[existing, None, RuntimeError("db failure")]),
    )
    db = _Db()

    result = await service.sync_capas_from_feishu(db)

    assert result == {"synced": 2, "failed": 2}
    assert existing.title == "更新标题"
    assert existing.status == "closed"
    assert len(db.added) == 1
    assert db.commits == 2
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_sync_capa_plan_tracks_matches_existing_and_creates_new_tracks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capa = SimpleNamespace(id=uuid4())
    existing = SimpleNamespace(reminder_status="pending", is_deleted=False)
    records = [
        _record("missing", {"CAPA编号": "", "计划内容": ""}),
        _record("unknown", {"CAPA编号": "CAPA-UNKNOWN", "计划内容": "计划"}),
        _record(
            "existing",
            {
                "CAPA编号": "CAPA-1",
                "计划内容": "修订 SOP",
                "责任人": "张三",
                "责任人确认": "是",
                "部门负责人": "李四",
                "部门负责人确认": "否",
                "进度": "完成",
                "提醒状态": "已提醒",
                "完成时间": "2026-09-01",
            },
        ),
        _record(
            "new",
            {
                "CAPA编号": "CAPA-2",
                "计划内容": "开展培训",
                "责任人确认": True,
                "部门负责人确认": False,
                "完成时间": "2026-09-02T08:00:00Z",
            },
        ),
    ]
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    monkeypatch.setattr(
        service, "_search_entity_records", AsyncMock(return_value=records)
    )
    monkeypatch.setattr(
        service.repository,
        "get_capa_by_code",
        AsyncMock(side_effect=[None, capa, capa]),
    )
    db = _Db([_Result(one=existing), _Result(one=None)])

    result = await service.sync_capa_plan_tracks_from_feishu(db)

    assert result == {"synced": 2, "failed": 2}
    assert existing.capa_id == capa.id
    assert existing.owner_confirmed is True
    assert existing.department_head_confirmed is False
    assert existing.progress == "完成"
    assert len(db.added) == 1
    assert db.commits == 2


@pytest.mark.asyncio
async def test_sync_functions_return_zero_when_runtime_or_search_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _Db()
    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(side_effect=AppException(message="disabled")),
    )
    assert await service.sync_capas_from_feishu(db) == {"synced": 0, "failed": 0}
    assert await service.sync_capa_plan_tracks_from_feishu(db) == {
        "synced": 0,
        "failed": 0,
    }

    monkeypatch.setattr(
        service,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(object(), object())),
    )
    monkeypatch.setattr(
        service,
        "_search_entity_records",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    )
    assert await service.sync_capas_from_feishu(db) == {"synced": 0, "failed": 0}
    assert await service.sync_capa_plan_tracks_from_feishu(db) == {
        "synced": 0,
        "failed": 0,
    }
