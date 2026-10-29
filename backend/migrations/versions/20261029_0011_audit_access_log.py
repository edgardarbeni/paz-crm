"""audit: append-only log of sensitive reads, outside the hash chain (D-89)

Design:
- `audit.access_log` is RANGE-partitioned by `occurred_at` (monthly) with a DEFAULT partition,
  like `audit.audit_log`, but it is not hash-chained: reads must not wait on the global
  `audit.chain_head` lock (D-45). Immutability comes from the same triggers and privileges.
- The application role can only EXECUTE `record_access` (SECURITY DEFINER) and SELECT the log.
- It stores who read what and how, never the content that was read.
- `audit.ensure_partitions` now creates the monthly partitions of both tables.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

from migrations.helpers import app_role, execute_script, if_role_exists

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RECORD_SIGNATURE = "uuid, inet, text, text, text, text, text, jsonb"

# The original message named audit_log; with two append-only tables it names the table.
_FORBID_MUTATION = """
CREATE OR REPLACE FUNCTION audit.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit.% is append-only (% rejected)', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END
$$;
"""

_FORBID_MUTATION_0002 = """
CREATE OR REPLACE FUNCTION audit.forbid_mutation() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'audit.audit_log is append-only (% rejected)', TG_OP
    USING ERRCODE = 'insufficient_privilege';
END
$$;
"""

_ENSURE_PARTITIONS = """
CREATE OR REPLACE FUNCTION audit.ensure_partitions(p_months_ahead integer DEFAULT 3)
RETURNS text[]
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_month   timestamp;
  v_name    text;
  v_created text[] := ARRAY[]::text[];
  v_table   text;
BEGIN
  FOREACH v_table IN ARRAY {tables} LOOP
    v_month := date_trunc('month', now() AT TIME ZONE 'UTC');
    FOR i IN 0..p_months_ahead LOOP
      v_name := format('%s_y%sm%s', v_table, to_char(v_month, 'YYYY'), to_char(v_month, 'MM'));
      IF to_regclass(format('audit.%I', v_name)) IS NULL THEN
        EXECUTE format(
          'CREATE TABLE audit.%I PARTITION OF audit.%I FOR VALUES FROM (%L) TO (%L)',
          v_name, v_table, v_month AT TIME ZONE 'UTC',
          (v_month + interval '1 month') AT TIME ZONE 'UTC'
        );
        v_created := v_created || v_name;
      END IF;
      v_month := v_month + interval '1 month';
    END LOOP;
  END LOOP;
  RETURN v_created;
END
$$;
"""


def upgrade() -> None:
    execute_script(
        """
        CREATE TABLE audit.access_log (
          occurred_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
          id            uuid        NOT NULL DEFAULT uuidv7(),
          actor_user_id uuid,
          actor_ip      inet,
          user_agent    text,
          request_id    text,
          action        text        NOT NULL,
          entity_table  text        NOT NULL,
          entity_id     text,
          details       jsonb,
          CONSTRAINT pk_access_log PRIMARY KEY (occurred_at, id)
        ) PARTITION BY RANGE (occurred_at);

        CREATE TABLE audit.access_log_default PARTITION OF audit.access_log DEFAULT;

        CREATE INDEX ix_access_log_entity ON audit.access_log (entity_table, entity_id, occurred_at);
        CREATE INDEX ix_access_log_actor_user_id ON audit.access_log (actor_user_id, occurred_at);

        CREATE FUNCTION audit.record_access(
          p_actor uuid, p_ip inet, p_user_agent text, p_request_id text, p_action text,
          p_entity_table text, p_entity_id text, p_details jsonb
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
          IF p_action IS NULL OR length(p_action) = 0 OR p_entity_table IS NULL THEN
            RAISE EXCEPTION 'access action and entity table are required';
          END IF;
          INSERT INTO audit.access_log (actor_user_id, actor_ip, user_agent, request_id, action,
                                        entity_table, entity_id, details)
          VALUES (p_actor, p_ip, p_user_agent, p_request_id, p_action, p_entity_table,
                  p_entity_id, p_details);
        END
        $$;

        CREATE TRIGGER trg_access_log_forbid_update_delete
          BEFORE UPDATE OR DELETE ON audit.access_log
          FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();
        CREATE TRIGGER trg_access_log_forbid_truncate
          BEFORE TRUNCATE ON audit.access_log
          FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation();
        """
    )
    execute_script(_FORBID_MUTATION)
    execute_script(_ENSURE_PARTITIONS.format(tables="ARRAY['audit_log', 'access_log']"))
    execute_script(
        f"""
        SELECT audit.ensure_partitions(3);
        REVOKE ALL ON audit.access_log FROM PUBLIC;
        REVOKE ALL ON FUNCTION audit.record_access({RECORD_SIGNATURE}) FROM PUBLIC;
        REVOKE ALL ON FUNCTION audit.ensure_partitions(integer) FROM PUBLIC;
        """
    )
    role = app_role()
    op.execute(
        if_role_exists(
            role,
            f"""
            GRANT SELECT ON audit.access_log TO {role};
            GRANT EXECUTE ON FUNCTION audit.record_access({RECORD_SIGNATURE}) TO {role};
            """,
        )
    )


def downgrade() -> None:
    execute_script(_FORBID_MUTATION_0002)
    execute_script(_ENSURE_PARTITIONS.format(tables="ARRAY['audit_log']"))
    execute_script(
        f"""
        REVOKE ALL ON FUNCTION audit.ensure_partitions(integer) FROM PUBLIC;
        DROP TABLE IF EXISTS audit.access_log CASCADE;
        DROP FUNCTION IF EXISTS audit.record_access({RECORD_SIGNATURE});
        """
    )
