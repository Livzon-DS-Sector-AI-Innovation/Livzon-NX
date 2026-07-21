from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import redact_sensitive
from app.modules.agent.automation_schema import NotifyStep, RecipientRule
from app.modules.agent.models import (
    AgentAutomation,
    AgentAutomationRun,
    AgentPushDelivery,
    AgentPushTemplateVersion,
    AgentRunEvent,
)
from app.platform.identity.models import Department, FeishuCardAction, User
from app.platform.identity.service import send_livzon_feishu_message


class PushDeliveryService:
    """Creates per-recipient delivery facts and sends through the platform gateway."""

    max_attempts = 3

    async def list_for_user(
        self,
        db: AsyncSession,
        *,
        user: User,
        page: int = 1,
        page_size: int = 20,
        status_value: str | None = None,
    ) -> dict[str, Any]:
        is_admin = user.role == "admin"
        statement = select(AgentPushDelivery).where(
            AgentPushDelivery.is_deleted.is_(False)
        )
        if not is_admin:
            statement = statement.where(AgentPushDelivery.recipient_user_id == user.id)
        if status_value:
            statement = statement.where(AgentPushDelivery.status == status_value)
        statement = statement.order_by(AgentPushDelivery.created_at.desc())
        result = await db.execute(
            statement.offset((page - 1) * page_size).limit(page_size)
        )
        return {
            "items": [
                self.delivery_view(item, is_admin=is_admin) for item in result.scalars()
            ],
            "page": page,
            "page_size": page_size,
        }

    async def get_for_user(
        self, db: AsyncSession, *, user: User, delivery_id: UUID
    ) -> dict[str, Any]:
        delivery = await db.get(AgentPushDelivery, delivery_id)
        if delivery is None or delivery.is_deleted:
            raise ValueError("投递记录不存在")
        is_admin = user.role == "admin"
        if not is_admin and delivery.recipient_user_id != user.id:
            raise PermissionError("无权查看该投递记录")
        return self.delivery_view(delivery, is_admin=is_admin)

    @staticmethod
    def delivery_view(delivery: AgentPushDelivery, *, is_admin: bool) -> dict[str, Any]:
        data = {
            "id": str(delivery.id),
            "automation_id": str(delivery.automation_id),
            "run_id": str(delivery.run_id),
            "channel": delivery.channel,
            "recipient_type": delivery.recipient_type,
            "status": delivery.status,
            "attempt_count": delivery.attempt_count,
            "external_message_id": delivery.external_message_id,
            "card_action_status": delivery.card_action_status,
            "last_error_code": delivery.last_error_code,
            "last_error_message": delivery.last_error_message,
            "sent_at": delivery.sent_at,
            "delivered_at": delivery.delivered_at,
            "created_at": delivery.created_at,
        }
        if is_admin:
            data["recipient_ref"] = {"redacted": True}
            data["content_summary"] = redact_sensitive(delivery.content_summary or {})
        else:
            data["content_summary"] = delivery.content_summary or {}
        return data

    async def claim_due_retries(
        self, db: AsyncSession, *, limit: int = 50
    ) -> list[UUID]:
        now = datetime.now(UTC)
        result = await db.execute(
            select(AgentPushDelivery)
            .where(
                AgentPushDelivery.is_deleted.is_(False),
                AgentPushDelivery.status == "pending",
                AgentPushDelivery.next_attempt_at.is_not(None),
                AgentPushDelivery.next_attempt_at <= now,
            )
            .order_by(AgentPushDelivery.next_attempt_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [item.id for item in result.scalars()]

    async def retry_delivery(self, db: AsyncSession, *, delivery_id: UUID) -> None:
        delivery = await db.get(AgentPushDelivery, delivery_id)
        if delivery is None or delivery.status != "pending":
            return
        template = await db.get(AgentPushTemplateVersion, delivery.template_version_id)
        if template is None:
            delivery.status = "failed"
            delivery.last_error_code = "push.template_missing"
            delivery.last_error_message = "投递模板版本不存在"
            return
        await self._send_snapshot_delivery(db, delivery=delivery, template=template)

    async def reconcile_card_actions(
        self, db: AsyncSession, *, limit: int = 100
    ) -> int:
        """Project authenticated Feishu action facts back into run timelines."""
        result = await db.execute(
            select(AgentPushDelivery)
            .where(
                AgentPushDelivery.is_deleted.is_(False),
                AgentPushDelivery.status == "sent",
                AgentPushDelivery.external_message_id.is_not(None),
                AgentPushDelivery.card_action_status.is_(None),
            )
            .order_by(AgentPushDelivery.sent_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        updated = 0
        for delivery in result.scalars():
            action_result = await db.execute(
                select(FeishuCardAction)
                .where(
                    FeishuCardAction.message_id == delivery.external_message_id,
                    FeishuCardAction.is_deleted.is_(False),
                    FeishuCardAction.status.in_(["processed", "rejected", "expired"]),
                )
                .order_by(FeishuCardAction.executed_at.desc())
                .limit(1)
            )
            action = action_result.scalar_one_or_none()
            if action is None:
                continue
            delivery.card_action_status = action.status
            delivery.status = (
                "interacted" if action.status == "processed" else "expired"
            )
            delivery.delivered_at = action.executed_at or datetime.now(UTC)
            run = await db.get(AgentAutomationRun, delivery.run_id)
            if run is not None:
                await self._event(
                    db,
                    run=run,
                    event_type="push_card_action_reconciled",
                    payload={
                        "delivery_id": str(delivery.id),
                        "action_key": action.action_key,
                        "action_status": action.status,
                    },
                )
            updated += 1
        return updated

    async def dispatch_notify(
        self,
        db: AsyncSession,
        *,
        automation: AgentAutomation,
        run: AgentAutomationRun,
        owner: User,
        step: NotifyStep,
        step_run_id: UUID,
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        template = await self._template(db, template_key=step.template, owner=owner)
        variables = {
            key: _resolve_value(value, outputs) for key, value in step.variables.items()
        }
        variables.setdefault("automation_name", automation.name)
        variables.setdefault("run_id", str(run.id))
        aggregation_key = _resolve_optional_text(step.aggregation_key, outputs)
        incident_key = _resolve_optional_text(step.incident_key, outputs)
        silence_until = _parse_silence_until(step.silence_until)
        recipients = await self._resolve_recipients(
            db, rules=step.recipients, owner=owner, outputs=outputs
        )
        results: list[dict[str, Any]] = []
        for recipient, rule in recipients:
            delivery = await self._get_or_create_delivery(
                db,
                automation=automation,
                run=run,
                step_run_id=step_run_id,
                template=template,
                recipient=recipient,
                rule=rule,
                variables=variables,
                aggregation_key=aggregation_key,
                incident_key=incident_key,
            )
            await self._apply_delivery_policy(
                db,
                delivery=delivery,
                silence_until=silence_until,
                aggregation_window_seconds=step.aggregation_window_seconds,
            )
            if delivery.status in {"pending", "sending"}:
                await self._send_delivery(
                    db, delivery=delivery, template=template, variables=variables
                )
            results.append(
                {
                    "delivery_id": str(delivery.id),
                    "recipient_user_id": str(recipient.id),
                    "status": delivery.status,
                }
            )
        await self._event(
            db,
            run=run,
            event_type="push_dispatch_completed",
            payload={
                "step_key": step.key,
                "template": step.template,
                "delivery_count": len(results),
                "sent_count": sum(item["status"] == "sent" for item in results),
            },
        )
        return {"template": step.template, "deliveries": results}

    async def _template(
        self, db: AsyncSession, *, template_key: str, owner: User
    ) -> AgentPushTemplateVersion:
        result = await db.execute(
            select(AgentPushTemplateVersion)
            .where(
                AgentPushTemplateVersion.template_key == template_key,
                AgentPushTemplateVersion.status == "active",
                AgentPushTemplateVersion.is_deleted.is_(False),
            )
            .order_by(AgentPushTemplateVersion.version.desc())
            .limit(1)
        )
        template = result.scalar_one_or_none()
        if template is not None:
            return template
        template = AgentPushTemplateVersion(
            template_key=template_key,
            version=1,
            title_template="Livzon 自动化通知",
            markdown_template="{{summary}}",
            actions=[],
        )
        template.created_by = owner.id
        template.updated_by = owner.id
        db.add(template)
        await db.flush()
        return template

    async def _resolve_recipients(
        self,
        db: AsyncSession,
        *,
        rules: list[RecipientRule],
        owner: User,
        outputs: dict[str, Any],
    ) -> list[tuple[User, RecipientRule]]:
        resolved: dict[UUID, tuple[User, RecipientRule]] = {}
        for rule in rules:
            user_ids = await self._user_ids_for_rule(db, rule=rule, outputs=outputs)
            for user_id in user_ids:
                user = await db.get(User, user_id)
                if user is not None and user.status == "active" and not user.is_deleted:
                    resolved.setdefault(user.id, (user, rule))
        if not resolved and any(rule.type == "user" for rule in rules):
            # A fixed recipient disappearing is a delivery failure, not a reason
            # to silently fall back to an arbitrary administrator.
            return []
        return list(resolved.values())

    async def _user_ids_for_rule(
        self, db: AsyncSession, *, rule: RecipientRule, outputs: dict[str, Any]
    ) -> list[UUID]:
        if rule.type == "user":
            return _as_uuid_list(rule.user_id)
        if rule.type == "owner_field":
            return _as_uuid_list(_resolve_path(rule.source or "", outputs))
        if rule.type == "department_leader":
            department = await db.get(Department, rule.department_ref)
            if department is None or not department.leader_user_id:
                return []
            result = await db.execute(
                select(User.id).where(
                    User.is_deleted.is_(False),
                    User.status == "active",
                    or_(
                        User.feishu_user_id == department.leader_user_id,
                        User.feishu_open_id == department.leader_user_id,
                    ),
                )
            )
            return list(result.scalars())
        # A role recipient must carry an explicit fixed local-user scope.  This
        # avoids a role rule becoming an unbounded organization broadcast.
        scoped_ids = _as_uuid_list((rule.scope or {}).get("user_ids"))
        if not scoped_ids or not rule.role:
            return []
        result = await db.execute(
            select(User.id).where(
                User.id.in_(scoped_ids),
                User.role == rule.role,
                User.status == "active",
                User.is_deleted.is_(False),
            )
        )
        return list(result.scalars())

    async def _get_or_create_delivery(
        self,
        db: AsyncSession,
        *,
        automation: AgentAutomation,
        run: AgentAutomationRun,
        step_run_id: UUID,
        template: AgentPushTemplateVersion,
        recipient: User,
        rule: RecipientRule,
        variables: dict[str, Any],
        aggregation_key: str | None,
        incident_key: str | None,
    ) -> AgentPushDelivery:
        idempotency_key = (
            f"push:{run.id}:{step_run_id}:{template.id}:{recipient.id}"
        )
        result = await db.execute(
            select(AgentPushDelivery).where(
                AgentPushDelivery.idempotency_key == idempotency_key,
                AgentPushDelivery.is_deleted.is_(False),
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        summary = {
            "title": _render(template.title_template, variables),
            "markdown": _render(template.markdown_template, variables),
        }
        delivery = AgentPushDelivery(
            automation_id=automation.id,
            run_id=run.id,
            step_run_id=step_run_id,
            template_version_id=template.id,
            recipient_type=rule.type,
            recipient_user_id=recipient.id,
            recipient_ref={"user_id": str(recipient.id)},
            template_key=template.template_key,
            template_version=template.version,
            content_summary=redact_sensitive(summary),
            idempotency_key=idempotency_key,
            aggregation_key=aggregation_key,
            incident_key=incident_key,
        )
        delivery.created_by = run.owner_user_id
        delivery.updated_by = run.owner_user_id
        db.add(delivery)
        await db.flush()
        return delivery

    async def _apply_delivery_policy(
        self,
        db: AsyncSession,
        *,
        delivery: AgentPushDelivery,
        silence_until: datetime | None,
        aggregation_window_seconds: int,
    ) -> None:
        """Suppress a durable record instead of dropping a quiet or duplicate alert."""
        if delivery.status != "pending":
            return
        now = datetime.now(UTC)
        if silence_until is not None and now < silence_until:
            delivery.status = "suppressed"
            delivery.last_error_code = "push.silenced"
            delivery.last_error_message = f"静默期至 {silence_until.isoformat()}"
            return
        if not delivery.aggregation_key:
            return
        result = await db.execute(
            select(AgentPushDelivery.id).where(
                AgentPushDelivery.is_deleted.is_(False),
                AgentPushDelivery.id != delivery.id,
                AgentPushDelivery.recipient_user_id == delivery.recipient_user_id,
                AgentPushDelivery.aggregation_key == delivery.aggregation_key,
                AgentPushDelivery.status.in_(["sent", "delivered", "interacted"]),
                AgentPushDelivery.sent_at
                >= now - timedelta(seconds=aggregation_window_seconds),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if result.scalar_one_or_none() is not None:
            delivery.status = "suppressed"
            delivery.last_error_code = "push.aggregated"
            delivery.last_error_message = "同类通知已在聚合窗口内发送"

    async def _send_delivery(
        self,
        db: AsyncSession,
        *,
        delivery: AgentPushDelivery,
        template: AgentPushTemplateVersion,
        variables: dict[str, Any],
    ) -> None:
        delivery.attempt_count += 1
        delivery.status = "sending"
        delivery.next_attempt_at = None
        recovery = await self._has_prior_incident_failure(db, delivery=delivery)
        title = _render(template.title_template, variables)
        markdown = _render(template.markdown_template, variables)
        if recovery:
            title = f"恢复：{title}"[:500]
            markdown = f"此前失败的同类通知现已恢复。\n\n{markdown}"[:8000]
        try:
            result = await send_livzon_feishu_message(
                db,
                user_ids=[delivery.recipient_user_id],
                text=markdown,
                title=title,
                markdown=markdown,
                structured=True,
                requires_business_action=bool(template.actions),
                actions=template.actions,
                business_ref={
                    "agent_push_delivery_id": str(delivery.id),
                    "automation_id": str(delivery.automation_id),
                    "run_id": str(delivery.run_id),
                },
            )
            item = (result.get("results") or [{}])[0]
        except Exception as exc:  # noqa: BLE001
            item = {"status": "failed", "error_message": str(exc)}
        await self._apply_send_result(
            db, delivery=delivery, item=item, recovery=recovery
        )

    async def _send_snapshot_delivery(
        self,
        db: AsyncSession,
        *,
        delivery: AgentPushDelivery,
        template: AgentPushTemplateVersion,
    ) -> None:
        delivery.attempt_count += 1
        delivery.status = "sending"
        delivery.next_attempt_at = None
        summary = dict(delivery.content_summary or {})
        try:
            result = await send_livzon_feishu_message(
                db,
                user_ids=[delivery.recipient_user_id],
                text=str(summary.get("markdown") or ""),
                title=str(summary.get("title") or "Livzon 自动化通知"),
                markdown=str(summary.get("markdown") or ""),
                structured=True,
                requires_business_action=bool(template.actions),
                actions=template.actions,
                business_ref={"agent_push_delivery_id": str(delivery.id)},
            )
            item = (result.get("results") or [{}])[0]
        except Exception as exc:  # noqa: BLE001
            item = {"status": "failed", "error_message": str(exc)}
        await self._apply_send_result(db, delivery=delivery, item=item, recovery=False)

    async def _apply_send_result(
        self,
        db: AsyncSession,
        *,
        delivery: AgentPushDelivery,
        item: dict[str, Any],
        recovery: bool,
    ) -> None:
        message_id = item.get("message_id")
        # A gateway may return a timeout after Feishu has accepted the message.
        # A durable external ID is authoritative and prevents a duplicate retry.
        if message_id:
            delivery.external_message_id = str(message_id)
        if item.get("status") == "sent" or message_id:
            delivery.status = "sent"
            delivery.sent_at = datetime.now(UTC)
            delivery.last_error_code = None
            delivery.last_error_message = None
            run = await db.get(AgentAutomationRun, delivery.run_id)
            if run is not None and message_id and item.get("status") != "sent":
                await self._event(
                    db,
                    run=run,
                    event_type="push_external_message_reconciled",
                    payload={"delivery_id": str(delivery.id)},
                )
            if run is not None and recovery:
                await self._event(
                    db,
                    run=run,
                    event_type="push_recovery_sent",
                    payload={
                        "delivery_id": str(delivery.id),
                        "incident_key": delivery.incident_key,
                    },
                )
            return
        delivery.last_error_code = str(item.get("error_code") or "push.send_failed")
        delivery.last_error_message = str(
            item.get("error_message") or "发送失败"
        )[:2000]
        if delivery.attempt_count < self.max_attempts:
            delivery.status = "pending"
            delivery.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=2**delivery.attempt_count
            )
            return
        delivery.status = "failed"
        run = await db.get(AgentAutomationRun, delivery.run_id)
        if run is not None:
            await self._event(
                db,
                run=run,
                event_type="push_delivery_failed",
                payload={
                    "delivery_id": str(delivery.id),
                    "error_code": delivery.last_error_code,
                    "incident_key": delivery.incident_key,
                },
            )

    async def _has_prior_incident_failure(
        self, db: AsyncSession, *, delivery: AgentPushDelivery
    ) -> bool:
        if not delivery.incident_key:
            return False
        result = await db.execute(
            select(AgentPushDelivery.id).where(
                and_(
                    AgentPushDelivery.is_deleted.is_(False),
                    AgentPushDelivery.id != delivery.id,
                    AgentPushDelivery.recipient_user_id == delivery.recipient_user_id,
                    AgentPushDelivery.incident_key == delivery.incident_key,
                    AgentPushDelivery.status == "failed",
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _event(
        self,
        db: AsyncSession,
        *,
        run: AgentAutomationRun,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        event = AgentRunEvent(
            run_id=run.id,
            event_type=event_type,
            actor_type="service_actor",
            actor_id=run.owner_user_id,
            payload_summary=redact_sensitive(payload),
            occurred_at=datetime.now(UTC),
        )
        event.created_by = run.owner_user_id
        event.updated_by = run.owner_user_id
        db.add(event)


def _resolve_value(value: Any, outputs: dict[str, Any]) -> Any:
    if hasattr(value, "ref"):
        return _resolve_path(str(value.ref), outputs)
    return value


def _resolve_optional_text(value: Any, outputs: dict[str, Any]) -> str | None:
    resolved = _resolve_value(value, outputs)
    if resolved is None:
        return None
    return str(resolved)[:200]


def _parse_silence_until(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _resolve_path(source: str, outputs: dict[str, Any]) -> Any:
    normalized = source.removeprefix("${").removesuffix("}")
    if normalized.startswith("steps."):
        normalized = normalized[len("steps.") :]
    cursor: Any = outputs
    for part in normalized.split("."):
        if not part:
            continue
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _as_uuid_list(value: Any) -> list[UUID]:
    values = value if isinstance(value, list) else [value]
    parsed: list[UUID] = []
    for item in values:
        try:
            parsed.append(UUID(str(item)))
        except (TypeError, ValueError):
            continue
    return parsed


def _render(template: str, variables: dict[str, Any]) -> str:
    values = {
        key: _display(redact_sensitive({key: value}).get(key))
        for key, value in variables.items()
    }
    values.setdefault("summary", json.dumps(values, ensure_ascii=False, sort_keys=True))
    content = template
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    return content[:8000]


def _display(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(redact_sensitive(value), ensure_ascii=False, sort_keys=True)
    return str(value)
