from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
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
    kind = str(schedule.get("kind") or ("cron" if schedule.get("cron") else "")).strip()
    if kind == "once":
        run_at = _aware_datetime(schedule.get("run_at"), field="run_at")
        if run_at <= datetime.now(UTC):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "单次计划时间必须晚于当前时间"
            )
        return {"kind": "once", "run_at": run_at.astimezone(UTC).isoformat()}
    if kind == "interval":
        every = schedule.get("every")
        unit = str(schedule.get("unit") or "").strip()
        if not isinstance(every, int) or isinstance(every, bool) or every < 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "间隔触发必须提供正整数 every"
            )
        if unit not in {"minutes", "hours", "days"}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "间隔触发 unit 仅支持 minutes、hours 或 days",
            )
        seconds = every * {"minutes": 60, "hours": 3600, "days": 86400}[unit]
        if seconds > 31 * 86400:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "间隔触发最长为 31 天")
        anchor_at = _aware_datetime(
            schedule.get("anchor_at") or datetime.now(UTC).isoformat(),
            field="anchor_at",
        )
        return {
            "kind": "interval",
            "every": every,
            "unit": unit,
            "anchor_at": anchor_at.astimezone(UTC).isoformat(),
        }
    if kind not in {"", "cron"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的计划类型")
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
    return {"kind": "cron", "cron": expression}


def next_fire_at(
    *,
    schedule: dict[str, Any],
    timezone: str,
    after: datetime | None = None,
) -> datetime | None:
    kind = str(schedule.get("kind") or ("cron" if schedule.get("cron") else ""))
    cursor = after or datetime.now(UTC)
    if cursor.tzinfo is None:
        cursor = cursor.replace(tzinfo=UTC)
    if kind == "once":
        run_at = _aware_datetime(schedule.get("run_at"), field="run_at")
        return run_at.astimezone(UTC) if run_at > cursor else None
    if kind == "interval":
        anchor = _aware_datetime(schedule.get("anchor_at"), field="anchor_at")
        every = int(schedule.get("every") or 0)
        unit = str(schedule.get("unit") or "")
        seconds = every * {"minutes": 60, "hours": 3600, "days": 86400}.get(unit, 0)
        if seconds <= 0:
            raise ValueError("scheduled interval is invalid")
        elapsed = (cursor - anchor).total_seconds()
        periods = max(1, math.floor(elapsed / seconds) + 1)
        return (anchor + timedelta(seconds=periods * seconds)).astimezone(UTC)
    expression = str(schedule.get("cron") or "").strip()
    if kind != "cron" or not expression:
        raise ValueError("scheduled trigger is missing schedule configuration")
    zone = _zone(timezone)
    local_after = cursor.astimezone(zone)
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
        next_value = next_fire_at(schedule=schedule, timezone=timezone, after=cursor)
        if next_value is None:
            break
        cursor = next_value
        result.append(next_value)
    return result


def _zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的时区") from exc


def _aware_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"计划必须提供 {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"{field} 必须是 ISO-8601 时间"
        ) from exc
    if parsed.tzinfo is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} 必须包含时区")
    return parsed
