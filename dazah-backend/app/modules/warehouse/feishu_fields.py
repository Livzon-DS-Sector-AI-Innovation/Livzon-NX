"""飞书多维表格字段类型常量与 CellValue 转换工具。

字段类型对齐飞书 OpenAPI /fields 返回的 type 数值：
https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-field/field-overview

页面编辑写回时，必须按字段类型构造 CellValue；公式、系统字段
（创建人/创建时间等）只读，人员/附件/关联字段仅查看不可编辑。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

# ── 字段类型常量（飞书 OpenAPI type 数值）──────────────────
FIELD_TYPE_TEXT = 1  # 多行文本
FIELD_TYPE_NUMBER = 2  # 数字
FIELD_TYPE_SINGLE_SELECT = 3  # 单选
FIELD_TYPE_MULTI_SELECT = 4  # 多选
FIELD_TYPE_DATE = 5  # 日期
FIELD_TYPE_CHECKBOX = 7  # 复选框
FIELD_TYPE_PERSON = 11  # 人员
FIELD_TYPE_PHONE = 13  # 电话号码
FIELD_TYPE_URL = 15  # 超链接
FIELD_TYPE_ATTACHMENT = 17  # 附件
FIELD_TYPE_LINK = 18  # 关联
FIELD_TYPE_FORMULA = 19  # 公式
FIELD_TYPE_CREATED_TIME = 20  # 创建时间
FIELD_TYPE_MODIFIED_TIME = 21  # 修改时间
FIELD_TYPE_CREATED_USER = 22  # 创建人
FIELD_TYPE_MODIFIED_USER = 23  # 修改人
FIELD_TYPE_AUTO_NUMBER = 24  # 自动编号
FIELD_TYPE_CREATED_TIME_NEW = 1001  # 创建时间（新版）
FIELD_TYPE_MODIFIED_TIME_NEW = 1002  # 修改时间（新版）
FIELD_TYPE_CREATED_USER_NEW = 1003  # 创建人（新版）
FIELD_TYPE_MODIFIED_USER_NEW = 1004  # 修改人（新版）
FIELD_TYPE_LINK_NEW = 1005  # 单向关联（新版）
FIELD_TYPE_LINK_BIDIRECTIONAL_NEW = 1006  # 双向关联（新版）

# 只读字段：公式与系统字段，页面禁止编辑并提示
FIELD_READONLY_TYPES = frozenset(
    {
        FIELD_TYPE_FORMULA,
        FIELD_TYPE_CREATED_TIME,
        FIELD_TYPE_MODIFIED_TIME,
        FIELD_TYPE_CREATED_USER,
        FIELD_TYPE_MODIFIED_USER,
        FIELD_TYPE_AUTO_NUMBER,
        FIELD_TYPE_CREATED_TIME_NEW,
        FIELD_TYPE_MODIFIED_TIME_NEW,
        FIELD_TYPE_CREATED_USER_NEW,
        FIELD_TYPE_MODIFIED_USER_NEW,
    }
)

# 仅查看字段：人员/附件/关联，详情弹窗展示但不可编辑
FIELD_VIEW_ONLY_TYPES = frozenset(
    {
        FIELD_TYPE_PERSON,
        FIELD_TYPE_ATTACHMENT,
        FIELD_TYPE_LINK,
        FIELD_TYPE_LINK_NEW,
        FIELD_TYPE_LINK_BIDIRECTIONAL_NEW,
    }
)

# 人员字段类型：人员选择、创建人、修改人（新旧版），值均为人员数组
FIELD_PERSON_TYPES = frozenset(
    {
        FIELD_TYPE_PERSON,
        FIELD_TYPE_CREATED_USER,
        FIELD_TYPE_MODIFIED_USER,
        FIELD_TYPE_CREATED_USER_NEW,
        FIELD_TYPE_MODIFIED_USER_NEW,
    }
)

# 页面可编辑字段类型
FIELD_EDITABLE_TYPES = frozenset(
    {
        FIELD_TYPE_TEXT,
        FIELD_TYPE_NUMBER,
        FIELD_TYPE_SINGLE_SELECT,
        FIELD_TYPE_MULTI_SELECT,
        FIELD_TYPE_DATE,
        FIELD_TYPE_CHECKBOX,
        FIELD_TYPE_PHONE,
        FIELD_TYPE_URL,
    }
)

FIELD_TYPE_NAMES: dict[int, str] = {
    FIELD_TYPE_TEXT: "多行文本",
    FIELD_TYPE_NUMBER: "数字",
    FIELD_TYPE_SINGLE_SELECT: "单选",
    FIELD_TYPE_MULTI_SELECT: "多选",
    FIELD_TYPE_DATE: "日期",
    FIELD_TYPE_CHECKBOX: "复选框",
    FIELD_TYPE_PERSON: "人员",
    FIELD_TYPE_PHONE: "电话号码",
    FIELD_TYPE_URL: "超链接",
    FIELD_TYPE_ATTACHMENT: "附件",
    FIELD_TYPE_LINK: "关联",
    FIELD_TYPE_FORMULA: "公式",
    FIELD_TYPE_CREATED_TIME: "创建时间",
    FIELD_TYPE_MODIFIED_TIME: "修改时间",
    FIELD_TYPE_CREATED_USER: "创建人",
    FIELD_TYPE_MODIFIED_USER: "修改人",
    FIELD_TYPE_AUTO_NUMBER: "自动编号",
    FIELD_TYPE_CREATED_TIME_NEW: "创建时间",
    FIELD_TYPE_MODIFIED_TIME_NEW: "修改时间",
    FIELD_TYPE_CREATED_USER_NEW: "创建人",
    FIELD_TYPE_MODIFIED_USER_NEW: "修改人",
    FIELD_TYPE_LINK_NEW: "关联",
    FIELD_TYPE_LINK_BIDIRECTIONAL_NEW: "关联",
}


def _normalize_type(field_type: int | str | None) -> int | None:
    """飞书返回的 type 可能是 int 或数字字符串，统一为 int。"""
    if field_type is None:
        return None
    try:
        return int(field_type)
    except (TypeError, ValueError):
        return None


def field_type_name(field_type: int | str | None) -> str:
    normalized = _normalize_type(field_type)
    if normalized is None:
        return ""
    return FIELD_TYPE_NAMES.get(normalized, f"未知({normalized})")


def is_readonly_field(field_type: int | str | None) -> bool:
    normalized = _normalize_type(field_type)
    return normalized is not None and normalized in FIELD_READONLY_TYPES


def is_view_only_field(field_type: int | str | None) -> bool:
    normalized = _normalize_type(field_type)
    return normalized is not None and normalized in FIELD_VIEW_ONLY_TYPES


def is_editable_field(field_type: int | str | None) -> bool:
    normalized = _normalize_type(field_type)
    return normalized is not None and normalized in FIELD_EDITABLE_TYPES


def _to_ms_timestamp(value: date | datetime | str | None) -> int | str:
    """Convert date/datetime to Feishu Bitable millisecond timestamp (UTC)."""
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return str(value)
    if isinstance(value, (date, datetime)):
        if isinstance(value, date) and not isinstance(value, datetime):
            dt = datetime(value.year, value.month, value.day, tzinfo=UTC)
        else:
            dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return int(dt.timestamp() * 1000)
    return str(value)


def build_feishu_cell_value(field_type: int | str | None, value: Any) -> Any:
    """按字段类型将页面提交的编辑值转换为飞书 CellValue。

    不可编辑/只读字段返回 None，调用方应跳过写入。
    """
    normalized = _normalize_type(field_type)
    if normalized is None or value is None:
        return None

    if normalized == FIELD_TYPE_TEXT or normalized == FIELD_TYPE_PHONE:
        return str(value)
    if normalized == FIELD_TYPE_NUMBER:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", "").strip())
        except ValueError:
            return None
    if normalized == FIELD_TYPE_SINGLE_SELECT:
        return str(value)
    if normalized == FIELD_TYPE_MULTI_SELECT:
        if isinstance(value, list):
            return [str(item) for item in value if item not in (None, "")]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return None
    if normalized == FIELD_TYPE_DATE:
        return _to_ms_timestamp(value)
    if normalized == FIELD_TYPE_CHECKBOX:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "是", "yes"}
        return bool(value)
    if normalized == FIELD_TYPE_URL:
        if isinstance(value, dict) and value.get("link"):
            return value
        return {"text": str(value), "link": str(value)}
    return None


def format_detail_value(field_type: int | str | None, value: Any) -> Any:
    """将飞书原始 CellValue 格式化为详情弹窗可读结构。

    日期时间戳转 YYYY-MM-DD；复选框转布尔；人员/附件/关联保留
    关键字段（id/name/tmp_url），供前端展示。
    """
    normalized = _normalize_type(field_type)
    if value is None:
        return None

    if normalized == FIELD_TYPE_DATE:
        if isinstance(value, (int, float)):
            timestamp_value = float(value)
            if timestamp_value > 1e12:
                timestamp_value /= 1000
            try:
                return datetime.fromtimestamp(timestamp_value).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError):
                return value
        if isinstance(value, str) and len(value) == 13 and value.isdigit():
            try:
                return datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError):
                return value
        return value
    if normalized == FIELD_TYPE_CHECKBOX:
        return bool(value)
    if normalized in FIELD_PERSON_TYPES:
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            return value
        return [
            {
                "id": item.get("id") if isinstance(item, dict) else None,
                "name": item.get("name") if isinstance(item, dict) else str(item),
                "avatar_url": (
                    item.get("avatar_url") or item.get("avatar") or ""
                    if isinstance(item, dict)
                    else None
                ),
            }
            for item in value
        ]
    if normalized == FIELD_TYPE_ATTACHMENT:
        if not isinstance(value, list):
            return value
        return [
            {
                "file_token": item.get("file_token")
                if isinstance(item, dict)
                else None,
                "name": item.get("name") if isinstance(item, dict) else str(item),
                "url": item.get("tmp_url") if isinstance(item, dict) else None,
            }
            for item in value
        ]
    if normalized == FIELD_TYPE_URL:
        if isinstance(value, dict):
            return value.get("link") or value.get("text")
        return value
    if normalized in (
        FIELD_TYPE_LINK,
        FIELD_TYPE_LINK_NEW,
        FIELD_TYPE_LINK_BIDIRECTIONAL_NEW,
    ):
        if isinstance(value, list):
            return [str(item) for item in value]
        return value
    return value
