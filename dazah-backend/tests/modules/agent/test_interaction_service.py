import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.interaction_schemas import (
    FeishuResourceTemplateCreate,
    InteractionFormField,
    InteractionRequestCreate,
    InteractionSubmissionCreate,
)
from app.modules.agent.interaction_service import AgentInteractionService
from app.modules.agent.models import AgentInteractionSubmission
from app.platform.identity.models import User


@pytest.mark.anyio
async def test_card_form_submission_is_idempotent_and_writes_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = User(
        name="Interaction User",
        username=f"interaction-{uuid.uuid4().hex[:12]}",
        role="user",
        status="active",
        auth_source="local",
    )
    db_session.add(user)
    await db_session.flush()
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_hermes(path: str, payload: dict[str, object]) -> dict[str, object]:
        calls.append((path, payload))
        if path.endswith("/inspect"):
            return {"fields": [{"field_name": "name"}, {"field_name": "amount"}]}
        return {"result": {"record_id": "rec-1"}}

    monkeypatch.setattr(
        AgentInteractionService, "_hermes_request", staticmethod(fake_hermes)
    )
    service = AgentInteractionService()
    template = await service.create_template(
        db_session,
        user=user,
        request=FeishuResourceTemplateCreate(
            name="收集模板",
            resource_url="https://example.feishu.cn/base/example",
            base_token="base-token",
            table_id="table-id",
            field_schema=[
                InteractionFormField(key="name", label="姓名", type="text"),
                InteractionFormField(key="amount", label="数量", type="number"),
            ],
            writable_fields=["name", "amount"],
        ),
    )
    template = await service.validate_template(
        db_session, user=user, template_id=template.id
    )
    assert template.status == "active"
    artifact = await service.create_request(
        db_session,
        user=user,
        request=InteractionRequestCreate(
            template_id=template.id,
            recipient_user_id=user.id,
            mode="card_form",
            title="请填写",
            form_schema=[
                InteractionFormField(
                    key="name", label="姓名", type="text", required=True
                ),
                InteractionFormField(key="amount", label="数量", type="number"),
            ],
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            idempotency_key="request-1",
        ),
    )
    submission = InteractionSubmissionCreate(
        request_version=artifact.version,
        idempotency_key="submission-1",
        values={"name": "张三", "amount": "2"},
    )

    first = await service.submit(
        db_session,
        user=user,
        request_id=artifact.request_id,
        request=submission,
    )
    second = await service.submit(
        db_session,
        user=user,
        request_id=artifact.request_id,
        request=submission,
    )

    assert first.status == second.status == "completed"
    count = await db_session.scalar(
        select(func.count()).select_from(AgentInteractionSubmission)
    )
    assert count == 1
    assert [path for path, _ in calls].count(
        "/internal/automation/bitable/records"
    ) == 1
