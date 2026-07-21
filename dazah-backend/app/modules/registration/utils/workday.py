"""Workday calculation utilities.

Ported from cde-drug-review-v2 shared/types.ts addWorkDays / ensureWorkday.
Considers weekends, statutory holidays, and makeup workdays (调休补班日).
"""

from datetime import date, timedelta

WEEKDAY_NAMES = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]

# Default holidays (fallback when DB is empty)
DEFAULT_HOLIDAYS: dict[str, list[str]] = {
    "2025": [
        "2025-01-01", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
        "2025-02-01", "2025-02-02", "2025-02-03", "2025-02-04",
        "2025-04-04", "2025-04-05", "2025-04-06",
        "2025-05-01", "2025-05-02", "2025-05-03", "2025-05-04", "2025-05-05",
        "2025-05-31", "2025-06-01", "2025-06-02",
        "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-04", "2025-10-05",
        "2025-10-06", "2025-10-07", "2025-10-08",
    ],
    "2026": [
        "2026-01-01", "2026-01-02", "2026-01-03",
        "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",
        "2026-02-20", "2026-02-21", "2026-02-22", "2026-02-23",
        "2026-04-04", "2026-04-05", "2026-04-06",
        "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
        "2026-06-19", "2026-06-20", "2026-06-21",
        "2026-09-25", "2026-09-26", "2026-09-27",
        "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05",
        "2026-10-06", "2026-10-07",
    ],
    "2027": [
        "2027-01-01",
        "2027-02-06", "2027-02-07", "2027-02-08", "2027-02-09",
        "2027-02-10", "2027-02-11", "2027-02-12", "2027-02-13",
        "2027-04-03", "2027-04-04", "2027-04-05",
        "2027-05-01", "2027-05-02", "2027-05-03", "2027-05-04", "2027-05-05",
        "2027-06-09", "2027-06-10", "2027-06-11",
        "2027-10-01", "2027-10-02", "2027-10-03", "2027-10-04", "2027-10-05",
        "2027-10-06", "2027-10-07", "2027-10-08",
    ],
}

DEFAULT_WORKDAYS: dict[str, list[str]] = {
    "2025": ["2025-01-26", "2025-02-08", "2025-04-27", "2025-09-28", "2025-10-11"],
    "2026": ["2026-01-04", "2026-02-14", "2026-02-28", "2026-05-09", "2026-09-20", "2026-10-10"],
    "2027": ["2027-02-20", "2027-02-27", "2027-04-24", "2027-09-26", "2027-10-09"],
}


def add_workdays(
    start_date: date,
    days: int,
    holidays: list[str] | None = None,
    workdays: list[str] | None = None,
) -> date:
    """Add workdays to a start date, skipping weekends and holidays.

    Args:
        start_date: The starting date.
        days: Number of workdays to add.
        holidays: List of holiday date strings (YYYY-MM-DD).
        workdays: List of makeup workday strings (YYYY-MM-DD), which are weekends
                  but count as workdays due to holiday swaps (调休补班日).

    Returns:
        The resulting date after adding the specified workdays.
    """
    holidays = holidays or []
    workdays = workdays or []

    current = start_date
    remaining = days
    iterations = 0

    while remaining > 0:
        current += timedelta(days=1)
        date_str = current.isoformat()
        weekday = current.weekday()  # Monday=0, Sunday=6

        # Check if it's a makeup workday (counts as workday even on weekend)
        if date_str in workdays:
            remaining -= 1
            continue

        # Check if it's a weekend
        if weekday >= 5:  # Saturday=5, Sunday=6
            continue

        # Check if it's a statutory holiday
        if date_str in holidays:
            continue

        remaining -= 1

        # Safety: prevent infinite loop
        iterations += 1
        if iterations > 365 * 3:
            break

    return current


def ensure_workday(
    target: date,
    holidays: list[str] | None = None,
    workdays: list[str] | None = None,
) -> date:
    """Ensure a date is a workday; if not, advance to the next workday.

    Args:
        target: The target date to check.
        holidays: List of holiday date strings.
        workdays: List of makeup workday strings.

    Returns:
        A workday date (may be the same as target if already a workday).
    """
    holidays = holidays or []
    workdays = workdays or []

    current = target
    for _ in range(10):
        date_str = current.isoformat()
        weekday = current.weekday()

        # Makeup workday → always counts as workday
        if date_str in workdays:
            return current

        # Weekend → skip to Monday
        if weekday >= 5:
            days_to_add = 2 if weekday == 5 else 1  # Sat→+2, Sun→+1
            current += timedelta(days=days_to_add)
            continue

        # Statutory holiday → skip one day
        if date_str in holidays:
            current += timedelta(days=1)
            continue

        # Already a workday
        return current

    return target
