"""Change action plan service layer."""

from __future__ import annotations

import ast
import html
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.modules.quality import repository
from app.modules.quality.feishu_notification import (
    send_user_card_with_message_id,
    update_card,
)
from app.modules.quality.models import ChangeActionPlan
from app.modules.quality.schemas.change_action_plan import (
    ChangeActionPlanDetail,
    ChangeActionPlanPersonOption,
    ChangeActionPlanReminderConfirmResult,
    ChangeActionPlanReminderRunResult,
    ChangeActionPlanSyncResult,
    CreateChangeActionPlanRequest,
    UpdateChangeActionPlanRequest,
)
from app.platform.integrations.feishu.bitable import BitableClient, _to_ms_timestamp
from app.platform.integrations.feishu.contact import get_all_users

logger = logging.getLogger(__name__)
settings = get_settings()

_FINISHED_STATUSES = {"已完成", "已关闭", "已确认"}


def _parse_date_value(value: Any) -> date | None:
    if value in (None, "", []):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC).date()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return datetime.fromtimestamp(int(raw) / 1000, tz=UTC).date()
        return date.fromisoformat(raw.replace("/", "-"))
    return None


def _extract_user_info(value: Any) -> tuple[str | None, str | None, str | None]:
    if value in (None, "", []):
        return None, None, None
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return (
                first.get("name") or first.get("en_name") or first.get("display_name"),
                first.get("id")
                or first.get("user_id")
                or first.get("open_id")
                or first.get("union_id"),
                first.get("avatar_url") or None,
            )
        return str(first), None, None
    if isinstance(value, dict):
        return (
            value.get("name") or value.get("display_name"),
            value.get("id") or value.get("user_id") or value.get("open_id"),
            value.get("avatar_url") or None,
        )
    return str(value), None, None


def _normalize_feishu_text(value: Any) -> str | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("[{") or raw.startswith("{"):
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                return raw
            normalized = _normalize_feishu_text(parsed)
            return normalized if normalized not in (None, "") else raw
        return raw
    if isinstance(value, list):
        parts = []
        for item in value:
            normalized = _normalize_feishu_text(item)
            if normalized:
                parts.append(normalized)
        return "".join(parts).strip() or None
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str) and text_value.strip():
            return text_value.strip()
        name_value = (
            value.get("name") or value.get("display_name") or value.get("en_name")
        )
        if isinstance(name_value, str) and name_value.strip():
            return name_value.strip()
        if "link" in value and isinstance(value["link"], str) and value["link"].strip():
            return value["link"].strip()
        return None
    return str(value).strip() or None


async def _resolve_bitable_user_id(
    db: AsyncSession,
    user_id: str | None,
) -> str | None:
    if not user_id:
        return None
    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        return None
    if not normalized_user_id.startswith("ou_"):
        return normalized_user_id

    from app.modules.quality.service.department_contacts import (
        get_department_contact_list_from_feishu,
    )

    contacts = await get_department_contact_list_from_feishu(
        db,
        page=1,
        page_size=1000,
    )
    for contact in contacts.get("items", []):
        if str(contact.get("open_id") or "").strip() == normalized_user_id:
            bitable_user_id = str(contact.get("bitable_user_id") or "").strip()
            if bitable_user_id:
                return bitable_user_id
        if (
            str(contact.get("department_head_open_id") or "").strip()
            == normalized_user_id
        ):
            bitable_user_id = str(
                contact.get("department_head_bitable_user_id") or ""
            ).strip()
            if bitable_user_id:
                return bitable_user_id
    return normalized_user_id


async def _build_user_field(
    db: AsyncSession,
    user_id: str | None,
) -> list[dict[str, str]] | None:
    resolved_user_id = await _resolve_bitable_user_id(db, user_id)
    if not resolved_user_id:
        return None
    return [{"id": resolved_user_id}]


def _normalize_search_value(value: Any) -> str:
    return str(value or "").strip().lower()


def _match_person_score(user: dict[str, Any], keyword: str) -> int | None:
    name = _normalize_search_value(user.get("name"))
    if not name or not user.get("open_id"):
        return None

    if name == keyword:
        return 0
    if name.startswith(keyword):
        return 1
    if keyword in name:
        return 2

    secondary_fields = (
        user.get("mobile"),
        user.get("email"),
        user.get("job_title"),
        user.get("employee_no"),
    )
    if any(keyword in _normalize_search_value(field) for field in secondary_fields):
        return 3

    return None


async def search_change_action_plan_person_options(
    keyword: str,
    limit: int = 20,
) -> list[ChangeActionPlanPersonOption]:
    normalized_keyword = keyword.strip().lower()
    if not normalized_keyword:
        return []

    users = await get_all_users()
    matched_users: list[tuple[int, str, dict[str, Any]]] = []
    seen_open_ids: set[str] = set()

    for user in users:
        open_id = str(user.get("open_id") or "").strip()
        if not open_id or open_id in seen_open_ids:
            continue

        score = _match_person_score(user, normalized_keyword)
        if score is None:
            continue

        seen_open_ids.add(open_id)
        matched_users.append((score, str(user.get("name") or ""), user))

    matched_users.sort(key=lambda item: (item[0], item[1]))
    limited_users = matched_users[:limit]

    return [
        ChangeActionPlanPersonOption(
            open_id=str(user.get("open_id") or ""),
            name=str(user.get("name") or ""),
            user_id=str(user.get("user_id") or "") or None,
            mobile=str(user.get("mobile") or "") or None,
            email=str(user.get("email") or "") or None,
            job_title=str(user.get("job_title") or "") or None,
        )
        for _, _, user in limited_users
    ]


class ChangeActionPlanFeishuSync:
    async def _resolve_runtime(
        self, db: AsyncSession
    ) -> tuple[BitableClient, str] | tuple[None, None]:
        from app.modules.quality.service import (
            quality_feishu_sync as feishu_sync_service,
        )

        runtime = await feishu_sync_service.feishu_sync._resolve_runtime(db)
        entity = runtime.get_entity_config("change_action_plan", direction="push")
        if (
            not runtime.is_enabled()
            or not entity
            or not entity.app_token
            or not entity.table_id
        ):
            return None, None
        return (
            BitableClient(
                app_token=entity.app_token,
                app_id=runtime.app_id,
                app_secret=runtime.app_secret,
            ),
            entity.table_id,
        )

    async def build_fields(
        self,
        db: AsyncSession,
        plan: ChangeActionPlan,
        *,
        include_users: bool = True,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "项目名称": plan.project_name,
            "变更控制号": plan.change_code,
            "涉及工作": plan.related_work or "",
            "状态": plan.status or "",
            "未完成是否延期": plan.delay_flag or "",
        }
        deadline_timestamp = _to_ms_timestamp(plan.deadline_date)
        delayed_deadline_timestamp = _to_ms_timestamp(plan.delayed_deadline_date)
        if deadline_timestamp != "":
            fields["项目截止时间"] = deadline_timestamp
        if delayed_deadline_timestamp != "":
            fields["延期后的日期"] = delayed_deadline_timestamp
        if include_users:
            owner = await _build_user_field(db, plan.owner_user_id)
            director = await _build_user_field(db, plan.director_user_id)
            if owner:
                fields["总负责人"] = owner
            if director:
                fields["部门负责人"] = director
        return fields

    async def search_records(
        self,
        db: AsyncSession,
        change_code: str | None = None,
    ) -> list[dict[str, Any]]:
        client, table_id = await self._resolve_runtime(db)
        if not client or not table_id:
            return []
        filter_str = None
        if change_code:
            filter_str = f'CurrentValue.[变更控制号] = "{change_code}"'
        return await client.search_records(
            table_id,
            filter_str=filter_str,
            page_size=500,
        )

    async def upsert_record(
        self,
        db: AsyncSession,
        plan: ChangeActionPlan,
        *,
        include_users: bool = True,
    ) -> str:
        client, table_id = await self._resolve_runtime(db)
        if not client or not table_id:
            raise RuntimeError("变更计划飞书同步未启用")

        fields = await self.build_fields(db, plan, include_users=include_users)
        if plan.feishu_record_id:
            record = await client.update_record(
                table_id,
                plan.feishu_record_id,
                fields,
            )
            record_id = record.get("record_id")
            return str(record_id) if record_id else plan.feishu_record_id

        record = await client.create_record(table_id, fields)
        record_id = record.get("record_id", "")
        return str(record_id)

    async def delete_record(self, db: AsyncSession, record_id: str) -> None:
        client, table_id = await self._resolve_runtime(db)
        if not client or not table_id or not record_id:
            return
        await client.delete_record(table_id, record_id)


feishu_sync = ChangeActionPlanFeishuSync()


def _should_retry_without_user_fields(exc: Exception) -> bool:
    error_text = str(exc)
    retry_markers = (
        "UserFieldConvFail",
        "1254066",
        "open_id cross app",
        "Person",
    )
    return any(marker in error_text for marker in retry_markers)


def _get_effective_deadline(plan: ChangeActionPlan) -> date | None:
    return plan.delayed_deadline_date or plan.deadline_date


def _is_finished(plan: ChangeActionPlan) -> bool:
    return (plan.status or "").strip() in _FINISHED_STATUSES


def _is_due_for_reminder(plan: ChangeActionPlan, *, today: date) -> bool:
    effective_deadline = _get_effective_deadline(plan)
    if not effective_deadline:
        return False
    return effective_deadline - timedelta(days=3) <= today


def _was_reminded_today(plan: ChangeActionPlan, *, today: date) -> bool:
    if not plan.last_reminded_at:
        return False
    return plan.last_reminded_at.astimezone(UTC).date() == today


def _get_reminder_recipient(plan: ChangeActionPlan) -> tuple[str | None, str | None]:
    if plan.owner_user_id:
        return plan.owner_user_id, plan.owner_name
    if plan.director_user_id:
        return plan.director_user_id, plan.director_name
    return None, None


def _build_reminder_confirm_url(plan_id: uuid.UUID) -> str:
    base_url = settings.FRONTEND_URL.rstrip("/")
    return (
        f"{base_url}/api/v1/quality/change-action-plans/"
        f"{plan_id}/reminders/confirm-page"
    )


def _build_reminder_markdown(plan: ChangeActionPlan) -> str:
    deadline = _get_effective_deadline(plan)
    deadline_text = deadline.isoformat() if deadline else "未设置"
    owner_name = plan.owner_name or "未设置"
    director_name = plan.director_name or "未设置"
    return (
        f"**变更控制号：**{plan.change_code}\n"
        f"**项目名称：**{plan.project_name}\n"
        f"**涉及工作：**{plan.related_work or '（无）'}\n"
        f"**负责人：**{owner_name}\n"
        f"**部门负责人：**{director_name}\n"
        f"**截止日期：**{deadline_text}\n"
        "当前已进入到期前 3 天提醒窗口，请及时处理并确认。"
    )


def _build_reminder_card_payload(
    plan: ChangeActionPlan,
    *,
    confirmed: bool,
    confirmed_by: str | None = None,
) -> dict[str, Any]:
    content = _build_reminder_markdown(plan)
    if confirmed:
        confirmation_text = confirmed_by or "已确认"
        content = f"{content}\n\n**确认状态：**{confirmation_text}"
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "变更计划提醒已确认"},
                "template": "green",
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        }

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "变更计划到期提醒"},
            "template": "orange",
        },
        "elements": [
            {"tag": "markdown", "content": content},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "已确认"},
                        "type": "primary",
                        "url": _build_reminder_confirm_url(plan.id),
                    }
                ],
            },
        ],
    }


async def _send_reminder_card(plan: ChangeActionPlan) -> str | None:
    recipient_open_id, _ = _get_reminder_recipient(plan)
    if not recipient_open_id:
        logger.warning("变更计划 %s 未配置负责人飞书账号，无法发送提醒", plan.id)
        return None

    card = _build_reminder_card_payload(plan, confirmed=False)
    try:
        message_id = await send_user_card_with_message_id(
            recipient_open_id,
            title="变更计划到期提醒",
            content=_build_reminder_markdown(plan),
            elements=card["elements"][1:],
        )
        if not message_id:
            logger.warning("变更计划 %s 飞书提醒发送失败（机器人可能无权限）", plan.id)
            return None
        return message_id
    except Exception as e:
        logger.warning("变更计划 %s 飞书提醒发送异常: %s", plan.id, e)
        return None


async def _patch_confirmation_card(plan: ChangeActionPlan) -> None:
    if not plan.reminder_message_id:
        return
    card = _build_reminder_card_payload(
        plan,
        confirmed=True,
        confirmed_by=plan.reminder_confirmed_by,
    )
    await update_card(plan.reminder_message_id, card)


async def _resolve_change_id(
    db: AsyncSession,
    *,
    change_id: uuid.UUID | None,
    change_code: str | None,
) -> uuid.UUID | None:
    if change_id:
        return change_id
    if not change_code:
        return None
    change = await repository.get_change_by_code(db, change_code)
    return change.id if change else None


def _serialize_plan(plan: ChangeActionPlan) -> dict[str, Any]:
    data = ChangeActionPlanDetail.model_validate(plan).model_dump()
    for field_name in (
        "change_code",
        "project_name",
        "related_work",
        "owner_name",
        "director_name",
        "status",
        "delay_flag",
    ):
        data[field_name] = _normalize_feishu_text(data.get(field_name))
    return data


async def find_due_change_action_plan_reminders(
    db: AsyncSession,
    *,
    today: date | None = None,
) -> list[ChangeActionPlan]:
    today = today or datetime.now(UTC).date()
    items, _ = await repository.get_change_action_plans(
        db,
        page=1,
        page_size=500,
    )
    due_items: list[ChangeActionPlan] = []
    for item in items:
        if not item.reminder_enabled or item.reminder_confirmed_at is not None:
            continue
        if _is_finished(item):
            continue
        if not _is_due_for_reminder(item, today=today):
            continue
        if _was_reminded_today(item, today=today):
            continue
        due_items.append(item)
    return due_items


async def send_change_action_plan_reminder(
    db: AsyncSession,
    plan: ChangeActionPlan,
    *,
    force: bool = False,
) -> str | None:
    today = datetime.now(UTC).date()
    if not plan.reminder_enabled:
        logger.warning("变更计划 %s 未启用提醒", plan.id)
        return None
    if plan.reminder_confirmed_at is not None:
        logger.info("变更计划 %s 已确认，跳过提醒", plan.id)
        return None
    if _is_finished(plan):
        logger.info("变更计划 %s 已完成，跳过提醒", plan.id)
        return None
    if not force and not _is_due_for_reminder(plan, today=today):
        logger.debug("变更计划 %s 尚未进入到期前 3 天提醒窗口", plan.id)
        return None
    if not force and _was_reminded_today(plan, today=today):
        logger.debug("变更计划 %s 今日已发送提醒", plan.id)
        return None

    message_id = await _send_reminder_card(plan)
    if not message_id:
        return None

    await repository.update_change_action_plan(
        db,
        plan,
        {
            "reminder_status": "reminded",
            "last_reminded_at": datetime.now(UTC),
            "reminder_message_id": message_id,
        },
    )
    return message_id


async def run_change_action_plan_reminders(
    db: AsyncSession,
    *,
    today: date | None = None,
) -> ChangeActionPlanReminderRunResult:
    due_items = await find_due_change_action_plan_reminders(db, today=today)
    reminded = 0
    failed = 0

    for item in due_items:
        try:
            await send_change_action_plan_reminder(db, item)
            reminded += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "Failed to send change action plan reminder: plan=%s error=%s",
                item.id,
                exc,
            )

    await db.commit()
    return ChangeActionPlanReminderRunResult(
        scanned=len(due_items),
        reminded=reminded,
        failed=failed,
    )


async def send_change_action_plan_reminder_for_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
) -> dict[str, Any]:
    plan = await repository.get_change_action_plan_by_id(db, plan_id)
    if not plan:
        raise NotFoundException(resource="变更行动计划", resource_id=str(plan_id))

    await send_change_action_plan_reminder(db, plan, force=True)
    await db.commit()
    result = await db.execute(
        select(ChangeActionPlan).where(ChangeActionPlan.id == plan.id)
    )
    plan = result.scalar_one()
    return _serialize_plan(plan)


async def confirm_change_action_plan_reminder(
    db: AsyncSession,
    plan_id: uuid.UUID,
    *,
    confirmed_by: str,
) -> ChangeActionPlanReminderConfirmResult:
    plan = await repository.get_change_action_plan_by_id(db, plan_id)
    if not plan:
        raise NotFoundException(resource="变更行动计划", resource_id=str(plan_id))

    if plan.reminder_confirmed_at is None:
        confirmed_at = datetime.now(UTC)
        await repository.update_change_action_plan(
            db,
            plan,
            {
                "reminder_status": "confirmed",
                "reminder_confirmed_at": confirmed_at,
                "reminder_confirmed_by": confirmed_by,
            },
        )
        await db.commit()
        result = await db.execute(
            select(ChangeActionPlan).where(ChangeActionPlan.id == plan.id)
        )
        plan = result.scalar_one()
        await _patch_confirmation_card(plan)

    return ChangeActionPlanReminderConfirmResult(
        success=True,
        reminder_status=plan.reminder_status,
        reminder_confirmed_at=plan.reminder_confirmed_at,
        reminder_confirmed_by=plan.reminder_confirmed_by,
    )


async def render_change_action_plan_reminder_confirmation_page(
    db: AsyncSession,
    plan_id: uuid.UUID,
    *,
    confirmed_by: str,
) -> str:
    result = await confirm_change_action_plan_reminder(
        db,
        plan_id,
        confirmed_by=confirmed_by,
    )
    confirmed_by_text = html.escape(result.reminder_confirmed_by or confirmed_by)
    confirmed_at_text = (
        result.reminder_confirmed_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        if result.reminder_confirmed_at
        else "-"
    )
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>变更计划提醒确认</title>
    <style>
      body {{
        font-family: Arial, sans-serif;
        background: #f5f7fa;
        margin: 0;
        padding: 40px 16px;
      }}
      .card {{
        max-width: 520px;
        margin: 0 auto;
        background: #fff;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: 24px;
        color: #1677ff;
      }}
      p {{
        margin: 8px 0;
        color: #333;
        line-height: 1.6;
      }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>已确认</h1>
      <p>变更计划提醒已确认，系统将停止后续重复提醒。</p>
      <p><strong>确认人：</strong>{confirmed_by_text}</p>
      <p><strong>确认时间：</strong>{confirmed_at_text}</p>
      <p>当前页面可直接关闭。</p>
    </div>
  </body>
</html>
"""


async def _mark_sync_success(
    db: AsyncSession, plan: ChangeActionPlan, record_id: str | None
) -> None:
    await repository.update_change_action_plan(
        db,
        plan,
        {
            "feishu_record_id": record_id or plan.feishu_record_id,
            "sync_status": "synced",
            "sync_error": None,
            "last_synced_at": datetime.now(UTC),
        },
    )


async def _mark_sync_failed(
    db: AsyncSession, plan: ChangeActionPlan, exc: Exception
) -> None:
    await repository.update_change_action_plan(
        db,
        plan,
        {
            "sync_status": "failed",
            "sync_error": str(exc),
        },
    )


async def _sync_plan_to_feishu(db: AsyncSession, plan: ChangeActionPlan) -> None:
    try:
        record_id = await feishu_sync.upsert_record(db, plan)
        await _mark_sync_success(db, plan, record_id)
    except Exception as exc:  # noqa: BLE001
        if (
            plan.owner_user_id or plan.director_user_id
        ) and _should_retry_without_user_fields(exc):
            logger.warning(
                (
                    "Change action plan sync failed with user"
                    " fields, retrying without users: %s"
                ),
                exc,
            )
            try:
                record_id = await feishu_sync.upsert_record(
                    db,
                    plan,
                    include_users=False,
                )
                await _mark_sync_success(db, plan, record_id)
                return
            except Exception as retry_exc:  # noqa: BLE001
                logger.warning(
                    (
                        "Retrying change action plan sync without"
                        " user fields still failed: %s"
                    ),
                    retry_exc,
                )
                await _mark_sync_failed(db, plan, retry_exc)
                return
        logger.warning("Failed to sync change action plan to Feishu: %s", exc)
        await _mark_sync_failed(db, plan, exc)


async def get_change_action_plan_list(
    db: AsyncSession,
    *,
    change_id: uuid.UUID | None = None,
    change_code: str | None = None,
    project_name: str | None = None,
    related_work: str | None = None,
    owner_name: str | None = None,
    director_name: str | None = None,
    status: str | None = None,
    delay_flag: str | None = None,
    sync_status: str | None = None,
    deadline_date_from: str | None = None,
    deadline_date_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    items, total = await repository.get_change_action_plans(
        db,
        change_id=change_id,
        change_code=change_code,
        project_name=project_name,
        related_work=related_work,
        owner_name=owner_name,
        director_name=director_name,
        status=status,
        delay_flag=delay_flag,
        sync_status=sync_status,
        deadline_date_from=_parse_date_value(deadline_date_from),
        deadline_date_to=_parse_date_value(deadline_date_to),
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_serialize_plan(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_change_action_plans_for_change(
    db: AsyncSession, change_id: uuid.UUID
) -> list[dict[str, Any]]:
    items, _ = await repository.get_change_action_plans(
        db,
        change_id=change_id,
        page=1,
        page_size=200,
    )
    return [_serialize_plan(item) for item in items]


async def create_change_action_plan_record(
    db: AsyncSession,
    data: CreateChangeActionPlanRequest,
    user_id: str,
) -> dict[str, Any]:
    payload = data.model_dump()
    payload["change_id"] = await _resolve_change_id(
        db,
        change_id=data.change_id,
        change_code=data.change_code,
    )
    if user_id != "system":
        payload["created_by"] = uuid.UUID(user_id)
        payload["updated_by"] = uuid.UUID(user_id)
    plan = await repository.create_change_action_plan(db, payload)
    await _sync_plan_to_feishu(db, plan)
    await db.commit()
    result = await db.execute(
        select(ChangeActionPlan).where(ChangeActionPlan.id == plan.id)
    )
    plan = result.scalar_one()
    return _serialize_plan(plan)


async def update_change_action_plan_record(
    db: AsyncSession,
    plan_id: uuid.UUID,
    data: UpdateChangeActionPlanRequest,
    user_id: str,
) -> dict[str, Any]:
    plan = await repository.get_change_action_plan_by_id(db, plan_id)
    if not plan:
        raise NotFoundException(resource="变更行动计划", resource_id=str(plan_id))

    update_data = data.model_dump(exclude_unset=True)
    person_fields = {
        "owner_name",
        "owner_user_id",
        "director_name",
        "director_user_id",
    }
    if person_fields.intersection(update_data) and (
        plan.feishu_record_id or plan.owner_user_id or plan.director_user_id
    ):
        raise ValueError("负责人/部门总监请在飞书多维表中维护")
    target_change_code = update_data.get("change_code", plan.change_code)
    target_change_id = await _resolve_change_id(
        db,
        change_id=update_data.get("change_id"),
        change_code=target_change_code,
    )
    update_data["change_id"] = target_change_id
    if user_id != "system":
        update_data["updated_by"] = uuid.UUID(user_id)
    await repository.update_change_action_plan(db, plan, update_data)
    await _sync_plan_to_feishu(db, plan)
    await db.commit()
    result = await db.execute(
        select(ChangeActionPlan).where(ChangeActionPlan.id == plan.id)
    )
    plan = result.scalar_one()
    return _serialize_plan(plan)


async def delete_change_action_plan_record(
    db: AsyncSession,
    plan_id: uuid.UUID,
) -> dict[str, bool]:
    plan = await repository.get_change_action_plan_by_id(db, plan_id)
    if not plan:
        raise NotFoundException(resource="变更行动计划", resource_id=str(plan_id))

    if plan.feishu_record_id:
        try:
            await feishu_sync.delete_record(db, plan.feishu_record_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete change action plan from Feishu: %s", exc)

    await repository.delete_change_action_plan(db, plan)
    await db.commit()
    return {"success": True}


async def sync_change_action_plan_to_feishu(
    db: AsyncSession,
    plan_id: uuid.UUID,
) -> dict[str, Any]:
    plan = await repository.get_change_action_plan_by_id(db, plan_id)
    if not plan:
        raise NotFoundException(resource="变更行动计划", resource_id=str(plan_id))

    await _sync_plan_to_feishu(db, plan)
    await db.commit()
    result = await db.execute(
        select(ChangeActionPlan).where(ChangeActionPlan.id == plan.id)
    )
    plan = result.scalar_one()
    return _serialize_plan(plan)


async def run_change_action_plan_reminders_now(
    db: AsyncSession,
) -> ChangeActionPlanReminderRunResult:
    return await run_change_action_plan_reminders(db)


async def sync_change_action_plans_from_feishu(
    db: AsyncSession,
    user_id: str,
) -> ChangeActionPlanSyncResult:
    records = await feishu_sync.search_records(db)
    synced = 0
    failed = 0

    for record in records:
        try:
            fields = record.get("fields", {})
            change_code = _normalize_feishu_text(fields.get("变更控制号")) or ""
            project_name = _normalize_feishu_text(fields.get("项目名称")) or ""
            related_work = _normalize_feishu_text(fields.get("涉及工作"))
            if not change_code or not project_name:
                raise AppException(message="飞书记录缺少变更控制号或项目名称")

            owner_name, owner_user_id, owner_avatar_url = _extract_user_info(
                fields.get("总负责人")
            )
            director_value = fields.get("部门负责人")
            if director_value in (None, ""):
                director_value = fields.get("部门总监")
            director_name, director_user_id, director_avatar_url = _extract_user_info(
                director_value
            )
            payload: dict[str, Any] = {
                "change_id": await _resolve_change_id(
                    db, change_id=None, change_code=change_code
                ),
                "change_code": change_code,
                "project_name": project_name,
                "related_work": related_work,
                "owner_name": owner_name,
                "owner_user_id": owner_user_id,
                "owner_avatar_url": owner_avatar_url,
                "director_name": director_name,
                "director_user_id": director_user_id,
                "director_avatar_url": director_avatar_url,
                "deadline_date": _parse_date_value(fields.get("项目截止时间")),
                "status": _normalize_feishu_text(fields.get("状态")),
                "delay_flag": _normalize_feishu_text(fields.get("未完成是否延期")),
                "delayed_deadline_date": _parse_date_value(fields.get("延期后的日期")),
                "feishu_record_id": record.get("record_id"),
                "sync_status": "synced",
                "sync_error": None,
                "last_synced_at": datetime.now(UTC),
            }
            if user_id != "system":
                payload["updated_by"] = uuid.UUID(user_id)

            existing = None
            if record.get("record_id"):
                existing = await repository.get_change_action_plan_by_feishu_record_id(
                    db,
                    record["record_id"],
                )
            if not existing:
                existing = await repository.get_change_action_plan_by_match_fields(
                    db,
                    change_code=change_code,
                    project_name=project_name,
                    related_work=related_work,
                )

            if existing:
                await repository.update_change_action_plan(db, existing, payload)
            else:
                if user_id != "system":
                    payload["created_by"] = uuid.UUID(user_id)
                await repository.create_change_action_plan(db, payload)
            synced += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to sync change action plan from Feishu: %s", exc)
            failed += 1

    await db.commit()
    return ChangeActionPlanSyncResult(synced=synced, failed=failed)
