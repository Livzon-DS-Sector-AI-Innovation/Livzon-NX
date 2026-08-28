from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_histories_have_one_merged_head() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["c1e7f4a9b2d6"]
    repair_revision = script.get_revision("c1e7f4a9b2d6")
    assert repair_revision is not None
    assert repair_revision.down_revision == "b5f4c8d1a2e3"
    merge_revision = script.get_revision("b5f4c8d1a2e3")
    assert merge_revision is not None
    assert set(merge_revision._normalized_down_revisions) == {
        "4772bce4935d",
        "5e1f7a9b0c2d",
    }
