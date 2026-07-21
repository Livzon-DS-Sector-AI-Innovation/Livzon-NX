"""Validation for module-scoped Feishu page binding keys."""

import re

from app.core.exceptions import AppException


def validate_module_page_key(page_key: str, module_code: str) -> None:
    """Accept menu keys in one module namespace without a fixed page list."""

    pattern = rf"{re.escape(module_code)}\.[\w-]+(?:\.[\w-]+)*"
    if len(page_key) > 255 or re.fullmatch(pattern, page_key) is None:
        raise AppException(message="不支持的菜单页面标识", status_code=404)
