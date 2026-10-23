from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.main import app
from app.modules.energy import ledger_notifications as notifications
from app.modules.energy.ledger_models import (
    EnergyBotConfig,
    EnergyCalculationRule,
    EnergyLedgerRevision,
    EnergyMeterPoint,
    EnergyNotificationRun,
    EnergyReading,
    EnergyUsageFact,
)
from app.modules.energy.ledger_schemas import MeterDefinition
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User
from app.platform.integrations.feishu.im import FeishuMessageSendResult


@pytest.fixture
async def direct_client(db_session, monkeypatch):
    actor = User(
        id=uuid4(),
        username="direct-" + uuid4().hex,
        name="能源录入测试",
        role="admin",
        status="active",
        auth_source="local",
    )
    db_session.add(actor)
    await db_session.flush()
    definition = MeterDefinition(
        code="direct_" + uuid4().hex,
        name="101车间电量",
        category="electricity",
        reading_type="direct",
        quantity_kind="electricity",
        area="101",
        department="101车间",
        unit="kWh",
        source_sheet="电量",
        source_column=3,
        active_from=date(2026, 7, 1),
        active_to=date(2026, 8, 1),
        enabled=False,
    )
    point = EnergyMeterPoint(
        id=uuid4(),
        code=definition.code,
        definition=definition.model_dump(mode="json"),
        version=1,
    )
    db_session.add(point)
    await db_session.flush()

    async def user():
        return actor

    async def database():
        yield db_session

    @asynccontextmanager
    async def admission(kind):
        yield

    monkeypatch.setattr("app.core.maintenance_middleware.business_activity", admission)
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Dazah-Page-Key": "energy:entry"},
        ) as client:
            yield client, db_session, point
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_direct_entry_ignores_old_activation_dates(direct_client):
    client, db, point = direct_client
    params = {"reading_date": "2026-10-20", "dataset": "电量"}
    response = await client.get("/api/v1/energy/input-readings", params=params)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["point_id"] == str(point.id)
    payload = {
        **params,
        "values": [{"point_id": str(point.id), "version": 0, "value": "0"}],
    }
    response = await client.put("/api/v1/energy/input-readings", json=payload)
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["data"]["items"][0]["value"]) == 0
    assert response.json()["data"]["items"][0]["version"] == 1
    fact = await db.scalar(
        select(EnergyUsageFact).where(
            EnergyUsageFact.metric_key == "point:" + point.code
        )
    )
    assert fact is not None and fact.effective_value == 0
    revisions = (
        await db.scalars(
            select(EnergyLedgerRevision).where(
                EnergyLedgerRevision.entity_kind == "reading"
            )
        )
    ).all()
    assert len(revisions) == 1


@pytest.mark.asyncio
async def test_direct_entry_draft_conflict_and_correction_reason(direct_client):
    client, db, point = direct_client
    payload = {
        "reading_date": "2026-10-20",
        "dataset": "电量",
        "values": [{"point_id": str(point.id), "version": 0, "value": "12.5"}],
        "draft": True,
    }
    response = await client.put("/api/v1/energy/input-readings", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["value"] is None
    assert Decimal(response.json()["data"]["items"][0]["draft_value"]) == Decimal(
        "12.5"
    )
    payload["draft"] = False
    assert (
        await client.put("/api/v1/energy/input-readings", json=payload)
    ).status_code == 409
    payload["values"][0]["version"] = 1
    assert (
        await client.put("/api/v1/energy/input-readings", json=payload)
    ).status_code == 200
    payload["values"][0].update(version=2, value="20")
    assert (
        await client.put("/api/v1/energy/input-readings", json=payload)
    ).status_code == 422
    payload["reason"] = "核对原始读数"
    assert (
        await client.put("/api/v1/energy/input-readings", json=payload)
    ).status_code == 200
    row = await db.scalar(
        select(EnergyReading).where(EnergyReading.point_id == point.id)
    )
    assert row.value == 20 and row.version == 3
    payload["values"][0].update(version=3, value="30")
    payload["draft"] = True
    assert (
        await client.put("/api/v1/energy/input-readings", json=payload)
    ).status_code == 200
    payload["values"][0].update(version=4, value="20")
    payload["draft"] = False
    response = await client.put("/api/v1/energy/input-readings", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["draft_value"] is None
    assert row.value == 20 and row.version == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dataset,value,status",
    [("日总量", "1", 422), ("电量", "-1", 422), ("饮用水码", "1", 403)],
)
async def test_direct_entry_validates_source_fields(
    direct_client, dataset, value, status
):
    client, _, point = direct_client
    payload = {
        "reading_date": "2026-10-20",
        "dataset": dataset,
        "values": [{"point_id": str(point.id), "version": 0, "value": value}],
    }
    response = await client.put("/api/v1/energy/input-readings", json=payload)
    assert response.status_code == status, response.text


def test_removed_management_routes_are_not_registered():
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for suffix in (
        "meter-points",
        "calculation-rules",
        "entry-plans",
        "entry-tasks",
        "entry-tasks/generate",
        "adjustments",
        "period-locks",
        "reporting/rebuild",
        "feishu-config",
        "sources",
        "sync-runs",
        "overview",
        "page-data/energy",
        "imports/snapshot-options",
        "imports/from-snapshot",
    ):
        assert "/api/v1/energy/" + suffix not in paths


@pytest.mark.asyncio
async def test_overview_reads_legacy_unconfirmed_workbook_metadata(direct_client):
    client, db, point = direct_client
    point.definition = dict(point.definition, unit="待确认", department="待确认")
    db.add(
        EnergyCalculationRule(
            id=uuid4(),
            code="legacy_total",
            version=1,
            definition={
                "code": "legacy_total",
                "name": "日总量·电量",
                "category": "electricity",
                "department": "待确认",
                "unit": "待确认",
                "active_from": "2026-07-01",
                "enabled": False,
                "report_scope": "plant",
                "quantity_kind": "electricity",
                "terms": [{"metric_key": "point:" + point.code, "coefficient": "1"}],
            },
        )
    )
    await db.flush()
    response = await client.get(
        "/api/v1/energy/reporting",
        params={
            "start_date": "2026-10-01",
            "end_date": "2026-10-01",
            "report_scope": "plant",
            "include_basis": "true",
        },
        headers={"X-Dazah-Page-Key": "energy:ledger-overview"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["totals"][0]["unit"] == "待确认"
    assert data["totals"][0]["basis"]["nodes"][0]["name"] == "电量"
    assert data["totals"][0]["value"] is None
    response = await client.get(
        "/api/v1/energy/input-readings",
        params={
            "reading_date": "2026-10-01",
            "dataset": "电量",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["items"][0]["unit"] == "待确认"


@pytest.mark.asyncio
async def test_direct_submission_notifies_actor_without_plan_or_task(
    direct_client, monkeypatch
):
    from unittest.mock import AsyncMock

    client, db, point = direct_client
    db.add(
        EnergyBotConfig(
            id=uuid4(),
            name="default",
            encrypted_secret="fake-encrypted-secret",
            definition={
                "enabled": True,
                "app_id": "test-app",
                "base_url": "https://example.test",
            },
        )
    )
    await db.flush()
    payload = {
        "reading_date": "2026-10-20",
        "dataset": "电量",
        "values": [{"point_id": str(point.id), "version": 0, "value": "25"}],
    }
    response = await client.put("/api/v1/energy/input-readings", json=payload)
    assert response.status_code == 200, response.text
    run = await db.scalar(select(EnergyNotificationRun))
    assert run is not None and run.definition["dataset"] == "电量"
    assert run.definition["reading_date"] == "2026-10-20"
    actor_id = run.definition["target"]
    await notifications.enqueue_reading_notification(
        db, UUID(actor_id), "电量", "2026-10-20", f"{point.id}-0", 1
    )
    assert await db.scalar(select(func.count()).select_from(EnergyNotificationRun)) == 1
    recipient = AsyncMock(return_value=("test-employee", "user_id"))
    token = AsyncMock(return_value="fake-test-token")
    send = AsyncMock(
        return_value=FeishuMessageSendResult(ok=True, message_id="test-message")
    )
    monkeypatch.setattr(notifications, "notification_recipient_for_user", recipient)
    monkeypatch.setattr(notifications.FeishuAuth, "get_tenant_access_token", token)
    monkeypatch.setattr(notifications, "decrypt_secret", lambda value: "fake-secret")
    monkeypatch.setattr(notifications, "send_feishu_message", send)
    await notifications.deliver_notifications(db, datetime.now(UTC))
    assert run.status == "sent" and run.message_id == "test-message"
    assert send.call_args.kwargs["tenant_access_token"] == "fake-test-token"
    assert send.call_args.kwargs["receive_id"] == "test-employee"
    assert "date=2026-10-20" in send.call_args.kwargs["content"]
    assert "/energy/entry?" in send.call_args.kwargs["content"]
    await notifications.deliver_notifications(db, datetime.now(UTC))
    send.assert_awaited_once()
