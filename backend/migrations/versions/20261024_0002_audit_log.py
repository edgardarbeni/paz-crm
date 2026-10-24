"""audit: immutable, hash-chained audit log partitioned by month (D-37)

Design:
- `audit.audit_log` is RANGE-partitioned by `occurred_at` (monthly) with a DEFAULT partition
  so inserts never fail if `ensure_partitions` was not run in time.
- `audit.chain_head` is a single row holding the last sequence and hash. `append_entry` locks
  it (FOR UPDATE), which serializes chain writes system-wide until the caller commits.
- The application role can only EXECUTE `append_entry` (SECURITY DEFINER) and SELECT the log.
  Row triggers reject UPDATE/DELETE and a statement trigger rejects TRUNCATE for every role.
- `verify_chain` recomputes hashes, detects gaps (deleted rows) and a truncated tail.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

from migrations.helpers import app_role, execute_script, if_role_exists

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_SIGNATURE = "uuid, inet, text, text, text, text, text, jsonb, jsonb"


def upgrade() -> None:
    execute_script(
        """
        CREATE FUNCTION audit.genesis_hash() RETURNS bytea
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$ SELECT sha256(convert_to('pazos-audit-genesis', 'UTF8')) $$;

        CREATE TABLE audit.chain_head (
          id        boolean PRIMARY KEY DEFAULT true,
          last_seq  bigint  NOT NULL,
          last_hash bytea   NOT NULL,
          CONSTRAINT ck_chain_head_single_row CHECK (id)
        );
        INSERT INTO audit.chain_head (id, last_seq, last_hash) VALUES (true, 0, audit.genesis_hash());

        CREATE TABLE audit.audit_log (
          occurred_at   timestamptz NOT NULL,
          id            uuid        NOT NULL,
          chain_seq     bigint      NOT NULL,
          actor_user_id uuid,
          actor_ip      inet,
          user_agent    text,
          request_id    text,
          action        text        NOT NULL,
          entity_table  text,
          entity_id     text,
          before        jsonb,
          after         jsonb,
          prev_hash     bytea       NOT NULL,
          entry_hash    bytea       NOT NULL,
          CONSTRAINT pk_audit_log PRIMARY KEY (occurred_at, id)
        ) PARTITION BY RANGE (occurred_at);

        CREATE TABLE audit.audit_log_default PARTITION OF audit.audit_log DEFAULT;

        CREATE INDEX ix_audit_log_chain_seq ON audit.audit_log (chain_seq);
        CREATE INDEX ix_audit_log_entity ON audit.audit_log (entity_table, entity_id, occurred_at);
        CREATE INDEX ix_audit_log_actor_user_id ON audit.audit_log (actor_user_id, occurred_at);
        CREATE INDEX ix_audit_log_request_id ON audit.audit_log (request_id);

        -- Canonical digest. Time is hashed as integer microseconds since epoch so the result
        -- does not depend on the session TimeZone; NULLs are encoded explicitly as \\N.
        CREATE FUNCTION audit.entry_digest(
          p_prev bytea, p_seq bigint, p_id uuid, p_occurred_at timestamptz, p_actor uuid,
          p_ip inet, p_user_agent text, p_request_id text, p_action text, p_entity_table text,
          p_entity_id text, p_before jsonb, p_after jsonb
        ) RETURNS bytea
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$
          SELECT sha256(p_prev || convert_to(concat_ws(E'\\x1f',
            p_seq::text,
            p_id::text,
            (extract(epoch FROM p_occurred_at) * 1000000)::bigint::text,
            coalesce(p_actor::text, '\\N'),
            coalesce(host(p_ip), '\\N'),
            coalesce(p_user_agent, '\\N'),
            coalesce(p_request_id, '\\N'),
            p_action,
            coalesce(p_entity_table, '\\N'),
            coalesce(p_entity_id, '\\N'),
            coalesce(p_before::text, '\\N'),
            coalesce(p_after::text, '\\N')
          ), 'UTF8'))
        $$;

        CREATE FUNCTION audit.append_entry(
          p_actor uuid, p_ip inet, p_user_agent text, p_request_id text, p_action text,
          p_entity_table text, p_entity_id text, p_before jsonb, p_after jsonb
        ) RETURNS bigint
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
          v_seq  bigint;
          v_prev bytea;
          v_id   uuid := uuidv7();
          v_at   timestamptz;
          v_hash bytea;
        BEGIN
          IF p_action IS NULL OR length(p_action) = 0 THEN
            RAISE EXCEPTION 'audit action is required';
          END IF;

          SELECT last_seq + 1, last_hash INTO v_seq, v_prev
            FROM audit.chain_head WHERE id FOR UPDATE;
          v_at := clock_timestamp();  -- taken after the lock, so time follows the sequence

          v_hash := audit.entry_digest(v_prev, v_seq, v_id, v_at, p_actor, p_ip, p_user_agent,
                                       p_request_id, p_action, p_entity_table, p_entity_id,
                                       p_before, p_after);

          INSERT INTO audit.audit_log (occurred_at, id, chain_seq, actor_user_id, actor_ip,
                                       user_agent, request_id, action, entity_table, entity_id,
                                       before, after, prev_hash, entry_hash)
          VALUES (v_at, v_id, v_seq, p_actor, p_ip, p_user_agent, p_request_id, p_action,
                  p_entity_table, p_entity_id, p_before, p_after, v_prev, v_hash);

          UPDATE audit.chain_head SET last_seq = v_seq, last_hash = v_hash WHERE id;
          RETURN v_seq;
        END
        $$;

        CREATE FUNCTION audit.verify_chain(p_from_seq bigint DEFAULT 1)
        RETURNS TABLE (checked bigint, first_broken_seq bigint)
        LANGUAGE plpgsql STABLE
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
          r          record;
          v_prev     bytea;
          v_expected bigint := p_from_seq;
          v_count    bigint := 0;
          v_head     bigint;
        BEGIN
          IF p_from_seq <= 1 THEN
            v_prev := audit.genesis_hash();
            v_expected := 1;
          ELSE
            SELECT l.entry_hash INTO v_prev FROM audit.audit_log l WHERE l.chain_seq = p_from_seq - 1;
            IF v_prev IS NULL THEN
              RETURN QUERY SELECT 0::bigint, p_from_seq - 1;
              RETURN;
            END IF;
          END IF;

          FOR r IN SELECT * FROM audit.audit_log l WHERE l.chain_seq >= v_expected
                   ORDER BY l.chain_seq LOOP
            IF r.chain_seq <> v_expected
               OR r.prev_hash <> v_prev
               OR r.entry_hash <> audit.entry_digest(r.prev_hash, r.chain_seq, r.id, r.occurred_at,
                                                     r.actor_user_id, r.actor_ip, r.user_agent,
                                                     r.request_id, r.action, r.entity_table,
                                                     r.entity_id, r.before, r.after) THEN
              RETURN QUERY SELECT v_count, v_expected;
              RETURN;
            END IF;
            v_prev := r.entry_hash;
            v_expected := v_expected + 1;
            v_count := v_count + 1;
          END LOOP;

          SELECT h.last_seq INTO v_head FROM audit.chain_head h WHERE h.id;
          IF v_head <> v_expected - 1 THEN
            RETURN QUERY SELECT v_count, v_expected;  -- rows missing at the tail
            RETURN;
          END IF;
          RETURN QUERY SELECT v_count, NULL::bigint;
        END
        $$;

        CREATE FUNCTION audit.forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'audit.audit_log is append-only (% rejected)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
        END
        $$;

        CREATE TRIGGER trg_audit_log_forbid_update_delete
          BEFORE UPDATE OR DELETE ON audit.audit_log
          FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation();
        CREATE TRIGGER trg_audit_log_forbid_truncate
          BEFORE TRUNCATE ON audit.audit_log
          FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation();
        CREATE TRIGGER trg_chain_head_forbid_delete
          BEFORE DELETE OR TRUNCATE ON audit.chain_head
          FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_mutation();

        -- Monthly partitions [month, next month) in UTC. Returns the names it created.
        CREATE FUNCTION audit.ensure_partitions(p_months_ahead integer DEFAULT 3)
        RETURNS text[]
        LANGUAGE plpgsql
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
          v_month   timestamp := date_trunc('month', now() AT TIME ZONE 'UTC');
          v_name    text;
          v_created text[] := ARRAY[]::text[];
        BEGIN
          FOR i IN 0..p_months_ahead LOOP
            v_name := format('audit_log_y%sm%s', to_char(v_month, 'YYYY'), to_char(v_month, 'MM'));
            IF to_regclass(format('audit.%I', v_name)) IS NULL THEN
              EXECUTE format(
                'CREATE TABLE audit.%I PARTITION OF audit.audit_log FOR VALUES FROM (%L) TO (%L)',
                v_name, v_month AT TIME ZONE 'UTC', (v_month + interval '1 month') AT TIME ZONE 'UTC'
              );
              v_created := v_created || v_name;
            END IF;
            v_month := v_month + interval '1 month';
          END LOOP;
          RETURN v_created;
        END
        $$;

        SELECT audit.ensure_partitions(3);
        """
    )

    execute_script(
        f"""
        REVOKE ALL ON ALL TABLES IN SCHEMA audit FROM PUBLIC;
        REVOKE ALL ON FUNCTION audit.append_entry({APPEND_SIGNATURE}) FROM PUBLIC;
        REVOKE ALL ON FUNCTION audit.ensure_partitions(integer) FROM PUBLIC;
        """
    )
    role = app_role()
    op.execute(
        if_role_exists(
            role,
            f"""
            GRANT USAGE ON SCHEMA audit TO {role};
            GRANT SELECT ON audit.audit_log, audit.chain_head TO {role};
            GRANT EXECUTE ON FUNCTION audit.append_entry({APPEND_SIGNATURE}) TO {role};
            GRANT EXECUTE ON FUNCTION audit.verify_chain(bigint) TO {role};
            """,
        )
    )


def downgrade() -> None:
    execute_script(
        f"""
        DROP FUNCTION IF EXISTS audit.ensure_partitions(integer);
        DROP TABLE IF EXISTS audit.audit_log CASCADE;
        DROP TABLE IF EXISTS audit.chain_head CASCADE;
        DROP FUNCTION IF EXISTS audit.forbid_mutation();
        DROP FUNCTION IF EXISTS audit.verify_chain(bigint);
        DROP FUNCTION IF EXISTS audit.append_entry({APPEND_SIGNATURE});
        DROP FUNCTION IF EXISTS audit.entry_digest(
          bytea, bigint, uuid, timestamptz, uuid, inet, text, text, text, text, text, jsonb, jsonb);
        DROP FUNCTION IF EXISTS audit.genesis_hash();
        """
    )
