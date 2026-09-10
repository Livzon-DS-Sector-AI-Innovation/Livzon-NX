"""生产模块数据库迁移的结构测试。

覆盖 PR 迁移中引入的 fermentation_records 表迁移：
- upgrade 先检查目标表存在则删除，再建表并建索引
- downgrade 按顺序删索引、删表

覆盖发酵看板批次实绩与扎帐月设置迁移（批号/周期部分唯一索引 + 软删）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import sqlalchemy as sa

FERMENTATION_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "2f0b698eb4d8_add_fermentation_records_table.py"
)
BATCH_ACTUALS_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "a3f8c2d1b4e7_add_fermentation_batch_actuals.py"
)
MONTH_SETTINGS_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "b7c9e1f4a6d8_add_fermentation_month_settings.py"
)
PRODUCT_CODE_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "c2f5a8d3e7b1_add_product_code_to_fermentation_tables.py"
)
MERGE_HEADS_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "957e2da4f7c7_merge_fermentation_product_and_.py"
)


def _load_fermentation_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "fermentation_records_migration",
        FERMENTATION_MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migration(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_inspect(has_table: bool) -> Any:
    """构造 sa.inspect 返回的假 inspector，带 has_table 结果。"""

    class _Inspector:
        def has_table(self, table_name: str, schema: str | None) -> bool:
            return has_table

    return _Inspector()


def _record_created_table(target: list[str], value: Any) -> None:
    target.append(str(value))


def _record_dropped_table(
    target: list[tuple[str, str]], table: Any, schema: Any
) -> None:
    target.append((str(table), schema))


def _record_created_index(
    target: list[tuple[str, str, list[str], bool]],
    name: Any,
    table: Any,
    columns: Any,
    unique: Any,
) -> None:
    target.append((str(name), str(table), columns, bool(unique)))


def _record_dropped_index(
    target: list[tuple[str, str, str]], name: Any, table: Any, schema: Any
) -> None:
    target.append((str(name), str(table), schema))


def test_fermentation_migration_upgrade_drops_existing_and_creates_table(
    monkeypatch: Any,
) -> None:
    migration = _load_fermentation_migration()
    created_tables: list[str] = []
    dropped_tables: list[tuple[str, str]] = []
    created_indexes: list[tuple[str, str, list[str], bool]] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    # 让 sa.inspect(conn) 返回一个带 has_table 结果的假 inspector。
    monkeypatch.setattr(sa, "inspect", lambda conn: _fake_inspect(has_table=True))
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda *args, **kwargs: _record_created_table(created_tables, args[0]),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: _record_dropped_table(
            dropped_tables, table, k.get("schema")
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, **kwargs: _record_created_index(
            created_indexes, name, table, columns, kwargs.get("unique")
        ),
    )

    migration.upgrade()

    assert "fermentation_records" in created_tables
    assert ("fermentation_records", "production") in dropped_tables
    assert {index[0] for index in created_indexes} == {
        "ix_fermentation_records_batch_no",
        "ix_fermentation_records_product_name",
    }
    assert all(  # noqa: E501
        index[2] in (["batch_no"], ["product_name"])
        for index in created_indexes  # noqa: E501
    )


def test_fermentation_migration_upgrade_does_not_drop_when_table_missing(
    monkeypatch: Any,
) -> None:
    migration = _load_fermentation_migration()
    dropped_tables: list[tuple[str, str]] = []
    created_tables: list[str] = []

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(sa, "inspect", lambda conn: _fake_inspect(has_table=False))
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: _record_dropped_table(
            dropped_tables, table, k.get("schema")
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda *args, **kwargs: _record_created_table(created_tables, args[0]),
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
    monkeypatch: Any,
) -> None:
    migration = _load_fermentation_migration()
    dropped_indexes: list[tuple[str, str, str]] = []
    dropped_tables: list[tuple[str, str]] = []

    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, table_name, **kw: _record_dropped_index(
            dropped_indexes, name, table_name, kw.get("schema")
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: _record_dropped_table(
            dropped_tables, table, k.get("schema")
        ),
    )

    migration.downgrade()

    assert dropped_indexes == [
        ("ix_fermentation_records_product_name", "fermentation_records", "production"),
        ("ix_fermentation_records_batch_no", "fermentation_records", "production"),
    ]
    assert dropped_tables == [("fermentation_records", "production")]


def _record_created_table_with_schema(
    target: list[tuple[str, Any]], value: Any, **kwargs: Any
) -> None:
    target.append((str(value), kwargs.get("schema")))


def _record_created_partial_index(
    target: list[dict[str, Any]],
    name: Any,
    table: Any,
    columns: Any,
    **kwargs: Any,
) -> None:
    target.append(
        {
            "name": str(name),
            "table": str(table),
            "columns": list(columns),
            "unique": bool(kwargs.get("unique")),
            "partial": kwargs.get("postgresql_where") is not None,
            "schema": kwargs.get("schema"),
        }
    )


def _run_board_setting_migration(
    monkeypatch: Any, path: Path, module_name: str
) -> tuple[Any, list[tuple[str, Any]], list[dict[str, Any]], list[Any], list[Any]]:
    """执行迁移的 upgrade+downgrade，返回模块与各 op 调用记录。"""
    migration = _load_migration(path, module_name)
    created_tables: list[tuple[str, Any]] = []
    created_indexes: list[dict[str, Any]] = []
    dropped_indexes: list[Any] = []
    dropped_tables: list[Any] = []

    monkeypatch.setattr(
        migration.op,
        "create_table",
        lambda *args, **kwargs: _record_created_table_with_schema(
            created_tables, args[0], **kwargs
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, **kwargs: _record_created_partial_index(
            created_indexes, name, table, columns, **kwargs
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, table_name, **kw: dropped_indexes.append((str(name), table_name)),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_table",
        lambda table, *a, **k: dropped_tables.append((str(table), k.get("schema"))),
    )

    migration.upgrade()
    migration.downgrade()
    return migration, created_tables, created_indexes, dropped_indexes, dropped_tables


def test_batch_actuals_migration_creates_table_and_partial_unique_index(
    monkeypatch: Any,
) -> None:
    _, created_tables, created_indexes, _, _ = _run_board_setting_migration(
        monkeypatch,
        BATCH_ACTUALS_MIGRATION_PATH,
        "fermentation_batch_actuals_migration",
    )

    assert created_tables == [("fermentation_batch_actuals", "production")]
    assert created_indexes == [
        {
            "name": "ux_fermentation_batch_actuals_batch_no",
            "table": "fermentation_batch_actuals",
            "columns": ["batch_no"],
            "unique": True,
            "partial": True,
            "schema": "production",
        }
    ]


def test_month_settings_migration_creates_table_and_partial_unique_index(
    monkeypatch: Any,
) -> None:
    _, created_tables, created_indexes, _, _ = _run_board_setting_migration(
        monkeypatch,
        MONTH_SETTINGS_MIGRATION_PATH,
        "fermentation_month_settings_migration",
    )

    assert created_tables == [("fermentation_month_settings", "production")]
    assert created_indexes == [
        {
            "name": "ux_fermentation_month_settings_period",
            "table": "fermentation_month_settings",
            "columns": ["period_start"],
            "unique": True,
            "partial": True,
            "schema": "production",
        }
    ]


def test_board_setting_migrations_downgrade_drops_index_before_table(
    monkeypatch: Any,
) -> None:
    for path, module_name, table, index in (
        (
            BATCH_ACTUALS_MIGRATION_PATH,
            "fermentation_batch_actuals_migration",
            "fermentation_batch_actuals",
            "ux_fermentation_batch_actuals_batch_no",
        ),
        (
            MONTH_SETTINGS_MIGRATION_PATH,
            "fermentation_month_settings_migration",
            "fermentation_month_settings",
            "ux_fermentation_month_settings_period",
        ),
    ):
        _, _, _, dropped_indexes, dropped_tables = _run_board_setting_migration(
            monkeypatch, path, module_name
        )
        # 先删索引再删表，且都在 production schema 下
        assert dropped_indexes == [(index, table)]
        assert dropped_tables == [(table, "production")]


def test_board_setting_migrations_chain_from_current_head() -> None:
    batch = _load_migration(
        BATCH_ACTUALS_MIGRATION_PATH, "fermentation_batch_actuals_migration"
    )
    month = _load_migration(
        MONTH_SETTINGS_MIGRATION_PATH, "fermentation_month_settings_migration"
    )
    assert batch.revision == "a3f8c2d1b4e7"
    assert batch.down_revision == "c9d400000023"
    assert month.revision == "b7c9e1f4a6d8"
    assert month.down_revision == batch.revision


def test_product_code_migration_adds_columns_and_swaps_unique_indexes(
    monkeypatch: Any,
) -> None:
    """product_code 迁移：三表加列，产量/月设置唯一索引改为产品内唯一。"""
    migration = _load_migration(
        PRODUCT_CODE_MIGRATION_PATH, "fermentation_product_code_migration"
    )
    added_columns: list[tuple[str, str, dict[str, Any]]] = []
    dropped_columns: list[tuple[str, str]] = []
    created_indexes: list[dict[str, Any]] = []
    dropped_indexes: list[str] = []

    def _add_column(
        table: str, column: sa.Column, **kwargs: Any
    ) -> None:
        added_columns.append((table, column.name, kwargs))

    monkeypatch.setattr(migration.op, "add_column", _add_column)
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table, column, **kw: dropped_columns.append((table, column)),
    )
    monkeypatch.setattr(
        migration.op,
        "create_index",
        lambda name, table, columns, **kwargs: _record_created_partial_index(
            created_indexes, name, table, columns, **kwargs
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_index",
        lambda name, table_name, **kw: dropped_indexes.append(str(name)),
    )

    migration.upgrade()
    migration.downgrade()

    # upgrade：三表加 product_code（含 server_default 回填 FA）
    assert [table for table, _, _ in added_columns] == [
        "schedule_excel_archives",
        "fermentation_batch_actuals",
        "fermentation_month_settings",
    ]
    assert all(column == "product_code" for _, column, _ in added_columns)
    # upgrade：唯一索引换成产品内唯一，存档表加普通索引；
    # downgrade：把两条进行中唯一索引换回旧口径（列收窄、索引名还原）
    assert {
        (item["name"], tuple(item["columns"])) for item in created_indexes
    } == {
        ("ix_schedule_excel_archives_product_code", ("product_code",)),
        ("ux_fermentation_batch_actuals_product_batch", ("product_code", "batch_no")),
        ("ux_fermentation_month_settings_period", ("product_code", "period_start")),
        ("ux_fermentation_batch_actuals_batch_no", ("batch_no",)),
        ("ux_fermentation_month_settings_period", ("period_start",)),
    }
    # 部分唯一索引始终只用于两条进行中唯一约束
    assert {
        item["name"] for item in created_indexes if item["partial"]
    } == {
        "ux_fermentation_batch_actuals_product_batch",
        "ux_fermentation_month_settings_period",
        "ux_fermentation_batch_actuals_batch_no",
    }
    # downgrade：先换回旧唯一索引再删列
    assert ("fermentation_batch_actuals", "product_code") in dropped_columns
    assert ("fermentation_month_settings", "product_code") in dropped_columns
    assert ("schedule_excel_archives", "product_code") in dropped_columns


def test_merge_heads_migration_joins_product_and_contact_branches() -> None:
    merge = _load_migration(
        MERGE_HEADS_MIGRATION_PATH, "fermentation_merge_heads_migration"
    )
    assert merge.revision == "957e2da4f7c7"
    assert set(merge.down_revision) == {"c2f5a8d3e7b1", "c9d400000026"}
    # 合并迁移不改变任何结构
    assert merge.upgrade() is None
    assert merge.downgrade() is None
