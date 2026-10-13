import asyncio
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models.listing  # noqa: F401  (register tables on Base.metadata)
import app.models.scrape_run  # noqa: F401
from app.config import settings
from app.database import Base

config = context.config
if config.config_file_name is not None and not config.attributes.get("connection"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The URL always comes from app settings (DATABASE_URL env var / .env) so the
# CLI and the app can't disagree about which database they're migrating.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def _compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    # Columns added by hand with ALTER TABLE ... REAL report as REAL, while
    # sa.Float renders FLOAT. Same storage affinity in SQLite — not drift.
    if isinstance(metadata_type, sa.Float) and type(inspected_type).__name__.upper() in ("REAL", "FLOAT"):
        return False
    return None  # fall back to Alembic's default comparison


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        # SQLite can't ALTER most things in place; batch mode recreates the
        # table behind the scenes so column changes work there too.
        render_as_batch=True,
        compare_type=_compare_type,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    # When the app runs migrations at startup it hands us a sync connection
    # (via AsyncConnection.run_sync) — we're already inside an event loop
    # there, so asyncio.run() would fail.
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
