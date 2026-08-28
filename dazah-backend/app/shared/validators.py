"""共享校验函数"""

import logging

logger = logging.getLogger(__name__)


def normalize_yield_rate(value: float | None) -> float | None:
    """将小数格式的收率值自动转换为百分比格式。

    如果 0 < value <= 10，判定为小数格式（如 0.93 表示 93%），自动 ×100。
    否则保持原值（已是百分比格式或为 0/None）。
    """
    if value is not None and 0 < value <= 10:
        logger.info(
            "yield_rate_auto_normalized original=%s normalized=%s",
            value,
            value * 100,
        )
        return value * 100
    return value
