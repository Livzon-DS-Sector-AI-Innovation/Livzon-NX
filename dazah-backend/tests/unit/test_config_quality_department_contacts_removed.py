"""部门联系人配置项下线断言（core config 回归防护）。

QUALITY_DEPARTMENT_CONTACT_FEISHU_APP_TOKEN / _TABLE_ID 随部门联系人功能
整体删除；本测试防止环境变量或 Settings 字段被无意恢复。
"""

from __future__ import annotations

import inspect

from app.core.config import Settings


def test_department_contact_settings_fields_removed() -> None:
    fields = set(Settings.model_fields.keys())
    assert "QUALITY_DEPARTMENT_CONTACT_FEISHU_APP_TOKEN" not in fields
    assert "QUALITY_DEPARTMENT_CONTACT_FEISHU_TABLE_ID" not in fields


def test_department_contact_env_names_absent_from_module_source() -> None:
    source = inspect.getsource(Settings)
    assert "QUALITY_DEPARTMENT_CONTACT" not in source
