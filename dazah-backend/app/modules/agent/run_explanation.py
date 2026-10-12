"""Bounded run diagnostics without task payloads or raw dependency errors."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.identity.models import User

from .automation_service import AgentAutomationService
from .models import (
    AgentConfirmation,
    AgentInteractionRequest,
    AgentPushDelivery,
    AgentToolCall,
)
from .schemas import AgentRunExplanationOut, AgentRunFactOut
from .tools import tool_registry


class AgentRunExplanationService:
    async def explain(
        self, db: AsyncSession, *, user: User, run_id: UUID
    ) -> AgentRunExplanationOut:
        detail = await AgentAutomationService().get_run(db, user=user, run_id=run_id)
        run = detail["run"]
        if run.payload_redacted:
            raise HTTPException(403, "运行诊断仅向任务所有者开放")
        facts = [
            AgentRunFactOut(
                kind="step",
                id=step.id,
                status=step.status,
                step_key=step.step_key,
                operation=step.operation,
                occurred_at=step.started_at,
            )
            for step in detail["steps"]
        ]
        calls = (
            (
                await db.execute(
                    select(AgentToolCall)
                    .where(
                        AgentToolCall.correlation_id == run.correlation_id,
                        AgentToolCall.request_payload["subject"]["user_id"].astext
                        == str(user.id),
                        AgentToolCall.is_deleted.is_(False),
                    )
                    .order_by(AgentToolCall.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        facts.extend(
            AgentRunFactOut(
                kind="tool",
                id=item.id,
                status=item.status,
                operation=item.operation,
                occurred_at=item.created_at,
            )
            for item in calls
        )
        confirmations = (
            (
                await db.execute(
                    select(AgentConfirmation)
                    .where(
                        AgentConfirmation.request_payload["trace_id"].astext
                        == str(run.correlation_id),
                        AgentConfirmation.user_id == user.id,
                        AgentConfirmation.is_deleted.is_(False),
                    )
                    .order_by(AgentConfirmation.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        facts.extend(
            AgentRunFactOut(
                kind="confirmation",
                id=item.id,
                status=item.status,
                operation=item.operation,
                occurred_at=item.created_at,
            )
            for item in confirmations
        )
        interactions = (
            (
                await db.execute(
                    select(AgentInteractionRequest)
                    .where(
                        AgentInteractionRequest.run_id == run_id,
                        AgentInteractionRequest.owner_user_id == user.id,
                        AgentInteractionRequest.is_deleted.is_(False),
                    )
                    .order_by(AgentInteractionRequest.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        facts.extend(
            AgentRunFactOut(
                kind="interaction",
                id=item.id,
                status=item.status,
                step_key=item.step_key,
                occurred_at=item.created_at,
            )
            for item in interactions
        )
        deliveries = (
            (
                await db.execute(
                    select(AgentPushDelivery)
                    .where(
                        AgentPushDelivery.run_id == run_id,
                        AgentPushDelivery.is_deleted.is_(False),
                    )
                    .order_by(AgentPushDelivery.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        facts.extend(
            AgentRunFactOut(
                kind="delivery",
                id=item.id,
                status=item.status,
                occurred_at=item.created_at,
            )
            for item in deliveries
        )
        recovery = "运行完成，可查看步骤和投递状态。"
        if run.status == "failed":
            last = next(
                (
                    step
                    for step in reversed(detail["steps"])
                    if step.status != "succeeded"
                ),
                None,
            )
            spec = (
                tool_registry.get(last.operation) if last and last.operation else None
            )
            recovery = (
                "失败步骤涉及非幂等写入，请人工核对业务结果后重新发起。"
                if spec and spec.write and not spec.idempotent
                else "排除失败原因后，可确认重试原运行；已完成步骤不会从头执行。"
            )
        elif run.status == "skipped_policy":
            recovery = "检查当前角色权限、任务授权、版本及并发策略后重新确认任务。"
        elif run.status == "waiting":
            recovery = "检查待确认项、交互表单或等待条件；完成后由运行器继续执行。"
        elif run.status in {"running", "queued"}:
            recovery = "任务仍在执行或排队，可刷新查看进度；请勿重复发起。"
        return AgentRunExplanationOut(
            run_id=run.id,
            trace_id=run.correlation_id,
            status=run.status,
            error_code=run.error_code,
            recovery=recovery,
            facts=facts,
        )
