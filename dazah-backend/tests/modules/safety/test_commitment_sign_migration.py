"""安全承诺车间签署迁移结构守护：单 head、链路正确、与模型对齐。"""

import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script() -> ScriptDirectory:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    return ScriptDirectory.from_config(config)


def test_commitment_sign_migration_chains_single_head():
    """f9a3d5c7e1b2 接在 e7c2a9f4b6d8 之后，且迁移链保持单 head。"""
    script = _script()
    heads = script.get_heads()
    assert len(heads) == 1, f"迁移必须保持单 head，当前: {heads}"
    revision = script.get_revision("f9a3d5c7e1b2")
    assert revision is not None
    assert revision.down_revision == "e7c2a9f4b6d8"


def test_commitment_sign_migration_matches_models():
    """迁移建表与承诺签署/车间模型一致（关键列表）。"""
    script = _script()
    revision = script.get_revision("f9a3d5c7e1b2")
    assert revision is not None and revision.path is not None
    spec = importlib.util.spec_from_file_location(
        "commitment_sign_migration", revision.path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = Path(revision.path).read_text(encoding="utf-8")
    from app.modules.safety import models

    # 迁移中出现的承诺相关新表名（签署/车间）都应在模型中可对应
    found = [
        name
        for name in (
            "safety_commitment_workshop_configs",
            "safety_commitment_workshop_fills",
            "safety_commitment_signatures",
        )
        if name in source
    ]
    assert found, "迁移应包含承诺车间/签署相关新表"
    # 迁移里的新表都能在模型元数据中找到（schema=safety 前缀兼容）
    model_tables = set()
    for name in dir(models):
        obj = getattr(models, name, None)
        if isinstance(obj, type) and hasattr(obj, "__table__"):
            model_tables.add(obj.__table__.name)
    for name in found:
        assert name in model_tables, f"迁移建表 {name} 缺少对应模型"
