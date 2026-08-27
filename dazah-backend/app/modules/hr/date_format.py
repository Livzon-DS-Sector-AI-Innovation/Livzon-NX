"""HR 培训模块日期显示格式常量与工具函数。

仅用于文档导出格式化。API 响应中的 date 字段保持 Pydantic 默认 ISO 格式。
"""

from datetime import datetime
from typing import Any

# 文档导出日期格式：YYYY.MM.DD
HR_EXPORT_DATE_FORMAT = "%Y.%m.%d"


def fmt_date_str(v: Any) -> str:
    """将 YYYY-MM-DD 字符串转为 YYYY.MM.DD。

    无法解析时原样返回，保证不因格式问题导致导出失败。
    """
    if not v:
        return ""
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").strftime(
            HR_EXPORT_DATE_FORMAT
        )
    except (ValueError, TypeError):
        return str(v)


def fmt_date_obj(v: Any) -> str:
    """将 date 对象格式化为 YYYY.MM.DD。"""
    if v is None:
        return ""
    return str(v.strftime(HR_EXPORT_DATE_FORMAT))
