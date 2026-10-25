"""core: extensions, module schemas, app-role grants and helper functions

Revision ID: 0001
Revises:
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

from migrations.helpers import app_role, if_role_exists

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODULE_SCHEMAS = ("identity", "geography", "people", "candidacies")
EXTENSIONS = ("postgis", "pg_trgm", "unaccent", "citext")


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension} WITH SCHEMA public")

    for schema in (*MODULE_SCHEMAS, "audit"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        op.execute(f"REVOKE ALL ON SCHEMA {schema} FROM PUBLIC")

    # unaccent() is STABLE; this IMMUTABLE wrapper allows expression/trigram indexes on names.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.f_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )

    role = app_role()
    grants = "\n".join(
        f"""
        GRANT USAGE ON SCHEMA {schema} TO {role};
        ALTER DEFAULT PRIVILEGES IN SCHEMA {schema}
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role};
        ALTER DEFAULT PRIVILEGES IN SCHEMA {schema}
          GRANT USAGE, SELECT ON SEQUENCES TO {role};
        """
        for schema in MODULE_SCHEMAS
    )
    op.execute(if_role_exists(role, grants))


def downgrade() -> None:
    role = app_role()
    revokes = "\n".join(
        f"""
        ALTER DEFAULT PRIVILEGES IN SCHEMA {schema}
          REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {role};
        ALTER DEFAULT PRIVILEGES IN SCHEMA {schema}
          REVOKE USAGE, SELECT ON SEQUENCES FROM {role};
        """
        for schema in MODULE_SCHEMAS
    )
    op.execute(if_role_exists(role, revokes))
    op.execute("DROP FUNCTION IF EXISTS public.f_unaccent(text)")
    for schema in (*MODULE_SCHEMAS, "audit"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    # Extensions are left installed: other databases objects may depend on them.
