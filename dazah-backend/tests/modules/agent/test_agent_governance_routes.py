import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent import api
from app.modules.agent.repository import AgentRepository


@pytest.mark.anyio
async def test_safe_trace_export_contains_only_metadata_and_valid_digest(
    db_session: AsyncSession,
) -> None:
    trace_id = uuid4()
    admin = SimpleNamespace(id=uuid4(), role="admin")

    response = await api.export_control_plane_trace(
        trace_id=trace_id,
        db=db_session,
        current_user=admin,
    )
    payload = json.loads(response.body)

    assert payload["content_policy"] == (
        "metadata_only_no_business_body_or_credentials"
    )
    assert payload["filters"] == {"trace_id": str(trace_id)}
    assert payload["trace"]["timeline"] == []
    canonical = json.dumps(
        payload["trace"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert payload["verification"]["sha256"] == hashlib.sha256(canonical).hexdigest()
    assert response.headers["content-disposition"].endswith(f"{trace_id}.json\"")


@pytest.mark.anyio
async def test_runtime_overview_reports_empty_healthy_baseline(
    db_session: AsyncSession,
) -> None:
    response = await api.get_control_plane_runtime_overview(
        db=db_session,
        current_user=SimpleNamespace(id=uuid4(), role="admin"),
    )
    payload = json.loads(response.body)["data"]

    assert payload == {
        "pending_confirmations": 0,
        "failed_deliveries": 0,
        "latest_error_trace_id": None,
        "latest_error_at": None,
    }


@pytest.mark.anyio
async def test_runtime_overview_rejects_non_admin(db_session: AsyncSession) -> None:
    with pytest.raises(HTTPException) as exc:
        await api.get_control_plane_runtime_overview(
            db=db_session,
            current_user=SimpleNamespace(id=uuid4(), role="user"),
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.anyio
async def test_confirmation_control_list_persists_expired_status(
    db_session: AsyncSession,
) -> None:
    confirmation = await AgentRepository().create_confirmation(
        db_session,
        session_id=None,
        user_id=None,
        operation="identity.deliver_feishu_message",
        summary="过期投递确认",
        risk_level="medium",
        request_payload={},
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    response = await api.list_control_plane_confirmations(
        page=1,
        page_size=20,
        status_value=None,
        user_id=None,
        db=db_session,
        current_user=SimpleNamespace(id=uuid4(), role="admin"),
    )
    payload = json.loads(response.body)["data"]

    assert payload["items"][0]["id"] == str(confirmation.id)
    assert payload["items"][0]["status"] == "expired"
