from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.platform.audit.models import AuditLog
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User
from app.platform.system.feedback_api import router
from app.platform.system.feedback_service import (
    MAX_SCREENSHOT_BYTES,
    validate_screenshot,
)


def screenshot_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 30), "white").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
async def feedback_client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, dict[str, User | None]]]:
    actor = User(id=uuid4(), name="反馈测试提交者", role="user", status="active")
    db_session.add(actor)
    await db_session.flush()
    state: dict[str, User | None] = {"user": actor}
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def user() -> User | None:
        return state["user"]

    async def db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_db] = db
    monkeypatch.setattr("app.platform.identity.rbac.is_ordinary_admin", _not_ordinary)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, state


async def _not_ordinary(_db: AsyncSession, _user_id: object) -> bool:
    return False


async def submit(client: AsyncClient, *, feedback_id: str | None = None, **fields: str):
    return await client.post(
        "/api/v1/identity/me/feedback",
        data={
            "feedback_id": feedback_id or str(uuid4()),
            "description": "点击保存按钮后页面出现错误提示，无法保存。",
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
            "page_path": "/production",
            **fields,
        },
        files=[("screenshots", ("problem.png", screenshot_bytes(), "image/png"))],
    )


@pytest.mark.asyncio
async def test_feedback_submission_owner_isolation_and_admin_reply(
    feedback_client, db_session: AsyncSession
) -> None:
    client, state = feedback_client
    owner = state["user"]
    response = await submit(client)
    assert response.status_code == 201
    record = response.json()
    assert record["status"] == "pending"
    assert record["reporter_name"] == owner.name
    assert len(record["screenshots"]) == 1
    assert "content" not in record["screenshots"][0]
    own = await client.get("/api/v1/identity/me/feedback")
    assert own.status_code == 200
    assert own.json()["total"] == 1
    image_path = (
        f"/api/v1/identity/me/feedback/{record['id']}/screenshots/"
        f"{record['screenshots'][0]['id']}"
    )
    image = await client.get(image_path)
    assert image.status_code == 200
    assert image.headers["cache-control"] == "private, no-store"
    assert image.headers["content-type"] == "image/jpeg"

    outsider = User(id=uuid4(), name="另一个测试用户", role="user", status="active")
    db_session.add(outsider)
    await db_session.flush()
    state["user"] = outsider
    assert (await client.get(image_path)).status_code == 404
    assert (await client.get("/api/v1/identity/me/feedback")).json()["total"] == 0
    assert (await client.get("/api/v1/identity/admin/feedback")).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/identity/admin/feedback/{record['id']}",
            json={"status": "resolved", "reply": "已修复", "version": 1},
        )
    ).status_code == 403

    outsider.role = "admin"
    inbox = await client.get("/api/v1/identity/admin/feedback?status=pending")
    assert inbox.status_code == 200
    assert record["id"] in [item["id"] for item in inbox.json()["items"]]
    result = await client.patch(
        f"/api/v1/identity/admin/feedback/{record['id']}",
        json={
            "status": "resolved",
            "reply": "已修复保存异常，请重新尝试。",
            "version": 1,
        },
    )
    assert result.status_code == 200
    assert result.json()["version"] == 2
    assert result.json()["status"] == "resolved"
    conflict = await client.patch(
        f"/api/v1/identity/admin/feedback/{record['id']}",
        json={"status": "processing", "version": 1},
    )
    assert conflict.status_code == 409
    state["user"] = owner
    updated = await client.get("/api/v1/identity/me/feedback")
    assert updated.json()["items"][0]["reply"] == "已修复保存异常，请重新尝试。"
    audit = await db_session.execute(
        select(AuditLog).where(AuditLog.resource_id == record["id"])
    )
    assert {row.action for row in audit.scalars()} == {
        "feedback_submitted",
        "feedback_updated",
    }


@pytest.mark.asyncio
async def test_submission_retry_is_idempotent(feedback_client) -> None:
    client, _ = feedback_client
    ticket = str(uuid4())
    first = await submit(client, feedback_id=ticket)
    second = await submit(client, feedback_id=ticket)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"] == ticket
    assert (await client.get("/api/v1/identity/me/feedback")).json()["total"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"description": "          "},
        {"occurred_at": datetime.now(UTC).replace(tzinfo=None).isoformat()},
        {"occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        {"page_path": "/production?private=value"},
    ],
)
async def test_rejects_invalid_fields(feedback_client, fields) -> None:
    client, _ = feedback_client
    assert (await submit(client, **fields)).status_code == 422
    assert (await client.get("/api/v1/identity/me/feedback")).json()["total"] == 0


@pytest.mark.asyncio
async def test_authentication_and_system_admin_only(
    feedback_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, state = feedback_client
    state["user"].role = "admin"

    async def ordinary(_db: AsyncSession, _user_id: object) -> bool:
        return True

    monkeypatch.setattr("app.platform.identity.rbac.is_ordinary_admin", ordinary)
    assert (await client.get("/api/v1/identity/admin/feedback")).status_code == 403
    assert (await submit(client)).status_code == 201
    state["user"] = None
    assert (await client.get("/api/v1/identity/me/feedback")).status_code == 401
    assert (await submit(client)).status_code == 401


@pytest.mark.parametrize(
    "content,mime",
    [
        (b"<svg></svg>", "image/svg+xml"),
        (b"invalid", "image/png"),
        (screenshot_bytes(), "image/jpeg"),
        (b"x" * (MAX_SCREENSHOT_BYTES + 1), "image/png"),
    ],
    ids=["svg", "corrupt", "mime-mismatch", "oversized"],
)
def test_screenshot_rejects_spoofed_or_oversized_uploads(
    content: bytes, mime: str
) -> None:
    with pytest.raises(HTTPException) as error:
        validate_screenshot(content, mime)
    assert error.value.status_code == 422


def test_screenshot_reencoding_discards_trailing_payload() -> None:
    normalized, mime = validate_screenshot(
        screenshot_bytes() + b"trailing-private-payload", "image/png"
    )
    assert mime == "image/jpeg"
    assert b"trailing-private-payload" not in normalized
