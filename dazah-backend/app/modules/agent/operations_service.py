from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentPushDelivery,
)
from app.platform.identity.models import User

AUTOMATION_TEMPLATES = [
    {
        "key": "daily_exception_digest_v1",
        "title": "每日异常摘要",
        "description": "按计划聚合只读检查结果，并向任务所有者发送摘要。",
        "subflows": ["collect_readonly_checks", "render_digest", "notify_owner"],
        "requires_confirmation": True,
    },
    {
        "key": "purchase_arrival_inbound_v1",
        "title": "采购到货—仓储入库待办",
        "description": "接收采购到货事件后创建仓储人工待办，确认后继续后续步骤。",
        "subflows": ["wait_purchase_arrival", "create_inbound_manual_task"],
        "requires_confirmation": True,
    },
]


class AgentOperationsService:
    window_days = 30

    async def health(self, db: AsyncSession, *, user: User) -> list[dict[str, Any]]:
        automations = await self._automations(db, user=user)
        cutoff = datetime.now(UTC) - timedelta(days=self.window_days)
        runs = await self._runs(
            db, automation_ids=[item.id for item in automations], cutoff=cutoff
        )
        grouped: dict[Any, list[AgentAutomationRun]] = defaultdict(list)
        for run in runs:
            grouped[run.automation_id].append(run)
        result: list[dict[str, Any]] = []
        for automation in automations:
            records = grouped[automation.id]
            failures = sum(item.status == "failed" for item in records)
            waiting = sum(item.status == "waiting" for item in records)
            total = len(records)
            score = 100
            if total == 0:
                score -= 35
            elif failures:
                score -= round(failures / total * 60)
            score -= min(waiting * 10, 20)
            if automation.status in {"quarantined", "suspended_policy"}:
                score = min(score, 20)
            reasons = []
            if total == 0:
                reasons.append("30 天内没有运行证据")
            if failures:
                reasons.append(f"{failures}/{total} 次运行失败")
            if waiting:
                reasons.append(f"{waiting} 个运行等待外部事件或人工待办")
            result.append(
                {
                    "automation_id": str(automation.id),
                    "name": automation.name,
                    "status": automation.status,
                    "health_score": max(score, 0),
                    "run_count": total,
                    "failure_count": failures,
                    "waiting_count": waiting,
                    "invalid": total == 0
                    or automation.status in {"quarantined", "suspended_policy"},
                    "evidence": reasons or ["运行稳定"],
                }
            )
        return sorted(result, key=lambda item: item["health_score"])

    async def trends(self, db: AsyncSession, *, user: User) -> dict[str, Any]:
        automations = await self._automations(db, user=user)
        ids = [item.id for item in automations]
        cutoff = datetime.now(UTC) - timedelta(days=self.window_days)
        runs = await self._runs(db, automation_ids=ids, cutoff=cutoff)
        deliveries = await self._deliveries(db, automation_ids=ids, cutoff=cutoff)
        run_days: dict[str, Counter[str]] = defaultdict(Counter)
        for run in runs:
            run_days[run.created_at.date().isoformat()][run.status] += 1
        delivery_statuses = Counter(item.status for item in deliveries)
        return {
            "window_days": self.window_days,
            "run_status_by_day": [
                {"date": day, **dict(statuses)}
                for day, statuses in sorted(run_days.items())
            ],
            "delivery_statuses": dict(delivery_statuses),
            "failure_count": sum(item.status == "failed" for item in runs),
            "waiting_count": sum(item.status == "waiting" for item in runs),
            "duplicate_suppressed_count": sum(
                item.status == "suppressed" for item in deliveries
            ),
        }

    async def suggestions(
        self, db: AsyncSession, *, user: User
    ) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for item in await self.health(db, user=user):
            if item["failure_count"]:
                suggestions.append(
                    {
                        "automation_id": item["automation_id"],
                        "kind": "failure_review",
                        "message": (
                            "建议检查失败步骤、权限范围，"
                            "或将不稳定操作改为人工待办。"
                        ),
                        "evidence": item["evidence"],
                        "requires_owner_confirmation": True,
                    }
                )
            elif item["invalid"]:
                suggestions.append(
                    {
                        "automation_id": item["automation_id"],
                        "kind": "retire_or_test",
                        "message": "建议先模拟运行；无业务价值时由所有者归档。",
                        "evidence": item["evidence"],
                        "requires_owner_confirmation": True,
                    }
                )
        return suggestions

    async def admin_report(self, db: AsyncSession, *, user: User) -> dict[str, Any]:
        if user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
        health = await self.health(db, user=user)
        trends = await self.trends(db, user=user)
        unhealthy = [item for item in health if item["health_score"] < 70]
        return {
            "summary": (
                f"近 {self.window_days} 天共观察 {len(health)} 个自动化，"
                f"失败运行 {trends['failure_count']} 次，"
                f"待处理运行 {trends['waiting_count']} 个，"
                f"低健康度任务 {len(unhealthy)} 个。"
            ),
            "health": health,
            "trends": trends,
            "suggestions": await self.suggestions(db, user=user),
        }

    @staticmethod
    def templates() -> list[dict[str, Any]]:
        return AUTOMATION_TEMPLATES

    async def _automations(
        self, db: AsyncSession, *, user: User
    ) -> list[AgentAutomation]:
        statement = select(AgentAutomation).where(AgentAutomation.is_deleted.is_(False))
        if user.role != "admin":
            statement = statement.where(AgentAutomation.owner_user_id == user.id)
        result = await db.execute(statement)
        return list(result.scalars())

    async def _runs(
        self, db: AsyncSession, *, automation_ids: list[Any], cutoff: datetime
    ) -> list[AgentAutomationRun]:
        if not automation_ids:
            return []
        result = await db.execute(
            select(AgentAutomationRun).where(
                AgentAutomationRun.automation_id.in_(automation_ids),
                AgentAutomationRun.is_deleted.is_(False),
                AgentAutomationRun.created_at >= cutoff,
            )
        )
        return list(result.scalars())

    async def _deliveries(
        self, db: AsyncSession, *, automation_ids: list[Any], cutoff: datetime
    ) -> list[AgentPushDelivery]:
        if not automation_ids:
            return []
        result = await db.execute(
            select(AgentPushDelivery).where(
                AgentPushDelivery.automation_id.in_(automation_ids),
                AgentPushDelivery.is_deleted.is_(False),
                AgentPushDelivery.created_at >= cutoff,
            )
        )
        return list(result.scalars())
