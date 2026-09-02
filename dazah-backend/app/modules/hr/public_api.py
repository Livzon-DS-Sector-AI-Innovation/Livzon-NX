"""HR module public API for cross-module consumption."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.repository import EmployeeRepository

# Valid filter keys accepted by EmployeeRepository.list_employees / _apply_filters
_VALID_FILTER_KEYS = {
    "department",
    "status",
    "keyword",
    "team",
    "position",
    "job_category",
    "level",
    "gender",
    "education",
    "political_status",
    "marital_status",
    "status_category",
    "age_min",
    "age_max",
    "birth_year_min",
    "birth_year_max",
    "hire_date_after",
    "hire_date_before",
    "factory_entry_date_after",
    "factory_entry_date_before",
    "work_start_date_after",
    "work_start_date_before",
}


# 公共 API 允许的聚合/去重字段白名单（禁止对敏感列如
# id_card/phone/bank_account 做聚合泄露）
_ALLOWED_AGG_FIELDS = frozenset(
    {
        "department",
        "education",
        "position",
        "gender",
        "status",
        "employee_type",
        "sub_department",
        "level",
        "job_title",
    }
)


def _assert_field_allowed(field: str, kind: str = "field") -> None:
    if field not in _ALLOWED_AGG_FIELDS:
        raise ValueError(f"{kind} '{field}' 不在允许的字段列表中")


def _normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw filter dict for EmployeeRepository queries.

    - Maps ``name`` → ``keyword`` (LLM planners often emit ``name``).
    - Drops any keys not recognised by the repository.
    """
    normalized: dict[str, Any] = {}
    for key, value in filters.items():
        if key == "name" and value:
            normalized["keyword"] = value
        elif key in _VALID_FILTER_KEYS and value is not None:
            normalized[key] = value
    return normalized


def _employee_to_dict(emp: Any) -> dict[str, str | None]:
    """Convert an Employee ORM object to a lightweight dict for AI context."""
    return {
        "name": emp.name,
        "employee_number": emp.employee_number,
        "department": emp.department,
        "team": emp.team,
        "position": emp.position,
        "status": emp.status,
        "hire_date": str(emp.hire_date) if emp.hire_date else None,
        "gender": emp.gender,
        "education": emp.education,
        "age": str(emp.age) if emp.age is not None else None,
    }


async def list_employees_by_department(
    session: AsyncSession, department: str
) -> tuple[list[dict[str, str | None]], int]:
    """List employees by department name."""
    repo = EmployeeRepository(session)
    employees, total = await repo.list_employees(
        department=department, page=1, page_size=200
    )
    data = [_employee_to_dict(e) for e in employees]
    return data, total


async def resolve_visible_dept_alias_set(
    session: AsyncSession,
    user: Any,
) -> set[str] | None:
    """解析用户 HR 可见培训部门别名集合（跨模块调用入口，供权限验证台等使用）。

    返回 None 表示管理员全部可见，与 hr/api.py `_resolve_visible_scope` 语义一致。
    延迟导入 hr.api 避免模块级循环依赖。
    """
    from app.modules.hr.api import _resolve_visible_scope

    return await _resolve_visible_scope(session, user)


async def query_employees(
    session: AsyncSession,
    *,
    filters: dict[str, Any],
    page: int = 1,
    page_size: int = 200,
) -> tuple[list[dict[str, str | None]], int]:
    """Flexible employee query for AI context injection.

    Args:
        filters: Dict of filter conditions (e.g.
        {"department": "生产部", "status": "在职"})
        page: Page number (1-based)
        page_size: Items per page

    Returns:
        Tuple of (employee dicts list, total count)
    """
    repo = EmployeeRepository(session)
    normalized = _normalize_filters(filters)
    employees, total = await repo.list_employees(
        **normalized, page=page, page_size=page_size
    )
    data = [_employee_to_dict(e) for e in employees]
    return data, total


async def count_employees(
    session: AsyncSession,
    *,
    filters: dict[str, Any],
) -> int:
    """Count employees matching flexible criteria."""
    repo = EmployeeRepository(session)
    normalized = _normalize_filters(filters)
    _, total = await repo.list_employees(**normalized, page=1, page_size=1)
    return total


async def search_employees_by_name(
    session: AsyncSession, name: str
) -> list[dict[str, str | None]]:
    """Search employees by name keyword.

    Returns a lightweight list of employee facts for AI context injection.
    """
    repo = EmployeeRepository(session)
    employees, _ = await repo.list_employees(keyword=name, page=1, page_size=10)
    return [_employee_to_dict(e) for e in employees]


async def search_employees_fuzzy(
    session: AsyncSession, name: str
) -> list[dict[str, str | None]]:
    """Fuzzy search: when exact match returns empty, search by each Chinese character.

    Returns employees whose name contains any character from the query name.
    """
    repo = EmployeeRepository(session)
    seen_ids: set[str] = set()
    results: list[dict[str, str | None]] = []

    for char in name:
        # Only search Chinese characters
        if "一" <= char <= "鿿":
            employees, _ = await repo.list_employees(keyword=char, page=1, page_size=10)
            for e in employees:
                uid = str(e.id)
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    results.append(_employee_to_dict(e))
    return results


async def group_count_employees(
    session: AsyncSession,
    *,
    group_by: str,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Group employees by a field and count occurrences.

    Args:
        group_by: Field name to group by (e.g. "education", "department")
        filters: Filter conditions

    Returns:
        List of {"value": field_value, "count": int} sorted by count descending.
    """
    _assert_field_allowed(group_by, "group_by")
    repo = EmployeeRepository(session)
    normalized = _normalize_filters(filters)
    return await repo.group_count(group_by, **normalized)


async def get_distinct_employee_values(
    session: AsyncSession,
    *,
    field: str,
    filters: dict[str, Any],
) -> list[str]:
    """Get distinct non-null values for a field.

    Args:
        field: Field name (e.g. "department", "education")
        filters: Filter conditions

    Returns:
        List of distinct values.
    """
    _assert_field_allowed(field, "field")
    repo = EmployeeRepository(session)
    normalized = _normalize_filters(filters)
    return await repo.get_distinct_values(field, **normalized)


async def query_training_ledgers(
    session: AsyncSession,
    keywords: list[str],
    *,
    limit: int = 5,
    content_limit: int = 400,
) -> list[dict[str, Any]]:
    """按关键词模糊检索培训台账（培训主题/内容/培训对象/授课部门）。

    供跨模块（如质量偏差工作台）只读检索使用；未命中返回空列表。
    """
    from datetime import date, datetime

    from sqlalchemy import or_, select

    from app.modules.hr.models import TrainingLedger

    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    cleaned = [k.strip() for k in keywords if k and len(k.strip()) >= 2]
    if not cleaned:
        return []
    patterns = [f"%{_escape_like(kw)}%" for kw in cleaned[:8]]
    match_clause = or_(
        *[
            column.ilike(pattern)
            for column in (
                TrainingLedger.training_subject,
                TrainingLedger.training_content,
                TrainingLedger.trainees,
                TrainingLedger.teaching_dept,
            )
            for pattern in patterns
        ]
    )
    stmt = (
        select(TrainingLedger)
        .where(TrainingLedger.is_deleted.is_(False), match_clause)
        .order_by(TrainingLedger.training_date.desc().nullslast())
        .limit(limit)
    )
    result = await session.execute(stmt)
    items: list[dict[str, Any]] = []
    for row in result.scalars().all():
        training_date = row.training_date
        items.append(
            {
                "training_date": (
                    training_date.isoformat()
                    if isinstance(training_date, (date, datetime))
                    else str(training_date) if training_date else None
                ),
                "training_subject": row.training_subject,
                "training_content": (row.training_content or "")[:content_limit],
                "training_method": row.training_method,
                "duration_hours": row.duration_hours,
                "trainer": row.trainer,
                "instructor": row.instructor,
                "teaching_dept": row.teaching_dept,
                "trainees": (row.trainees or "")[:200],
                "training_type": row.training_type,
                "assessment_result": row.assessment_result,
            }
        )
    return items
