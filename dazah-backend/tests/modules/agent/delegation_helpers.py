"""Signed test identities exercise the real gateway authorization boundary."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.modules.agent.schemas import AgentTrustedSubject
from app.platform.identity.agent_delegation import issue_agent_delegation
from app.platform.identity.models import ExternalIdentityBinding, User


async def delegated_subject(
    db: AsyncSession, settings: Settings, user: User, source: str
) -> tuple[AgentTrustedSubject, dict[str, str]]:
    binding_id = None
    if source == "feishu":
        binding = ExternalIdentityBinding(
            tenant_id=user.tenant_key or "default",
            platform="feishu",
            app_fingerprint="security-regression",
            external_open_id=f"test-{uuid4().hex}",
            local_user_id=user.id,
            status="active",
        )
        db.add(binding)
        await db.flush()
        binding_id = binding.id
    subject = AgentTrustedSubject.model_validate({
        "user_id": user.id,
        "tenant_id": user.tenant_key or "default",
        "source": source,
        "external_binding_id": binding_id,
    })
    return subject, {
        "Authorization": f"Bearer {settings.AGENT_TOOL_TOKEN}",
        "X-Dazah-Delegation": issue_agent_delegation(
            settings, user, source=source, external_binding_id=binding_id
        ),
    }
