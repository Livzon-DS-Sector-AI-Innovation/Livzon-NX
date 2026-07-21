from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter  # type: ignore[import-untyped]
from fastapi import HTTPException, status


def normalize_schedule_config(
    *,
    trigger_type: str,
    schedule: dict[str, Any],
    timezone: str,
) -> dict[str, Any]:
    """Validate and normalize persisted trigger schedule configuration."""
    _zone(timezone)
    if trigger_type != "schedule":
        return {}
    expression = str(schedule.get("cron") or schedule.get("expression") or "").strip()
    if not expression or not croniter.is_valid(expression):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "定时触发必须提供有效的五段 cron 表达式",
        )
    fields = expression.split()
    if len(fields) != 5:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "首期定时触发只支持五段 cron 表达式",
        )
    return {"cron": expression}


def next_fire_at(
    *,
    schedule: dict[str, Any],
    timezone: str,
    after: datetime | None = None,
) -> datetime:
    expression = str(schedule.get("cron") or "").strip()
    if not expression:
        raise ValueError("scheduled trigger is missing cron expression")
    zone = _zone(timezone)
    local_after = (after or datetime.now(UTC)).astimezone(zone)
    next_local = cast(datetime, croniter(expression, local_after).get_next(datetime))
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=zone)
    return next_local.astimezone(UTC)


def preview_next_fires(
    *,
    schedule: dict[str, Any],
    timezone: str,
    count: int,
    after: datetime | None = None,
) -> list[datetime]:
    if count < 1 or count > 20:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "预览次数必须在 1 到 20 之间")
    result: list[datetime] = []
    cursor = after or datetime.now(UTC)
    for _ in range(count):
        cursor = next_fire_at(schedule=schedule, timezone=timezone, after=cursor)
        result.append(cursor)
    return result


def _zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的时区") from exc
