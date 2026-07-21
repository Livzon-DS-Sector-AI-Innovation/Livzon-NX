from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import AgentAutomationRun, AgentRunEvent, AgentStepRun
from app.platform.identity.models import User


class AgentManualTaskService:
    async def complete(
        self, db: AsyncSession, *, user: User, run_id: UUID
    ) -> dict[str, Any]:
        run = await db.get(AgentAutomationRun, run_id)
        if run is None or run.is_deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "人工待办不存在")
        if user.role != "admin" and run.owner_user_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权完成该人工待办")
        result = await db.execute(
            select(AgentStepRun)
            .where(
                AgentStepRun.run_id == run.id,
                AgentStepRun.status == "waiting_manual",
            )
            .order_by(AgentStepRun.created_at.asc())
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "没有待完成的人工待办")
        task.status = "succeeded"
        task.output_summary = {"status": "completed", "completed_by": str(user.id)}
        task.finished_at = datetime.now(UTC)
        run.status = "queued"
        run.retry_at = datetime.now(UTC)
        event = AgentRunEvent(
            run_id=run.id,
            event_type="manual_task_completed",
            actor_type="user",
            actor_id=user.id,
            payload_summary={"step_key": task.step_key},
            occurred_at=datetime.now(UTC),
        )
        event.created_by = user.id
        event.updated_by = user.id
        db.add(event)
        return {"run_id": str(run.id), "step_key": task.step_key, "status": "queued"}
