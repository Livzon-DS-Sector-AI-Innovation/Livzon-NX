"""The security repair and current main must remain reachable without data DDL."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from app.core import dev_migration as guard


def test_merge_preserves_both_histories_and_runs_no_database_operations(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["b9e4f7a2c5d1"]
    merge = script.get_revision("b8d2f4a6c0e9")
    assert merge is not None
    assert set(merge.down_revision) == {"a7c3e5f1b8d2", "f4a6c8e0b2d5"}
    for parent in merge.down_revision:
        pending = list(
            script.iterate_revisions(merge.revision, parent, implicit_base=True)
        )
        assert pending[0].revision == merge.revision
        assert parent not in {revision.revision for revision in pending}
        assert set(merge.down_revision) - {parent} <= {r.revision for r in pending}
    history = {revision.revision for revision in script.walk_revisions()}
    assert {"d1f2a3b4c5d6", "a7c3e5f1b8d2", "f4a6c8e0b2d5"} <= history

    spec = importlib.util.spec_from_file_location("security_history_merge", merge.path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    operations = Mock()
    monkeypatch.setattr(module, "op", operations, raising=False)
    module.upgrade()
    module.downgrade()
    assert operations.mock_calls == []


def test_reviewed_plan_includes_the_other_branch_like_alembic_upgrade(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(config)
    for current in ("f4a6c8e0b2d5", "a7c3e5f1b8d2"):
        monkeypatch.setattr(
            guard.MigrationContext,
            "configure",
            lambda _, revision=current: SimpleNamespace(
                get_current_heads=lambda: (revision,)
            ),
        )
        connection = SimpleNamespace(
            scalar=lambda _: "development",
            engine=SimpleNamespace(url=make_url("postgresql://db/development")),
        )
        plan = guard._read_plan(config, connection)
        actual = script._upgrade_revs("head", current)
        assert plan.pending_revisions == tuple(
            step.revision.revision for step in actual
        )
        assert plan.pending_revisions[-1] == "b9e4f7a2c5d1"
        assert len(plan.pending_revisions) > 1
