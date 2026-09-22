import importlib.util
from pathlib import Path
from unittest.mock import Mock


def test_department_migration_preserves_existing_plan_columns(monkeypatch):
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/c9d400000054_add_capa_plan_department.py"
    )
    spec = importlib.util.spec_from_file_location("capa_department_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    add, drop = Mock(), Mock()
    monkeypatch.setattr(module.op, "add_column", add)
    monkeypatch.setattr(module.op, "drop_column", drop)
    module.upgrade()
    table, column = add.call_args.args
    assert table == "capa_plan_tracks"
    assert column.name == "department" and column.nullable
    assert add.call_args.kwargs == {"schema": "quality"}
    module.downgrade()
    drop.assert_called_once_with("capa_plan_tracks", "department", schema="quality")
