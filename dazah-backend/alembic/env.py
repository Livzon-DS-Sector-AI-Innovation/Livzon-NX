from collections.abc import MutableMapping
from importlib import import_module
from logging.config import fileConfig
from typing import Literal

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


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
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
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
