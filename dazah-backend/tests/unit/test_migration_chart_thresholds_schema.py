"""chart_thresholds 迁移结构性校验（表结构/约束/降级）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from alembic.config import Config
from alembic.script import ScriptDirectory


def _load_migration():
    root = Path(__file__).resolve().parents[2]
    path = root / "alembic" / "versions" / "c9d3e7a1f5b2_add_chart_thresholds.py"
    spec = importlib.util.spec_from_file_location("mig_chart_thresholds", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_is_single_head_and_linked() -> None:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"迁移必须保持单 head，当前: {heads}"
    rev = script.get_revision("c9d3e7a1f5b2")
    assert rev is not None
    assert rev.down_revision == "b3a6d7e8f902"


def test_upgrade_creates_table_with_expected_shape() -> None:
    module = _load_migration()
    calls: list[tuple] = []

    def _record(func_name, *args, **kwargs):
        calls.append((func_name, args, kwargs))

    module.op = MagicMock()
    for fn in ("create_table", "create_index", "drop_index", "drop_table"):
        side = lambda *a, _fn=fn, **k: _record(_fn, *a, **k)  # noqa: E731
        getattr(module.op, fn).side_effect = side

    module.upgrade()
    creates = [c for c in calls if c[0] == "create_table"]
    assert len(creates) == 1
    name, cols, kw = creates[0][1][0], creates[0][1][1:], creates[0][2]
    assert name == "chart_thresholds"
    col_names = {c.name for c in cols}
    assert {"id", "scope_key", "chart_key", "threshold", "is_deleted"} <= col_names
    assert kw.get("schema") == "production"

    module.downgrade()
    drops = [c for c in calls if c[0] == "drop_table"]
    assert drops and drops[0][1][0] == "chart_thresholds"
