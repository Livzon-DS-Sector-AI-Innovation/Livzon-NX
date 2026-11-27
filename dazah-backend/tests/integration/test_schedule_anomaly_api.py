"""排产异常记录端点集成测试。

- HTTP 层：真实路由 + mock 服务层 DB 调用（沿用排产存档接口测试模式）；
- 覆盖列表分页契约、新增成功、入参校验 400、响应结构。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.production.schedule_anomaly_api as anomaly_api
from app.core.database import get_db
from app.main import app
from app.modules.production.schedule_anomaly_models import ScheduleAnomalyRecord
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API_PREFIX = "/api/v1/production/schedule-anomalies"


def _fake_record(**overrides: Any) -> ScheduleAnomalyRecord:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "product_code": "FA",
        "batch_no": "FA26314",
        "tank_no": "202A",
        "anomaly_type": "reseeded",
        "event_date": date(2026, 11, 28),
        "reason": "移种延后，原接种作废",
        "remark": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ScheduleAnomalyRecord(**defaults)


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    async def _override_current_user() -> User:
        return User(
            id=uuid.uuid4(),
            name="异常接口测试用户",
            username=f"anomaly-api-{uuid.uuid4().hex[:10]}",
            role="admin",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def no_real_db(monkeypatch: Any) -> None:
    """HTTP 层不触碰数据库：mock get_db 与服务层 DB 函数。"""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield AsyncMock(spec=AsyncSession)

    app.dependency_overrides[get_db] = _override_get_db
    monkeypatch.setattr(
        anomaly_api.schedule_anomaly_service,
        "list_anomalies",
        AsyncMock(
            return_value=([(_fake_record(), "标记人")], 1), name="list"
        ),
    )
    monkeypatch.setattr(
        anomaly_api.schedule_anomaly_service,
        "create_anomaly",
        AsyncMock(return_value=_fake_record(), name="create"),
    )
    monkeypatch.setattr(
        anomaly_api.schedule_anomaly_service,
        "list_anomalies_for_export",
        AsyncMock(return_value=[(_fake_record(), "标记人")], name="export"),
    )
    monkeypatch.setattr(
        anomaly_api.schedule_anomaly_service,
        "build_anomalies_workbook",
        lambda rows: b"PKfake-xlsx",
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_list_returns_paginated_contract(
    auth_client: AsyncClient, no_real_db: None
) -> None:
    response = await auth_client.get(
        f"{API_PREFIX}?page=1&page_size=20&product=FA&anomaly_type=reseeded"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["meta"]["total"] == 1
    item = body["data"][0]
    assert item["batch_no"] == "FA26314"
    assert item["anomaly_type_label"] == "补种"
    assert item["created_by_name"] == "标记人"

    call = anomaly_api.schedule_anomaly_service.list_anomalies.await_args
    assert call.kwargs["anomaly_type"] == "reseeded"
    assert call.kwargs["page"] == 1


@pytest.mark.anyio
async def test_list_rejects_unknown_anomaly_type(
    auth_client: AsyncClient, no_real_db: None
) -> None:
    response = await auth_client.get(f"{API_PREFIX}?anomaly_type=unknown")
    assert response.status_code == 400


@pytest.mark.anyio
async def test_create_returns_serialized_record(
    auth_client: AsyncClient, no_real_db: None
) -> None:
    payload = {
        "product_code": "FA",
        "batch_no": "FA26314",
        "tank_no": "202A",
        "anomaly_type": "reseeded",
        "event_date": "2026-11-28",
        "reason": "移种延后，原接种作废",
    }
    response = await auth_client.post(API_PREFIX, json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "异常已登记"
    assert body["data"]["anomaly_type_label"] == "补种"
    assert body["data"]["event_date"] == "2026-11-28"

    call = anomaly_api.schedule_anomaly_service.create_anomaly.await_args
    assert call.kwargs["batch_no"] == "FA26314"
    assert call.kwargs["created_by"] is not None


@pytest.mark.anyio
async def test_export_streams_xlsx_with_filters(
    auth_client: AsyncClient, no_real_db: None
) -> None:
    response = await auth_client.get(
        f"{API_PREFIX}/export?product=FA&anomaly_type=reseeded"
    )
    assert response.status_code == 200, response.text
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    disposition = response.headers["content-disposition"]
    assert "schedule-anomalies" not in disposition
    call = anomaly_api.schedule_anomaly_service.list_anomalies_for_export.await_args
    assert call.kwargs["product_code"] == "FA"
    assert call.kwargs["anomaly_type"] == "reseeded"


@pytest.mark.anyio
async def test_create_maps_validation_error_to_400(
    auth_client: AsyncClient, no_real_db: None
) -> None:
    from app.modules.production.schedule_anomaly_service import (
        AnomalyValidationError,
    )

    anomaly_api.schedule_anomaly_service.create_anomaly.side_effect = (
        AnomalyValidationError("原因不能为空")
    )
    response = await auth_client.post(
        API_PREFIX,
        json={
            "product_code": "FA",
            "batch_no": "FA26316",
            "anomaly_type": "other",
            "event_date": "2026-11-28",
            "reason": "",
        },
    )
    assert response.status_code == 400
    assert "原因不能为空" in response.json()["message"]


@pytest.mark.anyio
async def test_create_rejects_missing_required_fields(
    auth_client: AsyncClient, no_real_db: None
) -> None:
    response = await auth_client.post(
        API_PREFIX,
        json={"product_code": "FA", "batch_no": "FA26316"},
    )
    assert response.status_code == 422
