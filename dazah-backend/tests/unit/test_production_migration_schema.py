"""生产模块数据库迁移的结构测试。

覆盖 PR 迁移中引入的 fermentation_records 表迁移：
- upgrade 先检查目标表存在则删除，再建表并建索引
- downgrade 按顺序删索引、删表
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa

FERMENTATION_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "2f0b698eb4d8_add_fermentation_records_table.py"
)


def _load_fermentation_migration():
    spec = importlib.util.spec_from_file_location(
        "fermentation_records_migration",
        FERMENTATION_MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_inspect(has_table: bool):
    """构造 sa.inspect 返回的假 inspector，带 has_table 结果。"""

    class _Inspector:
        def has_table(self, table_name: str, schema: str | None) -> bool:
            return has_table

    return _Inspector()


def test_fermentation_migration_upgrade_drops_existing_and_creates_table(
    monkeypatch,
) -> None:
    migration = _load_fermentation_migration()
    created_tables: list[str] = []
    dropped_tables: list[tuple[str, str]] = []
    created_indexes: list[tuple[str, str, list[str], bool]] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    # 让 sa.inspect(conn) 返回一个带 has_table 结果的假 inspector。
    monkeypatch.setattr(sa, "inspect", lambda conn: _fake_inspect(has_table=True))
    monkeypatch.setattr(migration.op, "create_table",
        lambda *args, **kwargs: created_tables.append(str(args[0])) or None,
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: dropped_tables.append((table, k.get("schema"))) or None,
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, **kwargs: created_indexes.append(
            (name, table, columns, bool(kwargs.get("unique")))
        )
        or None,
    )

    migration.upgrade()

    assert "fermentation_records" in created_tables
    assert ("fermentation_records", "production") in dropped_tables
    assert {index[0] for index in created_indexes} == {
        "ix_fermentation_records_batch_no",
        "ix_fermentation_records_product_name",
    }
    assert all(index[2] == ["batch_no"] or index[2] == ["product_name"] for index in created_indexes)


def test_fermentation_migration_upgrade_does_not_drop_when_table_missing(
    monkeypatch,
) -> None:
    migration = _load_fermentation_migration()
    dropped_tables: list[tuple[str, str]] = []
    created_tables: list[str] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(sa, "inspect", lambda conn: _fake_inspect(has_table=False))
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: dropped_tables.append((table, k.get("schema"))) or None,
    )
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda *args, **kwargs: created_tables.append(str(args[0])) or None,
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, **kwargs: None,
    )

    migration.upgrade()

    assert dropped_tables == []
    assert "fermentation_records" in created_tables


def test_fermentation_migration_downgrade_drops_indexes_and_table(
    monkeypatch,
) -> None:
    migration = _load_fermentation_migration()
    dropped_indexes: list[tuple[str, str, str]] = []
    dropped_tables: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, table_name, **kw: dropped_indexes.append(
            (name, table_name, kw.get("schema"))
        )
        or None,
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: dropped_tables.append((table, k.get("schema"))) or None,
    )

    migration.downgrade()

    assert dropped_indexes == [
        ("ix_fermentation_records_product_name", "fermentation_records", "production"),
        ("ix_fermentation_records_batch_no", "fermentation_records", "production"),
    ]
    assert dropped_tables == [("fermentation_records", "production")]