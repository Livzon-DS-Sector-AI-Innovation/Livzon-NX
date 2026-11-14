"""监护人名单迁移结构守护：单 head、链路正确、与模型表结构对齐。"""

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script() -> ScriptDirectory:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(config)


def test_guardian_roster_migration_chains_single_head():
    """e7c2a9f4b6d8 接在 4bd62e5d78a1 之后，且迁移链保持单 head。"""
    script = _script()
    heads = script.get_heads()
    assert len(heads) == 1, f"迁移必须保持单 head，当前: {heads}"
    revision = script.get_revision("e7c2a9f4b6d8")
    assert revision is not None
    assert revision.down_revision == "4bd62e5d78a1"
    assert (
        heads[0] == "e7c2a9f4b6d8"
        or script.get_revision(heads[0]).down_revision is not None
    )


def test_guardian_roster_migration_matches_model():
    """迁移建表与 GuardianRoster 模型一致（表名/schema/关键列）。"""
    from app.modules.safety.models import GuardianRoster

    script = _script()
    revision = script.get_revision("e7c2a9f4b6d8")
    assert revision is not None and revision.path is not None
    spec = importlib.util.spec_from_file_location(
        "guardian_roster_migration", revision.path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    table = GuardianRoster.__table__
    source = Path(revision.path).read_text(encoding="utf-8")
    # 建表名与 schema 一致（迁移里出现 safety.guardian_roster 与表名）
    assert table.name == "guardian_roster"
    assert "guardian_roster" in source and "safety" in source
    # 关键列都应在迁移中出现（存在性文本断言，避免解析 DDL）
    for column in (
        "person_name",
        "workshop",
        "phone",
        "position",
        "score",
        "exam_name",
        "exam_date",
        "remark",
        "source_file",
    ):
        assert column in table.columns, f"模型缺列 {column}"
        assert column in source, f"迁移未建列 {column}"
    # 车间索引（按车间聚合统计依赖）
    assert "ix_guardian_roster_workshop" in source
