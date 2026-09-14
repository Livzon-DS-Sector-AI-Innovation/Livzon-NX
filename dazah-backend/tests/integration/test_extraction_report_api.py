"""提炼工段成品日报端点集成测试。

- 真库冒烟：日报 upsert（同日覆盖）与列表过滤（自建会话）。
- 权限：无提炼产量权限时 403，且不触达数据层（HTTP 层，权限解析 mock）。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

import app.modules.production.extraction_report_api as extraction_api
import app.platform.identity.rbac as identity_rbac
from app.main import app
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API = "/api/v1/production/extraction-daily-reports"


@pytest.fixture
async def auth_client(
    client: AsyncClient, monkeypatch: Any
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(
        identity_rbac,
        "resolve_user_permissions",
        AsyncMock(return_value=["*"]),
    )

    async def _override_current_user() -> User:
        return User(
            id=uuid.uuid4(),
            name="提炼测试用户",
            username=f"extract-test-{uuid.uuid4().hex[:10]}",
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


@pytest.mark.anyio
async def test_daily_report_requires_extract_permission(
    auth_client: AsyncClient,
    monkeypatch: Any,
) -> None:
    """无提炼产量权限：列表与写入均 403，且不触达数据层。"""
    monkeypatch.setattr(
        identity_rbac,
        "resolve_user_permissions",
        AsyncMock(return_value=["production:fermentation-yield"]),
    )
    denied_list = await auth_client.get(API)
    assert denied_list.status_code == 403
    assert "提炼产量权限" in denied_list.json()["message"]

    denied_post = await auth_client.post(
        API, json={"report_date": "2026-09-10", "quantity_kg": 1200}
    )
    assert denied_post.status_code == 403


@pytest.mark.anyio
async def test_daily_report_rejects_missing_fields(auth_client: AsyncClient) -> None:
    """缺日期或成品量时 422（Schema 必填校验）。"""
    missing_quantity = await auth_client.post(API, json={"report_date": "2026-09-10"})
    assert missing_quantity.status_code == 422
    negative = await auth_client.post(
        API, json={"report_date": "2026-09-10", "quantity_kg": -1}
    )
    assert negative.status_code == 422


@pytest.mark.anyio
async def test_daily_report_upsert_overwrite_and_list(monkeypatch: Any) -> None:
    """真库冒烟：录入 → 同日覆盖 → 周期过滤列表（自建会话，避免跨循环）。

    权限守卫单独由 HTTP 用例覆盖，这里直接跳过守卫以使用自建会话；
    current_user 传 None 使 created_by/updated_by 落空值（满足用户表外键）。
    """
    from sqlalchemy import pool as sa_pool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from tests.db_safety import get_pytest_database_url

    monkeypatch.setattr(
        extraction_api, "_require_extract_permission", AsyncMock(return_value=None)
    )
    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            first = await extraction_api.upsert_extraction_daily_report(
                body=extraction_api.DailyReportBody(
                    report_date=date(2026, 9, 9), quantity_kg=1200.0
                ),
                db=session,
                current_user=None,
                product="FA",
            )
            assert json.loads(first.body)["data"]["quantity_kg"] == 1200.0
            item_id = json.loads(first.body)["data"]["id"]

            # 同日重复录入 → 覆盖更新（同一条记录）
            again = await extraction_api.upsert_extraction_daily_report(
                body=extraction_api.DailyReportBody(
                    report_date=date(2026, 9, 9), quantity_kg=1350.0
                ),
                db=session,
                current_user=None,
                product="FA",
            )
            assert json.loads(again.body)["data"]["id"] == item_id
            assert json.loads(again.body)["data"]["quantity_kg"] == 1350.0

            # 不同产品隔离
            await extraction_api.upsert_extraction_daily_report(
                body=extraction_api.DailyReportBody(
                    report_date=date(2026, 9, 9), quantity_kg=1.0
                ),
                db=session,
                current_user=None,
                product="MC",
            )

            # 周期过滤列表：按日期升序
            listed = await extraction_api.list_extraction_daily_reports(
                db=session,
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 30),
                product="FA",
                current_user=None,
            )
            rows = json.loads(listed.body)["data"]
            row = next(r for r in rows if r["report_date"] == "2026-09-09")
            assert row["quantity_kg"] == 1350.0
    finally:
        await engine.dispose()
