from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_histories_have_one_merged_head() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))

    script = ScriptDirectory.from_config(config)

    # 不变量：迁移链只有一个头（不允许出现分叉的多头）。
    # 不钉具体 revision —— 头会随新增迁移正常前进。
    heads = script.get_heads()
    assert len(heads) == 1, f"期望单一迁移头，实际为: {heads}"

    page_merge = script.get_revision("9e2f4a6c8b10")
    assert page_merge is not None
    assert set(page_merge._normalized_down_revisions) == {
        "d1e2f3a4b5c6",
        "f7b2d9a4c103",
    }
    assert script.get_revision("f7b2d9a4c103").down_revision == "d2f8a4c6e1b3"

    # 合并历史锚点保持不变：b5f4c8d1a2e3 是合并修订，
    # 其父为旧线两条链的 4772bce4935d 与 5e1f7a9b0c2d。
    merge_revision = script.get_revision("b5f4c8d1a2e3")
    assert merge_revision is not None
    assert set(merge_revision._normalized_down_revisions) == {
        "4772bce4935d",
        "5e1f7a9b0c2d",
    }
