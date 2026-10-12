"""Readable evidence fallback; never infer a global total from retained samples."""

import re
from typing import Any


def answer_focus(request: str) -> str:
    return "count" if re.search(
        r"多少|总数|人数|(?:有|共|总共)几(?:人|名|个|条|项)|数量(?:是多少|有多少)|how many|\bcount\b",
        request, re.IGNORECASE,
    ) else "details"


def reported_total(data: Any) -> tuple[int, str] | None:
    if not isinstance(data, dict):
        return None
    for container, prefix in [(data.get("meta"), "/meta"), (data.get("pagination"), "/pagination"), (data, "")]:
        if not isinstance(container, dict):
            continue
        for key in ("total", "count"):
            if key in container:
                value = container[key]
                # A present but invalid total cannot be replaced with page length.
                return (value, prefix + "/" + key) if type(value) is int and value >= 0 else None
    return None


_FIELD_LABELS = {
    "name": "姓名", "department": "部门", "employee_no": "工号", "job_title": "岗位",
    "status": "状态", "total": "总数", "count": "数量", "code": "编号", "record_id": "记录编号",
    "id": "标识", "amount": "数量", "items": "记录", "data": "内容", "meta": "分页信息",
    "page": "页码", "page_size": "每页条数",
}


def _readable_value(value: Any, depth: int = 0) -> str:
    if depth > 6:
        return "内容较长，暂未展开。"
    if isinstance(value, dict):
        return "\n".join(
            f"{_FIELD_LABELS.get(str(key), str(key))}：{_readable_value(item, depth + 1)}"
            for key, item in value.items() if item is not None
        ) or "暂无内容。"
    if isinstance(value, list):
        rows = [item for item in value if not (isinstance(item, dict) and set(item) == {"展示范围"})]
        lines = [f"- {_readable_value(item, depth + 1)}" for item in rows[:3]]
        lines.extend(str(item["展示范围"]) for item in value if isinstance(item, dict) and set(item) == {"展示范围"})
        if len(rows) > 3:
            lines.append(f"仅展示前 3 条，本次返回 {len(rows)} 条。")
        return "\n".join(lines) or "未找到符合条件的记录。"
    if value is None:
        return "未提供"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def render_business_data(data: Any, *, focus: str = "details") -> str:
    total = reported_total(data)
    if focus == "count":
        return (
            f"本次查询范围内的总数为 **{total[0]}**。"
            if total is not None else "已取得查询结果，但返回信息不足，无法确认总数；不能把当前页或展示样本当作全部记录。"
        )
    if isinstance(data, dict):
        rows = next((data[key] for key in ("data", "items", "records") if isinstance(data.get(key), list)), None)
        if rows is not None:
            summary = f"本次查询范围内共 **{total[0]}** 条记录。\n\n" if total is not None else ""
            details = _readable_value(rows)
            if total is not None and rows and total[0] > len(rows) and not any(
                isinstance(row, dict) and "展示范围" in row for row in rows
            ):
                details += "\n仅展示本次返回的部分记录。"
            remaining = {key: value for key, value in data.items() if key not in {"data", "items", "records", "meta", "pagination", "total"}}
            return summary + details + ("\n\n" + _readable_value(remaining) if remaining else "")
    return _readable_value(data)
