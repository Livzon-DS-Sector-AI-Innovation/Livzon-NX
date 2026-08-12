from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redaction import redact_sensitive
from app.modules.agent.interaction_schemas import (
    FeishuResourceTemplateCreate,
    FeishuResourceTemplateOut,
    InteractionArtifact,
    InteractionRequestCreate,
    InteractionRequestPage,
    InteractionSubmissionCreate,
)
from app.modules.agent.models import (
    AgentAutomationRun,
    AgentFeishuResourceTemplate,
    AgentInteractionRequest,
    AgentInteractionSubmission,
)
from app.platform.identity.models import User


class AgentInteractionService:
    async def create_template(
        self,
        db: AsyncSession,
        *,
        user: User,
        request: FeishuResourceTemplateCreate,
    ) -> FeishuResourceTemplateOut:
        template = AgentFeishuResourceTemplate(
            owner_user_id=user.id,
            name=request.name,
            resource_type=request.resource_type,
            resource_url=request.resource_url,
            resource_ref={
                "base_token": request.base_token,
                "table_id": request.table_id,
                "view_id": request.view_id,
                "sheet_range": request.sheet_range,
            },
            view_type=request.view_type,
            field_schema=[
                item.model_dump(mode="json") for item in request.field_schema
            ],
            writable_fields=sorted(set(request.writable_fields)),
            record_mode=request.record_mode,
            status="pending",
        )
        template.created_by = user.id
        template.updated_by = user.id
        db.add(template)
        await db.flush()
        return self.template_out(template)

    async def list_templates(
        self, db: AsyncSession, *, user: User
    ) -> list[FeishuResourceTemplateOut]:
        statement = select(AgentFeishuResourceTemplate).where(
            AgentFeishuResourceTemplate.is_deleted.is_(False)
        )
        if user.role != "admin":
            statement = statement.where(
                or_(
                    AgentFeishuResourceTemplate.owner_user_id.is_(None),
                    AgentFeishuResourceTemplate.owner_user_id == user.id,
                )
            )
        result = await db.execute(
            statement.order_by(AgentFeishuResourceTemplate.updated_at.desc())
        )
        return [self.template_out(item) for item in result.scalars()]

    async def validate_template(
        self,
        db: AsyncSession,
        *,
        user: User,
        template_id: uuid.UUID,
    ) -> FeishuResourceTemplateOut:
        template = await self._template(db, user=user, template_id=template_id)
        ref = template.resource_ref
        payload = await self._hermes_request(
            (
                "/internal/automation/sheet/read"
                if template.resource_type == "sheet"
                else "/internal/automation/bitable/inspect"
            ),
            {
                "base_token": ref.get("base_token"),
                "table_id": ref.get("table_id"),
                **(
                    {"range": ref.get("sheet_range")}
                    if template.resource_type == "sheet"
                    else {}
                ),
            },
        )
        field_names = (
            set(template.writable_fields)
            if template.resource_type == "sheet" and payload.get("cells") is not None
            else _field_names(payload.get("fields"))
        )
        missing = sorted(set(template.writable_fields) - field_names)
        if missing:
            template.status = "invalid"
            template.validation_summary = {"missing_fields": missing}
        else:
            template.status = "active"
            template.validation_summary = {
                "field_count": len(field_names),
                "writable_field_count": len(template.writable_fields),
            }
        template.validated_at = datetime.now(UTC)
        template.updated_by = user.id
        await db.flush()
        await db.refresh(template)
        return self.template_out(template)

    async def create_request(
        self,
        db: AsyncSession,
        *,
        user: User,
        request: InteractionRequestCreate,
        trusted_automation: bool = False,
    ) -> InteractionArtifact:
        if (
            request.recipient_user_id != user.id
            and user.role != "admin"
            and not trusted_automation
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "只能为本人创建填写请求",
            )
        recipient = await db.get(User, request.recipient_user_id)
        if recipient is None or recipient.is_deleted or recipient.status != "active":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "收件人不可用")
        template = await self._template(db, user=user, template_id=request.template_id)
        if template.status != "active":
            raise HTTPException(status.HTTP_409_CONFLICT, "飞书资源模板尚未验证通过")
        if template.resource_type == "sheet" and request.mode != "table_link":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "电子表格模板首版仅支持 table_link 范围回读",
            )
        existing = await db.execute(
            select(AgentInteractionRequest).where(
                AgentInteractionRequest.idempotency_key == request.idempotency_key,
                AgentInteractionRequest.is_deleted.is_(False),
            )
        )
        item = existing.scalar_one_or_none()
        if item is None:
            item = AgentInteractionRequest(
                automation_id=request.automation_id,
                run_id=request.run_id,
                step_key=request.step_key,
                owner_user_id=user.id,
                recipient_user_id=request.recipient_user_id,
                template_id=template.id,
                mode=request.mode,
                status="pending",
                version=1,
                title=request.title,
                summary=request.summary,
                form_schema=[
                    field.model_dump(mode="json") for field in request.form_schema
                ],
                prefill=redact_sensitive(request.prefill),
                idempotency_key=request.idempotency_key,
                expires_at=request.expires_at,
                result_summary={"table_resource_url": template.resource_url},
            )
            item.created_by = user.id
            item.updated_by = user.id
            try:
                async with db.begin_nested():
                    db.add(item)
                    await db.flush()
            except IntegrityError:
                raced = await db.execute(
                    select(AgentInteractionRequest).where(
                        AgentInteractionRequest.idempotency_key
                        == request.idempotency_key,
                        AgentInteractionRequest.is_deleted.is_(False),
                    )
                )
                item = raced.scalar_one()
        return self.artifact(item, template)

    async def list_requests(
        self,
        db: AsyncSession,
        *,
        user: User,
        page: int,
        page_size: int,
    ) -> InteractionRequestPage:
        filters = [AgentInteractionRequest.is_deleted.is_(False)]
        if user.role != "admin":
            filters.append(AgentInteractionRequest.recipient_user_id == user.id)
        total = await db.scalar(
            select(func.count()).select_from(AgentInteractionRequest).where(*filters)
        )
        result = await db.execute(
            select(AgentInteractionRequest, AgentFeishuResourceTemplate)
            .join(
                AgentFeishuResourceTemplate,
                AgentFeishuResourceTemplate.id == AgentInteractionRequest.template_id,
            )
            .where(*filters)
            .order_by(AgentInteractionRequest.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return InteractionRequestPage(
            items=[self.artifact(item, template) for item, template in result.tuples()],
            page=page,
            page_size=page_size,
            total=int(total or 0),
        )

    async def get_request(
        self,
        db: AsyncSession,
        *,
        user: User,
        request_id: uuid.UUID,
    ) -> InteractionArtifact:
        item, template = await self._request(db, user=user, request_id=request_id)
        return self.artifact(item, template)

    async def submit(
        self,
        db: AsyncSession,
        *,
        user: User,
        request_id: uuid.UUID,
        request: InteractionSubmissionCreate,
    ) -> InteractionArtifact:
        item, template = await self._request(db, user=user, request_id=request_id)
        if item.status == "completed":
            return self.artifact(item, template)
        if item.status != "pending":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "填写请求当前不可重试，请先通过失败诊断修复或创建新请求",
            )
        if datetime.now(UTC) >= item.expires_at:
            item.status = "expired"
            raise HTTPException(status.HTTP_409_CONFLICT, "填写请求已过期")
        if request.request_version != item.version:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "填写请求版本已变化，请刷新后重试"
            )
        existing = await db.execute(
            select(AgentInteractionSubmission).where(
                AgentInteractionSubmission.request_id == item.id,
                AgentInteractionSubmission.idempotency_key == request.idempotency_key,
                AgentInteractionSubmission.is_deleted.is_(False),
            )
        )
        submission = existing.scalar_one_or_none()
        if submission is not None:
            return self.artifact(item, template)
        values = (
            _validate_values(
                request.values,
                item.form_schema,
                writable_fields=set(template.writable_fields),
            )
            if item.mode == "card_form"
            else {}
        )
        submission = AgentInteractionSubmission(
            request_id=item.id,
            request_version=item.version,
            submitted_by=user.id,
            idempotency_key=request.idempotency_key,
            values=redact_sensitive(values),
            status="processing",
        )
        submission.created_by = user.id
        submission.updated_by = user.id
        try:
            async with db.begin_nested():
                db.add(submission)
                await db.flush()
        except IntegrityError:
            return self.artifact(item, template)
        ref = template.resource_ref
        try:
            receipt = await self._hermes_request(
                (
                    "/internal/automation/bitable/records"
                    if item.mode == "card_form"
                    else (
                        "/internal/automation/sheet/read"
                        if template.resource_type == "sheet"
                        else "/internal/automation/bitable/read"
                    )
                ),
                (
                    {
                        "run_id": str(item.run_id or item.id),
                        "step_key": item.step_key or "interactive_collection",
                        "user_id": str(user.id),
                        "resource_url": template.resource_url,
                        "base_token": ref.get("base_token"),
                        "table_id": ref.get("table_id"),
                        "fields": values,
                    }
                    if item.mode == "card_form"
                    else {
                        "base_token": ref.get("base_token"),
                        "table_id": ref.get("table_id"),
                        **(
                            {"range": ref.get("sheet_range")}
                            if template.resource_type == "sheet"
                            else {}
                        ),
                    }
                ),
            )
            if item.mode == "table_link":
                required_fields = [
                    str(field.get("key"))
                    for field in item.form_schema
                    if field.get("required")
                ]
                verified = (
                    _has_sheet_values(receipt.get("cells"))
                    if template.resource_type == "sheet"
                    else _has_complete_record(receipt.get("records"), required_fields)
                )
                if not verified:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        "目标表尚未找到关键字段完整的记录，请填写后重试",
                    )
        except HTTPException as exc:
            if exc.status_code == status.HTTP_409_CONFLICT:
                raise
            submission.status = "failed"
            submission.error_code = "interaction.table_write_failed"
            submission.error_message = str(exc.detail)[:1000]
            item.status = "failed"
            await db.flush()
            raise
        submission.status = "succeeded"
        submission.write_receipt = redact_sensitive(receipt)
        item.status = "completed"
        item.completed_at = datetime.now(UTC)
        item.result_summary = {
            "submission_id": str(submission.id),
            "written": item.mode == "card_form",
            "verified": item.mode == "table_link",
        }
        if item.run_id is not None:
            run = await db.get(AgentAutomationRun, item.run_id)
            if run is not None and run.status == "waiting":
                run.status = "queued"
                run.retry_at = datetime.now(UTC)
                run.resume_at = None
        await db.flush()
        return self.artifact(item, template)

    async def _template(
        self, db: AsyncSession, *, user: User, template_id: uuid.UUID
    ) -> AgentFeishuResourceTemplate:
        template = await db.get(AgentFeishuResourceTemplate, template_id)
        if (
            template is None
            or template.is_deleted
            or (user.role != "admin" and template.owner_user_id not in {None, user.id})
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "飞书资源模板不存在")
        return template

    async def _request(
        self, db: AsyncSession, *, user: User, request_id: uuid.UUID
    ) -> tuple[AgentInteractionRequest, AgentFeishuResourceTemplate]:
        result = await db.execute(
            select(AgentInteractionRequest, AgentFeishuResourceTemplate)
            .join(
                AgentFeishuResourceTemplate,
                AgentFeishuResourceTemplate.id == AgentInteractionRequest.template_id,
            )
            .where(
                AgentInteractionRequest.id == request_id,
                AgentInteractionRequest.is_deleted.is_(False),
            )
        )
        row = result.one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "填写请求不存在")
        item, template = row
        if user.role != "admin" and item.recipient_user_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "无权访问该填写请求")
        return item, template

    @staticmethod
    async def _hermes_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        base_url = settings.HERMES_INTERNAL_URL.rstrip("/")
        if not base_url:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Hermes内部接口未配置"
            )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{base_url}{path}",
                    headers={
                        "Authorization": f"Bearer {settings.HERMES_INTERNAL_TOKEN}"
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status.HTTP_504_GATEWAY_TIMEOUT, "Hermes请求超时"
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Hermes连接失败") from exc
        if response.status_code >= 400:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"Hermes返回错误 {response.status_code}",
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "Hermes响应不是有效JSON"
            ) from exc
        if not isinstance(data, dict):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Hermes响应无效")
        return data

    @staticmethod
    def template_out(
        template: AgentFeishuResourceTemplate,
    ) -> FeishuResourceTemplateOut:
        return FeishuResourceTemplateOut(
            id=template.id,
            owner_user_id=template.owner_user_id,
            name=template.name,
            resource_type=template.resource_type,
            resource_url=template.resource_url,
            view_id=template.resource_ref.get("view_id"),
            view_type=template.view_type,
            field_schema=template.field_schema,
            writable_fields=template.writable_fields,
            record_mode=template.record_mode,
            status=template.status,
            validation_summary=redact_sensitive(template.validation_summary),
            validated_at=template.validated_at,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )

    @staticmethod
    def artifact(
        item: AgentInteractionRequest, template: AgentFeishuResourceTemplate
    ) -> InteractionArtifact:
        return InteractionArtifact(
            type="form" if item.mode == "card_form" else "table_link",
            request_id=item.id,
            version=item.version,
            title=item.title,
            summary=item.summary,
            status=item.status,
            actions=[
                {
                    "type": "open_url",
                    "label": "打开飞书表格"
                    if item.mode == "table_link"
                    else "查看目标表",
                    "url": template.resource_url,
                }
            ],
            form_schema=item.form_schema,
            table_resource={
                "template_id": str(template.id),
                "name": template.name,
                "resource_type": template.resource_type,
                "url": template.resource_url,
                "view_type": template.view_type,
            },
            expires_at=item.expires_at,
            automation_id=item.automation_id,
            run_id=item.run_id,
        )


def _field_names(payload: Any) -> set[str]:
    if isinstance(payload, dict):
        candidates = payload.get("items") or payload.get("fields") or []
    else:
        candidates = payload
    if not isinstance(candidates, list):
        return set()
    return {
        str(item.get("field_name") or item.get("name"))
        for item in candidates
        if isinstance(item, dict) and (item.get("field_name") or item.get("name"))
    }


def _has_complete_record(payload: Any, required_fields: list[str]) -> bool:
    if isinstance(payload, dict):
        candidates = payload.get("items") or payload.get("records") or []
    else:
        candidates = payload
    if not isinstance(candidates, list):
        return False
    for record in candidates:
        if not isinstance(record, dict):
            continue
        fields = (
            record.get("fields")
            if isinstance(record.get("fields"), dict)
            else record
        )
        if all(
            fields.get(key) is not None
            and fields.get(key) != ""
            and fields.get(key) != ()
            and fields.get(key) != []
            for key in required_fields
        ):
            return True
    return False


def _has_sheet_values(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key in ("values", "cells", "data", "valueRange"):
            if key in payload and _has_sheet_values(payload[key]):
                return True
        return False
    if isinstance(payload, list):
        return any(_has_sheet_values(item) for item in payload)
    return payload is not None and payload != ""


def _validate_values(
    values: dict[str, Any],
    schema: list[dict[str, Any]],
    *,
    writable_fields: set[str],
) -> dict[str, Any]:
    fields = {str(item.get("key")): item for item in schema}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"未知字段: {', '.join(unknown)}"
        )
    result: dict[str, Any] = {}
    for key, field in fields.items():
        value = values.get(key)
        if field.get("required") and (
            value is None or value == "" or value == () or value == []
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{field.get('label') or key}为必填项",
            )
        if value is None:
            continue
        expected = field.get("type")
        if expected == "number" and isinstance(value, str):
            try:
                value = float(value) if "." in value else int(value)
            except ValueError:
                pass
        if expected == "boolean" and isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"是", "true", "1", "yes"}:
                value = True
            elif normalized in {"否", "false", "0", "no"}:
                value = False
        if expected == "date" and isinstance(value, str):
            try:
                local_date = date.fromisoformat(value)
                value = int(
                    datetime.combine(
                        local_date,
                        time.min,
                        tzinfo=ZoneInfo("Asia/Shanghai"),
                    ).timestamp()
                    * 1000
                )
            except ValueError:
                pass
        if expected == "number" and (
            not isinstance(value, int | float) or isinstance(value, bool)
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}必须是数字"
            )
        if expected == "boolean" and not isinstance(value, bool):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}必须是布尔值"
            )
        if expected == "date" and not isinstance(value, int):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}必须是有效日期"
            )
        if expected in {"text", "single_select"} and not isinstance(value, str):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}必须是文本"
            )
        if expected == "multi_select" and not isinstance(value, list):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}必须是数组"
            )
        options = field.get("options") or []
        selected = value if isinstance(value, list) else [value]
        if expected in {"single_select", "multi_select"} and any(
            item not in options for item in selected
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key}包含未声明选项"
            )
        if key not in writable_fields:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"字段 {key} 不在模板可写范围"
            )
        result[key] = value
    return result
