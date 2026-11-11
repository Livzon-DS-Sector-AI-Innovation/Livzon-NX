"""图表警戒线 API 测试：鉴权、upsert 创建/更新、读取映射。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.modules.production import chart_thresholds_api as api
from app.modules.production.chart_threshold_models import ChartThreshold
from app.platform.identity.models import User


class _Result:
    """execute() 返回值桩：链式 .scalars().first()/.all()。"""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


def _admin() -> User:
    return User(
        name="警戒线管理员",
        username="threshold-admin",
        role="admin",
        status="active",
        auth_source="local",
    )


def _user() -> User:
    return User(
        name="普通用户",
        username="threshold-user",
        role="user",
        status="active",
        auth_source="local",
    )


@pytest.mark.anyio
async def test_list_requires_login() -> None:
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await api.list_chart_thresholds(
            scope_key="workshop-201-2/crude-extraction",
            db=db,
            current_user=None,
        )
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_upsert_requires_admin() -> None:
    db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await api.upsert_chart_threshold(
            api.ChartThresholdUpsert(
                scope_key="workshop-201-2/crude-extraction",
                chart_key="yield",
                threshold=90,
            ),
            db=db,
            current_user=_user(),
        )
    assert exc.value.status_code == 403
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_upsert_creates_when_missing() -> None:
    db = AsyncMock()
    db.execute.return_value = _Result([])
    admin = _admin()
    await api.upsert_chart_threshold(
        api.ChartThresholdUpsert(
            scope_key="workshop-201-2/crude-extraction",
            chart_key="yield",
            threshold=95,
        ),
        db=db,
        current_user=admin,
    )
    db.add.assert_called_once()
    row = db.add.call_args.args[0]
    assert isinstance(row, ChartThreshold)
    assert row.scope_key == "workshop-201-2/crude-extraction"
    assert row.chart_key == "yield"
    assert row.threshold == 95.0
    assert row.updated_by == admin.id
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_upsert_updates_existing() -> None:
    existing = ChartThreshold(
        scope_key="workshop-201-2/crude-extraction", chart_key="yield"
    )
    existing.threshold = 92.0
    db = AsyncMock()
    db.execute.return_value = _Result([existing])
    admin = _admin()
    await api.upsert_chart_threshold(
        api.ChartThresholdUpsert(
            scope_key="workshop-201-2/crude-extraction",
            chart_key="yield",
            threshold=90,
        ),
        db=db,
        current_user=admin,
    )
    assert existing.threshold == 90.0
    assert existing.updated_by == admin.id
    db.add.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_list_returns_chart_key_map() -> None:
    row_a = ChartThreshold(
        scope_key="workshop-201-2/crude-extraction", chart_key="yield"
    )
    row_a.threshold = 95.0
    row_b = ChartThreshold(
        scope_key="workshop-201-2/crude-extraction", chart_key="pass_rate"
    )
    row_b.threshold = 80.0
    db = AsyncMock()
    db.execute.return_value = _Result([row_a, row_b])
    resp = await api.list_chart_thresholds(
        scope_key="workshop-201-2/crude-extraction",
        db=db,
        current_user=_admin(),
    )
    body = json.loads(resp.body)
    assert body["code"] == 200
    assert body["data"] == {"yield": 95.0, "pass_rate": 80.0}
