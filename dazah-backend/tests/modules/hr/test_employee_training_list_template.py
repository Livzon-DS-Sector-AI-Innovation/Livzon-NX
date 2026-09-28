"""员工培训清单导出模板缺失时的错误契约回归测试。

生产曾因受控模板 HR-QD-01 从未随代码分发，导出在容器内抛出裸
FileNotFoundError 变成无信息 500，前端又只显示笼统「导出失败」。
回归锁定：模板缺失时抛出带部署指引的 AppException；模板放入
模块 templates 目录后能被优先找到。
"""

from pathlib import Path

import pytest

import app.modules.hr.employee_training_list_document_generator as gen
from app.core.exceptions import AppException


def test_missing_template_raises_app_exception_with_hint(monkeypatch):
    monkeypatch.setattr(gen, "TEMPLATE_NAME", "不存在-回归测试.xlsx")
    with pytest.raises(AppException) as exc_info:
        gen._find_template()
    assert "导出模板缺失" in exc_info.value.message
    assert "templates" in exc_info.value.message


def test_packaged_templates_dir_is_searched_first(monkeypatch):
    # 模块内置目录（git 跟踪）必须是第一候选，保证容器内随代码分发即可用
    packaged_dir = Path(gen.__file__).resolve().parent / "templates"
    placeholder = "占位-回归测试.xlsx"
    source = packaged_dir / placeholder
    if any(packaged_dir.glob("*.xlsx")):
        pytest.skip("内置模板目录已有模板文件，无需占位验证")
    packaged_dir.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(gen, "TEMPLATE_NAME", placeholder)
    try:
        assert gen._find_template() == source
    finally:
        source.unlink(missing_ok=True)
