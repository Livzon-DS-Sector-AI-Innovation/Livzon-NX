"""公告通知迁移 DDL 契约测试。

加载迁移文件并 mock op，断言 upgrade 只建 administration.notices 一张表
及两个索引（BaseModel 公共列逐列写出），downgrade 逆序删除、不动 schema。
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
import sqlalchemy as sa

MIGRATION_FILE = "b6d8a2e4c9f1_add_administration_notices.py"


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / f"alembic/versions/{MIGRATION_FILE}"
    spec = importlib.util.spec_from_file_location(
        MIGRATION_FILE.replace(".py", ""), path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_ops(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> dict[str, Mock]:
    mocks = {
        name: Mock()
        for name in (
            "create_table",
            "create_index",
            "drop_index",
            "drop_table",
            "execute",
        )
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(module.op, name, mock)
    return mocks


def test_upgrade_creates_notices_table_with_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load()
    mocks = _mock_ops(monkeypatch, module)

    module.upgrade()

    created = [call.args[0] for call in mocks["create_table"].call_args_list]
    assert created == ["notices"]
    create_call = mocks["create_table"].call_args_list[0]
    assert create_call.kwargs["schema"] == "administration"
    columns = {col.name for col in create_call.args[1:] if hasattr(col, "name")}
    # BaseModel 公共列必须逐列写出
    assert {"id", "created_at", "updated_at", "created_by", "is_deleted"} <= columns
    # 公告台账业务列齐备；search_text 必须存在（元数据搜索，不含内容）
    assert {
        "notice_no",
        "title",
        "publisher",
        "published_at",
        "category",
        "content",
        "remark",
        "source_file_name",
        "source_storage_key",
        "search_text",
    } <= columns
    # 两个业务索引以内联 sa.Index 随表创建（无独立 op.create_index 调用）
    inline_indexes = [arg for arg in create_call.args[1:] if isinstance(arg, sa.Index)]
    assert [idx.name for idx in inline_indexes] == [
        "ix_administration_notices_published_at",
        "ix_administration_notices_category",
    ]
    assert mocks["create_index"].call_count == 0
    assert mocks["execute"].call_count == 0, "administration schema 已存在，不得重建"


def test_downgrade_drops_notices_table(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load()
    mocks = _mock_ops(monkeypatch, module)

    module.downgrade()

    dropped = [call.args[0] for call in mocks["drop_table"].call_args_list]
    assert dropped == ["notices"]
    assert mocks["drop_table"].call_args_list[0].kwargs["schema"] == "administration"
    assert mocks["execute"].call_count == 0
    assert mocks["drop_index"].call_count == 0, "内联索引随表删除"
