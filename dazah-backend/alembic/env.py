from collections.abc import MutableMapping
from importlib import import_module
from logging.config import fileConfig
from typing import Any, Literal

from alembic import context
from app.core.config import get_settings
from app.shared.base_model import Base
from app.shared.module_registry import BUSINESS_MODULES, BUSINESS_SCHEMAS

# Import platform and module models so Alembic can detect them.
import_module("app.platform.audit.models")
import_module("app.platform.identity.models")
import_module("app.core.llm.config")
import_module("app.modules.agent.models")
for module in BUSINESS_MODULES:
    import_module(f"app.modules.{module.code}.models")

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

PROJECT_SCHEMAS = frozenset(("identity", "audit", "core", *BUSINESS_SCHEMAS))
AUDIT_USER_COLUMNS = frozenset(("created_by", "updated_by"))
LEGACY_SERVER_DEFAULT_COLUMNS = frozenset(
    {
        ("core", "agent_domain_events", "occurred_at"),
        ("production", "feishu_read_records", "synced_at"),
        ("production", "feishu_read_sync_runs", "started_at"),
        ("production", "feishu_sync_bindings", "field_mapping"),
        ("production", "feishu_sync_runs", "started_at"),
        ("production", "migration_runs", "inserted_count"),
        ("production", "migration_runs", "updated_count"),
        ("production", "migration_runs", "skipped_count"),
        ("production", "migration_runs", "failed_count"),
        ("production", "migration_runs", "report"),
        ("production", "process_execution_records", "recorded_at"),
        ("production", "process_execution_records", "data"),
        ("production", "ceramic_equipment_logs", "workshop"),
        ("production", "ceramic_material_separations", "workshop"),
        ("production", "ceramic_membrane_cleans", "workshop"),
        ("production", "ceramic_membrane_ops", "workshop"),
        ("quality", "feishu_read_records", "synced_at"),
        ("quality", "feishu_read_sync_runs", "started_at"),
        ("warehouse", "feishu_tables", "business_domain"),
    }
)


def include_name(
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    ],
    parent_names: MutableMapping[
        Literal["schema_name", "table_name", "schema_qualified_table_name"],
        str | None,
    ],
) -> bool:
    """Limit autogenerate to schemas owned by this application."""
    if type_ == "schema":
        return name in PROJECT_SCHEMAS
    if type_ == "table":
        return parent_names.get("schema_name") in PROJECT_SCHEMAS
    return True


def include_object(
    object_: Any,
    name: str | None,
    type_: Literal[
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    ],
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Keep autogenerate additive and respect module ownership boundaries.

    Existing database-only indexes and constraints may encode production data
    guarantees that are not represented by SQLAlchemy models. Their removal must
    therefore be written as an explicit reviewed migration, never inferred by
    autogenerate.

    Audit user IDs are cross-module references. The ORM uses ForeignKey metadata
    for relationship resolution, but new database constraints are intentionally
    omitted so business schemas do not become coupled to ``identity.users``.
    """
    # The migration policy for this application is additive. Existing
    # columns (including legacy/source-only fields) are never removed or
    # altered implicitly by autogenerate; metadata-only columns remain visible
    # so reviewed additions are still detected.
    if type_ == "column" and (reflected or compare_to is not None):
        return False

    if (
        reflected
        and compare_to is None
        and type_
        in {
            "foreign_key_constraint",
            "index",
            "unique_constraint",
        }
    ):
        return False

    if (
        not reflected
        and compare_to is None
        and type_ == "foreign_key_constraint"
        and {column.name for column in object_.columns} <= AUDIT_USER_COLUMNS
    ):
        return False

    # 血链表与收发任务表由 fa/mc lineage 模块以原生 SQL 即时创建并引用，
    # 无 ORM 模型（仅 SQLAlchemy text() 访问）。量纲漂移时不应自动施加移除。
    if (
        type_ == "table"
        and reflected
        and object_.name
        in {
            "batch_lineage",
            "fa_batch_lineage",
            "receiving_task",
            "fa_intermediate_records",
        }
        and object_.schema == "production"
    ):
        return False

    return True


def compare_server_default(
    _context: Any,
    inspected_column: Any,
    _metadata_column: Any,
    _rendered_inspected_default: str | None,
    _metadata_default: Any,
    _rendered_metadata_default: str | None,
) -> bool | None:
    """Ignore known historical defaults while detecting new default drift."""
    column_key = (
        inspected_column.table.schema,
        inspected_column.table.name,
        inspected_column.name,
    )
    if column_key in LEGACY_SERVER_DEFAULT_COLUMNS:
        return False
    return None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        compare_type=False,
        compare_server_default=False,
        compare_comments=False,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    # Preserve escaped credentials while switching Alembic's synchronous driver.
    # Re-parsing and manually quoting the password corrupts credentials containing
    # reserved URL characters even though the async application connection works.
    sync_url = make_url(settings.DATABASE_URL).set(drivername="postgresql+pg8000")

    engine = create_engine(
        sync_url,
        poolclass=NullPool,
        pool_pre_ping=True,
    )

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_name=include_name,
            include_object=include_object,
            compare_type=False,
            compare_server_default=False,
            compare_comments=False,
        )
        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
