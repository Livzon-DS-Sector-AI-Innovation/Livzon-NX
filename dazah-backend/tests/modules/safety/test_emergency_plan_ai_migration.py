"""应急预案 AI 工作台迁移断言（建表、FK 级联、部分唯一索引、回退顺序）。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

_VERSIONS = Path(__file__).resolve().parents[3] / "alembic/versions"
_NAME = "e5a9c3d7f2b8_add_emergency_plan_ai_workbench"


def _load():
    path = _VERSIONS / f"{_NAME}.py"
    spec = importlib.util.spec_from_file_location(_NAME, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_chains_from_work_permit_signatures() -> None:
    module = _load()
    assert module.revision == "e5a9c3d7f2b8"
    assert module.down_revision == "d7b2f9a4c1e6"


def test_upgrade_creates_three_tables_in_safety_schema(monkeypatch) -> None:
    module = _load()
    create_table, create_index = Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", create_index)

    module.upgrade()

    tables = [call.args[0] for call in create_table.call_args_list]
    assert tables == [
        "emergency_plan_contents",
        "emergency_plan_revisions",
        "emergency_plan_ai_messages",
    ]
    for call in create_table.call_args_list:
        assert call.kwargs["schema"] == "safety"
        column_names = {item.name for item in call.args[1:] if hasattr(item, "type")}
        assert {"id", "plan_id", "is_deleted", "created_at"} <= column_names

    contents_columns = {
        item.name
        for item in create_table.call_args_list[0].args[1:]
        if hasattr(item, "type")
    }
    assert {
        "content",
        "content_status",
        "revision_no",
        "ai_generated",
        "generation_params",
        "last_review",
        "last_reviewed_at",
        "content_updated_at",
    } <= contents_columns

    unique_index = next(
        call
        for call in create_index.call_args_list
        if call.args[0] == "uq_safety_emergency_plan_contents_plan"
    )
    assert unique_index.kwargs["unique"] is True
    assert "is_deleted = false" in str(unique_index.kwargs["postgresql_where"])


def test_plan_foreign_keys_cascade(monkeypatch) -> None:
    module = _load()
    create_table = Mock()
    monkeypatch.setattr(module.op, "create_table", create_table)
    monkeypatch.setattr(module.op, "create_index", Mock())

    module.upgrade()

    for call in create_table.call_args_list:
        plan_fks = [
            item
            for item in call.args[1:]
            if item.__class__.__name__ == "ForeignKeyConstraint"
            and list(item.column_keys) == ["plan_id"]
        ]
        assert len(plan_fks) == 1
        assert plan_fks[0].ondelete == "CASCADE"


def test_downgrade_drops_in_reverse_order(monkeypatch) -> None:
    module = _load()
    drop_table, drop_index = Mock(), Mock()
    monkeypatch.setattr(module.op, "drop_table", drop_table)
    monkeypatch.setattr(module.op, "drop_index", drop_index)

    module.downgrade()

    assert [call.args[0] for call in drop_table.call_args_list] == [
        "emergency_plan_ai_messages",
        "emergency_plan_revisions",
        "emergency_plan_contents",
    ]
    assert all(call.kwargs["schema"] == "safety" for call in drop_table.call_args_list)
