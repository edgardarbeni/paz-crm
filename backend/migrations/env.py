"""Alembic environment (async). Runs with the database *owner* role
(PAZ_MIGRATIONS_DATABASE_URL); the application connects with the least-privilege role."""

import asyncio
import os
import re
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401 - registers every table model on the metadata
from app.core.config import as_asyncpg_url
from app.core.db.base import metadata
from app.core.modules import managed_schemas

# Objects managed by hand-written SQL migrations, invisible to autogenerate.
_UNMANAGED_SCHEMAS = {"audit"}
# Each module declares its schema in `module.py` (`app.core.modules`).
_MANAGED_SCHEMAS = managed_schemas()


def include_name(name: str | None, type_: str, _: dict[str, Any]) -> bool:
    if type_ == "schema":
        return name in _MANAGED_SCHEMAS
    return True


# Runtime partitions (one per framework, D-14) and their indexes are not part of the models.
_RUNTIME_PARTITION = re.compile(r"^blocks_[0-9a-f]{32}")


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    table = obj if type_ == "table" else getattr(obj, "table", None)
    schema = getattr(table, "schema", None) or getattr(obj, "schema", None)
    if schema in _UNMANAGED_SCHEMAS:
        return False
    table_name = getattr(table, "name", "") or ""
    return not (reflected and _RUNTIME_PARTITION.match(table_name))


def migrations_url() -> str:
    """Only the owner URL is needed to migrate; application secrets are not required."""
    url = os.environ.get("PAZ_MIGRATIONS_DATABASE_URL") or os.environ.get("PAZ_DATABASE_URL")
    if not url:
        raise RuntimeError("Set PAZ_MIGRATIONS_DATABASE_URL to run migrations")
    return as_asyncpg_url(url)


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=metadata,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        version_table_schema="public",
        transaction_per_migration=True,
    )


def run_migrations_offline() -> None:
    _configure(url=migrations_url())
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = context.config.attributes.get("database_url") or migrations_url()
    engine = create_async_engine(url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
