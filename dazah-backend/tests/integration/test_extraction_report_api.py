"""提炼工段成品日报端点集成测试。

- 真库冒烟：日报 upsert（同日覆盖）与列表过滤（自建会话）。
- 权限：页面范围不包含提炼工段时 403，旧权限不得扩大范围。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.modules.production.extraction_report_api as extraction_api
import app.platform.identity.rbac as identity_rbac
from app.platform.identity.page_permissions import PagePermissionService
from app.platform.identity.schemas import PageDataScopeInput
from tests.modules.production.test_page_permission_acceptance import acceptance_app

API = "/api/v1/production/extraction-daily-reports"


@pytest.fixture
async def auth_client(
    monkeypatch: Any,
) -> AsyncIterator[AsyncClient]:
    app, _ = acceptance_app(
        extraction_api.router, monkeypatch, "production:overview",
        scope_type="production_extraction",
    )
    monkeypatch.setattr(
        identity_rbac,
        "resolve_user_permissions",
        AsyncMock(return_value=["*"]),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        headers={"X-Dazah-Page-Key": "production:overview"},
    ) as client:
        yield client


@pytest.mark.anyio
async def test_daily_report_requires_extraction_page_scope(
    auth_client: AsyncClient,
    monkeypatch: Any,
) -> None:
    """仅发酵范围：旧通配权限不能放开成品日报。"""
    PagePermissionService.effective_grants.return_value[0].data_scope = (
        PageDataScopeInput(scope_type="production_fermentation")
    )
    monkeypatch.setattr(
        identity_rbac,
        "resolve_user_permissions",
        AsyncMock(return_value=["*"]),
    )
    denied_list = await auth_client.get(API)
    assert denied_list.status_code == 403
    assert "提炼工段" in denied_list.json()["detail"]

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
