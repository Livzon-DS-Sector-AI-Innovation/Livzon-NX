"""安全模块飞书设置迁移链断言（5 个迁移的 DDL 与回退）。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

_VERSIONS = Path(__file__).resolve().parents[3] / "alembic/versions"
_CHAIN = [
    "b7d2e4f60a58_widen_change_object_to_text",
    "b4c6e8f2a9d0_create_safety_feishu_app_settings",
    "d2f5a8c0e3b1_safety_knowledge_feishu_mirror",
    "e6b9c2f4a7d3_drop_knowledge_update_status",
    "f8d4b6e2c9a1_add_knowledge_local_attachments",
]


def _load(name: str):
    path = _VERSIONS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chain_is_linear_from_main_head() -> None:
    """5 个迁移必须自主线 head 起单线串联，无分叉。"""
    modules = {name: _load(name) for name in _CHAIN}
    assert modules["b7d2e4f60a58_widen_change_object_to_text"].down_revision == (
        "a3f8c2d91e47"
    )
    by_rev = {m.revision: m for m in modules.values()}
    for module in modules.values():
        parent = module.down_revision
        if parent in by_rev:
            assert by_rev[parent].revision == parent
    # 每个 down_revision 都指向链上前一个（或主线 head），链上出现环/分叉时收集不齐
    order = ["a3f8c2d91e47"]
    while len(order) <= len(_CHAIN):
        nxt = [
            m.revision
            for m in modules.values()
            if m.down_revision == order[-1]
        ]
        assert len(nxt) == 1, f"链在 {order[-1]} 后分叉: {nxt}"
        order.append(nxt[0])


def test_widen_change_object_alters_quality_table_and_reverts(monkeypatch) -> None:
    module = _load("b7d2e4f60a58_widen_change_object_to_text")
    execute = Mock()
    monkeypatch.setattr(module.op, "execute", execute)

    module.upgrade()
    assert execute.call_args_list[0].args[0] == (
        "ALTER TABLE quality.quality_change_controls "
        "ALTER COLUMN change_object TYPE TEXT"
    )
    execute.reset_mock()
    module.downgrade()
    assert execute.call_args_list[0].args[0] == (
        "ALTER TABLE quality.quality_change_controls "
        "ALTER COLUMN change_object TYPE VARCHAR(255)"
    )


def test_feishu_app_settings_creates_and_drops_table(monkeypatch) -> None:
    module = _load("b4c6e8f2a9d0_create_safety_feishu_app_settings")
    create, drop = Mock(), Mock()
    monkeypatch.setattr(module.op, "create_table", create)
    monkeypatch.setattr(module.op, "drop_table", drop)

    module.upgrade()
    assert create.call_args.args[0] == "feishu_app_settings"
    assert create.call_args.kwargs.get("schema") == "safety"
    column_names = {
        col.name for col in create.call_args.args[1:] if hasattr(col, "name")
    }
    assert {"app_id", "app_secret", "is_enabled"} <= column_names

    module.downgrade()
    drop.assert_called_once_with(
        "feishu_app_settings", schema="safety"
    )
