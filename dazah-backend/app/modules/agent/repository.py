import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import normalize_correlation_id

from .models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentAutomationTrigger,
    AgentAutomationVersion,
    AgentConfirmation,
    AgentMessage,
    AgentRunEvent,
    AgentSession,
    AgentSkill,
    AgentStepRun,
    AgentToolCall,
    AgentWorkflow,
    AgentWorkflowRun,
)


class AgentRepository:
    async def create_automation(
        self,
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        source_session_id: uuid.UUID | None,
        name: str,
        description: str | None,
        scope_type: str,
        scope_ref: dict[str, Any],
    ) -> AgentAutomation:
        automation = AgentAutomation(
            owner_user_id=owner_user_id,
            source_session_id=source_session_id,
            name=name,
            description=description,
            scope_type=scope_type,
            scope_ref=scope_ref,
        )
        automation.created_by = owner_user_id
        automation.updated_by = owner_user_id
        db.add(automation)
        await db.flush()
        return automation

    async def create_automation_version(
        self,
        db: AsyncSession,
        *,
        automation_id: uuid.UUID,
        version: int,
        definition: dict[str, Any],
        policy_snapshot: dict[str, Any],
        capability_versions: dict[str, str],
        created_by: uuid.UUID,
        change_summary: str | None,
    ) -> AgentAutomationVersion:
        item = AgentAutomationVersion(
            automation_id=automation_id,
            version=version,
            definition=definition,
            policy_snapshot=policy_snapshot,
            capability_versions=capability_versions,
            created_by=created_by,
            updated_by=created_by,
            change_summary=change_summary,
        )
        db.add(item)
        await db.flush()
        return item

    async def replace_automation_triggers(
        self,
        db: AsyncSession,
        *,
        automation: AgentAutomation,
        triggers: list[dict[str, Any]],
        actor_id: uuid.UUID,
    ) -> list[AgentAutomationTrigger]:
        existing = await db.execute(
            select(AgentAutomationTrigger).where(
                AgentAutomationTrigger.automation_id == automation.id,
                AgentAutomationTrigger.is_deleted.is_(False),
            )
        )
        for item in existing.scalars():
            item.is_deleted = True
            item.updated_by = actor_id
        result: list[AgentAutomationTrigger] = []
        for raw in triggers:
            item = AgentAutomationTrigger(automation_id=automation.id, **raw)
            item.created_by = actor_id
            item.updated_by = actor_id
            db.add(item)
            result.append(item)
        await db.flush()
        return result

    async def get_automation(
        self, db: AsyncSession, automation_id: uuid.UUID
    ) -> AgentAutomation | None:
        result = await db.execute(
            select(AgentAutomation).where(
                AgentAutomation.id == automation_id,
                AgentAutomation.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_automation_version(
        self, db: AsyncSession, version_id: uuid.UUID
    ) -> AgentAutomationVersion | None:
        result = await db.execute(
            select(AgentAutomationVersion).where(
                AgentAutomationVersion.id == version_id,
                AgentAutomationVersion.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_automation_versions(
        self, db: AsyncSession, *, automation_id: uuid.UUID
    ) -> list[AgentAutomationVersion]:
        result = await db.execute(
            select(AgentAutomationVersion)
            .where(
                AgentAutomationVersion.automation_id == automation_id,
                AgentAutomationVersion.is_deleted.is_(False),
            )
            .order_by(AgentAutomationVersion.version.desc())
        )
        return list(result.scalars())

    async def list_automation_triggers(
        self, db: AsyncSession, *, automation_ids: list[uuid.UUID]
    ) -> list[AgentAutomationTrigger]:
        if not automation_ids:
            return []
        result = await db.execute(
            select(AgentAutomationTrigger)
            .where(
                AgentAutomationTrigger.automation_id.in_(automation_ids),
                AgentAutomationTrigger.is_deleted.is_(False),
            )
            .order_by(AgentAutomationTrigger.next_fire_at.asc().nullslast())
        )
        return list(result.scalars())

    async def list_automations(
        self,
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID | None,
        scope: str,
        status_value: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AgentAutomation], int]:
        query = select(AgentAutomation).where(AgentAutomation.is_deleted.is_(False))
        if scope == "mine":
            query = query.where(AgentAutomation.owner_user_id == owner_user_id)
        elif scope == "shared":
            query = query.where(AgentAutomation.scope_type == "shared")
        if status_value:
            query = query.where(AgentAutomation.status == status_value)
        count_query = select(func.count()).select_from(query.subquery())
        total = int((await db.execute(count_query)).scalar_one())
        result = await db.execute(
            query.order_by(AgentAutomation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars()), total

    async def list_automation_runs(
        self,
        db: AsyncSession,
        *,
        automation_ids: list[uuid.UUID],
        status_value: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AgentAutomationRun], int]:
        if not automation_ids:
            return [], 0
        query = select(AgentAutomationRun).where(
            AgentAutomationRun.is_deleted.is_(False),
            AgentAutomationRun.automation_id.in_(automation_ids),
        )
        if status_value:
            query = query.where(AgentAutomationRun.status == status_value)
        count_query = select(func.count()).select_from(query.subquery())
        total = int((await db.execute(count_query)).scalar_one())
        result = await db.execute(
            query.order_by(AgentAutomationRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars()), total

    async def get_automation_run(
        self, db: AsyncSession, run_id: uuid.UUID
    ) -> AgentAutomationRun | None:
        result = await db.execute(
            select(AgentAutomationRun).where(
                AgentAutomationRun.id == run_id,
                AgentAutomationRun.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_step_runs(
        self, db: AsyncSession, *, run_id: uuid.UUID
    ) -> list[AgentStepRun]:
        result = await db.execute(
            select(AgentStepRun)
            .where(AgentStepRun.run_id == run_id, AgentStepRun.is_deleted.is_(False))
            .order_by(AgentStepRun.created_at.asc())
        )
        return list(result.scalars())

    async def list_run_events(
        self, db: AsyncSession, *, run_id: uuid.UUID
    ) -> list[AgentRunEvent]:
        result = await db.execute(
            select(AgentRunEvent)
            .where(AgentRunEvent.run_id == run_id, AgentRunEvent.is_deleted.is_(False))
            .order_by(AgentRunEvent.occurred_at.asc())
        )
        return list(result.scalars())

    async def get_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> AgentSession | None:
        result = await db.execute(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def list_user_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[tuple[AgentSession, int, str | None, int]], int]:
        filters = (
            AgentSession.user_id == user_id,
            AgentSession.is_deleted.is_(False),
        )
        total = await db.scalar(select(func.count(AgentSession.id)).where(*filters))
        sessions = list(
            (
                await db.scalars(
                    select(AgentSession)
                    .where(*filters)
                    .order_by(AgentSession.updated_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        rows: list[tuple[AgentSession, int, str | None, int]] = []
        for session in sessions:
            message_count = await db.scalar(
                select(func.count(AgentMessage.id)).where(
                    AgentMessage.session_id == session.id,
                    AgentMessage.is_deleted.is_(False),
                )
            )
            last_message = await db.scalar(
                select(AgentMessage.content)
                .where(
                    AgentMessage.session_id == session.id,
                    AgentMessage.is_deleted.is_(False),
                )
                .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
                .limit(1)
            )
            pending_count = await db.scalar(
                select(func.count(AgentConfirmation.id)).where(
                    AgentConfirmation.session_id == session.id,
                    AgentConfirmation.status == "pending",
                    AgentConfirmation.expires_at > datetime.now(UTC),
                    AgentConfirmation.is_deleted.is_(False),
                )
            )
            rows.append(
                (session, message_count or 0, last_message, pending_count or 0)
            )
        return rows, total or 0

    async def archive_session(
        self,
        db: AsyncSession,
        *,
        session: AgentSession,
        user_id: uuid.UUID,
    ) -> AgentSession:
        session.status = "archived"
        session.updated_by = user_id
        await db.flush()
        return session

    async def create_session(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None,
        context: dict[str, Any],
        title: str | None,
    ) -> AgentSession:
        session = AgentSession(user_id=user_id, title=title, context=context)
        session.created_by = user_id
        session.updated_by = user_id
        db.add(session)
        await db.flush()
        return session

    async def get_active_channel_session(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: str,
        peer_id: str,
    ) -> AgentSession | None:
        result = await db.execute(
            select(AgentSession)
            .where(
                AgentSession.user_id == user_id,
                AgentSession.status == "active",
                AgentSession.is_deleted.is_(False),
                AgentSession.context["channel"].astext == channel,
                AgentSession.context["peer_id"].astext == peer_id,
            )
            .order_by(AgentSession.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def archive_active_channel_sessions(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        channel: str,
        peer_id: str,
    ) -> None:
        result = await db.execute(
            select(AgentSession).where(
                AgentSession.user_id == user_id,
                AgentSession.status == "active",
                AgentSession.is_deleted.is_(False),
                AgentSession.context["channel"].astext == channel,
                AgentSession.context["peer_id"].astext == peer_id,
            )
        )
        for session in result.scalars():
            session.status = "archived"
            session.updated_by = user_id
        await db.flush()

    async def add_message(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        user_id: uuid.UUID | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            session_id=session_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
            created_at=datetime.now(UTC),
        )
        message.created_by = user_id
        message.updated_by = user_id
        db.add(message)
        await db.flush()
        return message

    async def list_messages(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        limit: int = 20,
    ) -> list[AgentMessage]:
        result = await db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,
                AgentMessage.is_deleted.is_(False),
            )
            .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_all_messages(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
    ) -> list[AgentMessage]:
        result = await db.execute(
            select(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,
                AgentMessage.is_deleted.is_(False),
            )
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
        )
        return list(result.scalars().all())

    async def list_session_confirmations(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
    ) -> list[AgentConfirmation]:
        result = await db.execute(
            select(AgentConfirmation)
            .where(
                AgentConfirmation.session_id == session_id,
                AgentConfirmation.is_deleted.is_(False),
            )
            .order_by(AgentConfirmation.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_tool_call(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID | None,
        operation: str,
        request_payload: dict[str, Any],
    ) -> AgentToolCall:
        context = request_payload.get("context") or {}
        call = AgentToolCall(
            session_id=session_id,
            correlation_id=normalize_correlation_id(context.get("correlation_id")),
            operation=operation,
            request_payload=request_payload,
        )
        db.add(call)
        await db.flush()
        return call

    async def finish_tool_call(
        self,
        db: AsyncSession,
        call: AgentToolCall,
        *,
        status: str,
        response_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> AgentToolCall:
        call.status = status
        call.response_payload = response_payload
        call.error_message = error_message
        await db.flush()
        return call

    async def create_confirmation(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        operation: str,
        summary: str,
        risk_level: str,
        request_payload: dict[str, Any],
        expires_at: datetime,
    ) -> AgentConfirmation:
        confirmation = AgentConfirmation(
            session_id=session_id,
            user_id=user_id,
            operation=operation,
            summary=summary,
            risk_level=risk_level,
            request_payload=request_payload,
            expires_at=expires_at,
        )
        confirmation.created_by = user_id
        confirmation.updated_by = user_id
        db.add(confirmation)
        await db.flush()
        return confirmation

    async def get_confirmation(
        self,
        db: AsyncSession,
        confirmation_id: uuid.UUID,
    ) -> AgentConfirmation | None:
        result = await db.execute(
            select(AgentConfirmation).where(
                AgentConfirmation.id == confirmation_id,
                AgentConfirmation.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_confirmation_for_update(
        self,
        db: AsyncSession,
        confirmation_id: uuid.UUID,
    ) -> AgentConfirmation | None:
        """Lock one confirmation until the caller commits or rolls back.

        Feishu may redeliver the same card click concurrently.  The lock makes
        the pending-state check and the downstream write one atomic decision.
        """
        result = await db.execute(
            select(AgentConfirmation)
            .where(
                AgentConfirmation.id == confirmation_id,
                AgentConfirmation.is_deleted.is_(False),
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_pending_confirmations(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[AgentConfirmation]:
        if session_id is None and user_id is None:
            return []
        stmt = select(AgentConfirmation).where(
            AgentConfirmation.status == "pending",
            AgentConfirmation.expires_at > datetime.now(UTC),
            AgentConfirmation.is_deleted.is_(False),
        )
        if session_id is not None:
            stmt = stmt.where(AgentConfirmation.session_id == session_id)
        if user_id is not None:
            stmt = stmt.where(AgentConfirmation.user_id == user_id)
        result = await db.execute(stmt.order_by(AgentConfirmation.created_at.asc()))
        return list(result.scalars().all())

    async def execute_confirmation(
        self,
        db: AsyncSession,
        confirmation: AgentConfirmation,
        *,
        result_payload: dict[str, Any],
        user_id: uuid.UUID | None,
    ) -> AgentConfirmation:
        confirmation.status = "executed"
        confirmation.executed_at = datetime.now(UTC)
        confirmation.result_payload = result_payload
        confirmation.updated_by = user_id
        await db.flush()
        refreshed = await db.execute(
            select(AgentConfirmation)
            .where(
                AgentConfirmation.id == confirmation.id,
                AgentConfirmation.is_deleted.is_(False),
            )
            .execution_options(populate_existing=True)
        )
        return refreshed.scalar_one()

    async def cancel_confirmation(
        self,
        db: AsyncSession,
        confirmation: AgentConfirmation,
        *,
        user_id: uuid.UUID | None,
    ) -> AgentConfirmation:
        confirmation.status = "cancelled"
        confirmation.updated_by = user_id
        await db.flush()
        refreshed = await db.execute(
            select(AgentConfirmation)
            .where(
                AgentConfirmation.id == confirmation.id,
                AgentConfirmation.is_deleted.is_(False),
            )
            .execution_options(populate_existing=True)
        )
        return refreshed.scalar_one()

    async def list_skills(self, db: AsyncSession) -> list[AgentSkill]:
        result = await db.execute(
            select(AgentSkill)
            .where(AgentSkill.is_deleted.is_(False))
            .order_by(AgentSkill.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_skills(self, db: AsyncSession) -> list[AgentSkill]:
        result = await db.execute(
            select(AgentSkill)
            .where(
                AgentSkill.is_deleted.is_(False),
                AgentSkill.status == "active",
            )
            .order_by(AgentSkill.name.asc())
        )
        return list(result.scalars().all())

    async def get_skill(
        self, db: AsyncSession, skill_id: uuid.UUID
    ) -> AgentSkill | None:
        result = await db.execute(
            select(AgentSkill).where(
                AgentSkill.id == skill_id,
                AgentSkill.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_skill_by_name(self, db: AsyncSession, name: str) -> AgentSkill | None:
        result = await db.execute(
            select(AgentSkill).where(
                AgentSkill.name == name,
                AgentSkill.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_workflow(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
        name: str,
        description: str | None,
        trigger_phrases: list[str],
        steps: list[dict[str, Any]],
        source_skill: str | None,
        source_request: str | None,
    ) -> AgentWorkflow:
        workflow = AgentWorkflow(
            user_id=user_id,
            session_id=session_id,
            name=name,
            description=description,
            trigger_phrases=trigger_phrases,
            steps=steps,
            source_skill=source_skill,
            source_request=source_request,
        )
        workflow.created_by = user_id
        workflow.updated_by = user_id
        db.add(workflow)
        await db.flush()
        return workflow

    async def list_workflows(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID | None,
    ) -> list[AgentWorkflow]:
        query = select(AgentWorkflow).where(AgentWorkflow.is_deleted.is_(False))
        if user_id is not None:
            query = query.where(AgentWorkflow.user_id == user_id)
        else:
            query = query.where(AgentWorkflow.user_id.is_(None))
        result = await db.execute(query.order_by(AgentWorkflow.created_at.desc()))
        return list(result.scalars().all())

    async def list_legacy_workflows(
        self,
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID | None,
        platform: bool = False,
    ) -> list[AgentWorkflow]:
        query = select(AgentWorkflow).where(AgentWorkflow.is_deleted.is_(False))
        if platform:
            query = query.where(AgentWorkflow.user_id.is_not(None))
        else:
            query = query.where(AgentWorkflow.user_id == owner_user_id)
        result = await db.execute(query.order_by(AgentWorkflow.updated_at.desc()))
        return list(result.scalars().all())

    async def get_legacy_workflow_any(
        self,
        db: AsyncSession,
        workflow_id: uuid.UUID,
    ) -> AgentWorkflow | None:
        result = await db.execute(
            select(AgentWorkflow).where(
                AgentWorkflow.id == workflow_id,
                AgentWorkflow.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_workflow(
        self,
        db: AsyncSession,
        workflow_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None,
    ) -> AgentWorkflow | None:
        query = select(AgentWorkflow).where(
            AgentWorkflow.id == workflow_id,
            AgentWorkflow.is_deleted.is_(False),
        )
        if user_id is not None:
            query = query.where(AgentWorkflow.user_id == user_id)
        else:
            query = query.where(AgentWorkflow.user_id.is_(None))
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create_workflow_run(
        self,
        db: AsyncSession,
        *,
        workflow: AgentWorkflow,
        user_id: uuid.UUID | None,
        session_id: uuid.UUID | None,
    ) -> AgentWorkflowRun:
        run = AgentWorkflowRun(
            workflow_id=workflow.id,
            user_id=user_id,
            session_id=session_id,
            status="running",
            current_step=0,
            steps_snapshot=workflow.steps,
            step_results=[],
            started_at=datetime.now(UTC),
        )
        run.created_by = user_id
        run.updated_by = user_id
        db.add(run)
        await db.flush()
        return run

    async def get_workflow_run(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None,
    ) -> AgentWorkflowRun | None:
        query = select(AgentWorkflowRun).where(
            AgentWorkflowRun.id == run_id,
            AgentWorkflowRun.is_deleted.is_(False),
        )
        if user_id is not None:
            query = query.where(AgentWorkflowRun.user_id == user_id)
        else:
            query = query.where(AgentWorkflowRun.user_id.is_(None))
        result = await db.execute(query)
        return result.scalar_one_or_none()
