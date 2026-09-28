"""Gateway restart audit tests without a database or a live Gateway."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.platform.audit import middleware
from app.platform.audit.middleware import AuditMiddleware
from app.platform.audit.models import AuditLog
from app.platform.identity import service
from app.platform.identity.api import feishu_config_router
from app.platform.identity.deps import require_system_admin
from app.platform.identity.models import User
from app.platform.identity.schemas import FeishuGatewayRestartResult


class AuditSession:
    def __init__(self) -> None:
        self.records: list[AuditLog] = []

    async def __aenter__(self) -> "AuditSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        pass

    def add(self, record: AuditLog) -> None:
        self.records.append(record)

    async def commit(self) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("failed", [False, True])
async def test_restart_audit_preserves_result_and_links_http_request(
    monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    actor = User(id=uuid4(), role="admin")
    session = AuditSession()
    result = FeishuGatewayRestartResult(
        status="connected",
        message="飞书连接已恢复",
        previous_reconnects=2,
        gateway_reconnects=3,
        config_version=4,
        credential_version=5,
    )
    monkeypatch.setattr(
        service,
        "restart_livzon_feishu_gateway",
        AsyncMock(
            return_value=result,
            side_effect=HTTPException(502, "Gateway 不可用") if failed else None,
        ),
    )
    monkeypatch.setattr(middleware, "async_session_factory", lambda: session)
    app = FastAPI()
    app.include_router(feishu_config_router, prefix="/api/v1/identity")
    app.add_middleware(AuditMiddleware)

    async def database() -> Any:
        return session

    async def administrator(request: Request) -> User:
        request.state.audit_user_id = actor.id
        return actor

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_system_admin] = administrator
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/identity/feishu-config/gateway/restart")
    assert response.status_code == (502 if failed else 200)
    if failed:
        assert response.json()["detail"] == "Gateway 不可用"
        assert len(session.records) == 1
        assert session.records[0].action == "platform_api_request"
        assert session.records[0].status_code == 502
        return
    assert response.json()["data"] == result.model_dump(mode="json")
    event, operation = session.records
    assert event.action == "restart_livzon_feishu_gateway"
    assert event.request_id == operation.request_id == response.headers["X-Request-ID"]
    assert event.new_value == result.model_dump(
        mode="json", exclude={"credential_version"}
    )
    assert event.extra == {
        "status": "connected",
        "previous_reconnects": 2,
        "gateway_reconnects": 3,
        "config_version": 4,
    }
    assert event.old_value is None
