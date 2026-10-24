"""Helpers shared by hand-written migrations."""

import os
import re

from alembic import op
from sqlalchemy.util import await_only

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def app_role() -> str:
    """Least-privilege role used by the application (PAZ_DATABASE_APP_ROLE)."""
    role = os.environ.get("PAZ_DATABASE_APP_ROLE", "paz_app")
    if not _IDENTIFIER.match(role):
        raise ValueError(f"Invalid PAZ_DATABASE_APP_ROLE: {role!r}")
    return role


def if_role_exists(role: str, statements: str) -> str:
    """Wraps statements so environments without the app role (e.g. bare CI DBs) still migrate."""
    return f"""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
        {statements}
      ELSE
        RAISE NOTICE 'Role {role} does not exist; grants skipped';
      END IF;
    END $$;
    """


def execute_script(sql: str) -> None:
    """Runs a multi-statement SQL script (functions with $$ bodies included) on the migration's
    connection and transaction. asyncpg rejects several commands in one prepared statement, so
    the script goes through the driver's simple-query protocol."""
    driver_connection = op.get_bind().connection.dbapi_connection.driver_connection  # type: ignore[union-attr]
    await_only(driver_connection.execute(sql))
