#!/bin/bash
# DDL test of the reference DDL (ddl/) and the widget fixture's migration, in throwaway PostgreSQL
# containers: PostgreSQL 14 (the standalone floor, P10.7) and 16 (the shell floor, P19.5).
#
#   scripts/ddltest.sh                      # both versions
#   PG_IMAGES="postgres:16-alpine" scripts/ddltest.sh
#   DDLTEST_PREFIX=my-prefix scripts/ddltest.sh   # container name prefix (default be-protocol-ddltest)
#
# Each container runs on tmpfs, publishes no port and is removed on exit. Any failed statement,
# or any check below that does not hold, stops the run with a non-zero exit.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=${DDLTEST_PREFIX:-be-protocol-ddltest}
IMAGES=${PG_IMAGES:-"postgres:14-alpine postgres:16-alpine"}
STARTED=()
cleanup() { for c in "${STARTED[@]:-}"; do [ -n "$c" ] && docker rm -f "$c" >/dev/null 2>&1 || true; done; }
trap cleanup EXIT

run_one() {
  local image=$1 c=$2
  docker run -d --rm --name "$c" -e POSTGRES_PASSWORD=x --tmpfs /var/lib/postgresql/data "$image" >/dev/null
  STARTED+=("$c")
  for _ in $(seq 1 60); do docker exec "$c" pg_isready -U postgres -q 2>/dev/null && break; sleep 1; done
  sleep 1
  docker exec "$c" mkdir -p /t
  docker cp "$ROOT/ddl" "$c:/t/ddl" >/dev/null
  docker cp "$ROOT/fixtures/widget/migrations/0001_widget.sql" "$c:/t/0001_widget.sql" >/dev/null
  local P="docker exec -i -e PGOPTIONS=-cclient_min_messages=warning $c psql -U postgres -v ON_ERROR_STOP=1 -q -X -o /dev/null"
  local major
  major=$(docker exec "$c" psql -U postgres -tAX -c "SELECT current_setting('server_version_num')::int / 10000")

  # roles and schemas, the way the project's database initialisation creates them (P10, roles table)
  $P <<'SQL'
CREATE ROLE r_owner LOGIN PASSWORD 'x';        -- PG_OWNER_USER: owns tables, runs DDL
CREATE ROLE r_widget LOGIN PASSWORD 'x';       -- PG_USER: DML only, not a member of r_owner
CREATE SCHEMA s_widget;                        -- owned by postgres, as the initialisation does
CREATE SCHEMA s_fixture;
GRANT USAGE, CREATE ON SCHEMA s_widget, s_fixture TO r_owner;
GRANT USAGE ON SCHEMA s_widget, s_fixture TO r_widget;
ALTER DEFAULT PRIVILEGES FOR ROLE r_owner IN SCHEMA s_widget, s_fixture GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO r_widget;
ALTER DEFAULT PRIVILEGES FOR ROLE r_owner IN SCHEMA s_widget, s_fixture GRANT USAGE, SELECT ON SEQUENCES TO r_widget;
SQL

  # the platform migration, twice (idempotent, P1.1), as the owner, unqualified names (P11.2)
  for run in 1 2; do
    { echo "BEGIN; SET LOCAL ROLE r_owner; SET LOCAL search_path TO s_widget;"
      for f in $(cd "$ROOT/ddl" && ls [0-9]*.sql | sort); do echo "\\i /t/ddl/$f"; done
      echo "CREATE TABLE IF NOT EXISTS ddl_probe (id uuid NOT NULL, created_at timestamptz NOT NULL, name text NOT NULL, PRIMARY KEY (id, created_at)) PARTITION BY RANGE (created_at);"
      echo "COMMIT;"; } | $P
  done
  # the widget fixture's own migration, then the platform migration, in a second schema
  { echo "BEGIN; SET LOCAL ROLE r_owner; SET LOCAL search_path TO s_fixture;"
    echo "\\i /t/0001_widget.sql"
    for f in $(cd "$ROOT/ddl" && ls [0-9]*.sql | sort); do echo "\\i /t/ddl/$f"; done
    echo "COMMIT;"; } | $P
  # be_bus, created by the project's database initialisation (superuser), twice
  $P -f /t/ddl/be_bus.sql; $P -f /t/ddl/be_bus.sql

  # every observe.sql of the widget's fixtures file prepares against the widget schema
  {
    echo "BEGIN; SET LOCAL ROLE r_widget; SET LOCAL search_path TO s_fixture;"
    i=0
    grep -o 'sql: "[^"]*"' "$ROOT/fixtures/widget/conformance/fixtures.yaml" | sed 's/^sql: "//; s/"$//' | while IFS= read -r q; do
      i=$((i + 1)); echo "PREPARE observe_$i AS $q;"
    done
    echo "COMMIT;"; } | $P

  $P <<'SQL'
BEGIN; SET LOCAL ROLE r_widget; SET LOCAL search_path TO s_widget;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 's_widget' AND tableowner <> 'r_owner') THEN
    RAISE EXCEPTION 'a table is not owned by the owner role'; END IF;
  IF NOT has_schema_privilege(current_user, current_schema(), 'USAGE') OR has_schema_privilege(current_user, current_schema(), 'CREATE')
     OR pg_has_role(current_user, 'r_owner', 'MEMBER') THEN
    RAISE EXCEPTION 'runtime identity probe (P10.7) does not hold'; END IF;
END $$;
SAVEPOINT ddl;
DO $$ BEGIN CREATE TABLE should_fail (x int); RAISE EXCEPTION 'runtime could create a table';
EXCEPTION WHEN insufficient_privilege THEN NULL; END $$;
ROLLBACK TO ddl;
-- partitions through the definer function, idempotent
DO $$ BEGIN
  IF NOT besdk_ensure_range_partition('besdk_outbox', 'besdk_outbox_2026w40', '2026-09-28', '2026-10-05') THEN RAISE EXCEPTION 'create'; END IF;
  IF besdk_ensure_range_partition('besdk_outbox', 'besdk_outbox_2026w40', '2026-09-28', '2026-10-05') THEN RAISE EXCEPTION 'not idempotent'; END IF;
  PERFORM besdk_ensure_range_partition('besdk_outbox', 'besdk_outbox_2026w41', '2026-10-05', '2026-10-12');
END $$;
-- outbox insert and claim (P12.1)
INSERT INTO besdk_outbox (id, created_at, subject, aggregate_type, aggregate_id, aggregate_version, occurred_at, payload)
VALUES ('0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a60', '2026-10-02T10:00:00Z', 'conformance.widget.created.v1', 'conformance.widget.widget', 'w1', 1, now(), '{}');
DO $$ DECLARE n int; BEGIN
  WITH c AS (UPDATE besdk_outbox SET status = 'SENDING', claimed_until = now() + interval '30 seconds', attempts = attempts + 1
     WHERE (id, created_at) IN (SELECT id, created_at FROM besdk_outbox
            WHERE (status = 'PENDING' AND next_attempt_at <= now()) OR (status = 'SENDING' AND claimed_until < now())
            ORDER BY created_at, id LIMIT 256 FOR UPDATE SKIP LOCKED) RETURNING 1) SELECT count(*) INTO n FROM c;
  IF n <> 1 THEN RAISE EXCEPTION 'outbox claim returned %', n; END IF;
END $$;
-- cursor upsert: v2 applies, v1 is skipped (P12.6)
DO $$ DECLARE n int; BEGIN
  WITH u AS (INSERT INTO besdk_event_cursor (consumer, aggregate_type, aggregate_id, version, event_id) VALUES ('', 't', 'a', 2, 'e2')
    ON CONFLICT (consumer, aggregate_type, aggregate_id) DO UPDATE SET version = EXCLUDED.version, event_id = EXCLUDED.event_id, seen_at = now()
    WHERE besdk_event_cursor.version < EXCLUDED.version RETURNING 1) SELECT count(*) INTO n FROM u;
  IF n <> 1 THEN RAISE EXCEPTION 'cursor v2'; END IF;
  WITH u AS (INSERT INTO besdk_event_cursor (consumer, aggregate_type, aggregate_id, version, event_id) VALUES ('', 't', 'a', 1, 'e1')
    ON CONFLICT (consumer, aggregate_type, aggregate_id) DO UPDATE SET version = EXCLUDED.version, event_id = EXCLUDED.event_id, seen_at = now()
    WHERE besdk_event_cursor.version < EXCLUDED.version RETURNING 1) SELECT count(*) INTO n FROM u;
  IF n <> 0 THEN RAISE EXCEPTION 'cursor v1 applied over v2'; END IF;
END $$;
-- idempotency claim (P13), job lease, cron slot, queue unique key, reconciler claim (P14)
INSERT INTO besdk_idempotency (caller, idempotency_key, command, target, request_hash, status, expires_at)
VALUES ('user:u1', 'k1', 'conformance.widget.create', '', '\x00', 'CLAIMED', now() + interval '30 days') ON CONFLICT (caller, idempotency_key) DO NOTHING;
INSERT INTO besdk_job_lease (name, holder, expires_at) VALUES ('be.lifecycle', 'x/0', now() - interval '1s') ON CONFLICT DO NOTHING;
UPDATE besdk_job_lease SET holder = 'conformance/widget/i1', epoch = CASE WHEN holder = 'conformance/widget/i1' THEN epoch ELSE epoch + 1 END,
       expires_at = now() + interval '30 seconds'
 WHERE name = 'be.lifecycle' AND (expires_at < now() OR holder = 'conformance/widget/i1');
INSERT INTO besdk_job_slot (name, slot_at, holder) VALUES ('widget.daily', '2026-10-02T19:00:00Z', 'i1') ON CONFLICT (name, slot_at) DO NOTHING;
INSERT INTO besdk_job_queue (id, kind, args, unique_key, max_attempts) VALUES ('0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a61', 'widget.notify', '{}', 'u1', 5) ON CONFLICT DO NOTHING;
DO $$ DECLARE n int; BEGIN
  WITH i AS (INSERT INTO besdk_job_queue (id, kind, args, unique_key, max_attempts) VALUES ('0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a62', 'widget.notify', '{}', 'u1', 5)
             ON CONFLICT DO NOTHING RETURNING 1) SELECT count(*) INTO n FROM i;
  IF n <> 0 THEN RAISE EXCEPTION 'queue unique_key admitted a duplicate'; END IF;
END $$;
INSERT INTO besdk_reconcile (name, item_id, lease_until) VALUES ('widget.approve', 'w1', now() + interval '30 seconds')
ON CONFLICT (name, item_id) DO UPDATE SET lease_until = now() + interval '30 seconds'
 WHERE (besdk_reconcile.lease_until IS NULL OR besdk_reconcile.lease_until < now()) AND besdk_reconcile.next_at <= now();
-- gap-free number and its allocation row (P11.10); a repeated number fails with 23505
INSERT INTO besdk_number_series (series, scope, period, gapless) VALUES ('voucher', 'LE01', '2026-10', true) ON CONFLICT DO NOTHING;
UPDATE besdk_number_series SET next_value = next_value + 1, updated_at = now() WHERE series = 'voucher' AND scope = 'LE01' AND period = '2026-10';
INSERT INTO besdk_number_allocations (legal_entity_id, series, number, document_id) VALUES ('LE01', 'voucher', 'V-LE01-202610-000001', 'd1');
SAVEPOINT num;
DO $$ BEGIN INSERT INTO besdk_number_allocations (legal_entity_id, series, number, document_id) VALUES ('LE01', 'voucher', 'V-LE01-202610-000001', 'd2');
  RAISE EXCEPTION 'a repeated number was accepted';
EXCEPTION WHEN unique_violation THEN NULL; END $$;
ROLLBACK TO num;
-- advisory lock form (P10.8)
SELECT pg_advisory_xact_lock(hashtext(current_schema() || ':' || 'widget'), hashtext('a|b'));
-- the lifecycle log carries the sealed guard from creation (P16.5)
INSERT INTO besdk_lifecycle_log (action, detail) VALUES ('sealed', '{}');
SAVEPOINT s;
DO $$ BEGIN UPDATE besdk_lifecycle_log SET action = 'x'; RAISE EXCEPTION 'guard did not fire';
EXCEPTION WHEN SQLSTATE 'BE001' THEN NULL; END $$;
ROLLBACK TO s;
-- seal a partition through the definer function; a write is refused with BE001
SELECT besdk_ensure_range_partition('ddl_probe', 'ddl_probe_2026_09', '2026-09-01', '2026-10-01');
INSERT INTO ddl_probe VALUES ('0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a70', '2026-09-15', 'w');
SELECT besdk_seal_table('ddl_probe_2026_09'), besdk_seal_table('ddl_probe_2026_09');
SAVEPOINT s2;
DO $$ BEGIN UPDATE ddl_probe SET name = 'x'; RAISE EXCEPTION 'seal did not fire';
EXCEPTION WHEN SQLSTATE 'BE001' THEN NULL; END $$;
ROLLBACK TO s2;
-- thaw: create detached, load, seal and attach; the thawed unit is read-only (P16.2)
DO $$ BEGIN
  IF NOT besdk_thaw_create('ddl_probe', 'ddl_probe_2025_01') THEN RAISE EXCEPTION 'thaw create'; END IF;
  IF besdk_thaw_create('ddl_probe', 'ddl_probe_2025_01') THEN RAISE EXCEPTION 'thaw create not idempotent'; END IF;
END $$;
INSERT INTO ddl_probe_2025_01 VALUES ('0192f0c4-7b1e-7cc3-9a52-3f1d2e4b5a71', '2025-01-15', 'thawed');
DO $$ BEGIN
  IF NOT besdk_thaw_attach('ddl_probe', 'ddl_probe_2025_01', '2025-01-01', '2025-02-01') THEN RAISE EXCEPTION 'thaw attach'; END IF;
  IF besdk_thaw_attach('ddl_probe', 'ddl_probe_2025_01', '2025-01-01', '2025-02-01') THEN RAISE EXCEPTION 'thaw attach not idempotent'; END IF;
  IF (SELECT count(*) FROM ddl_probe WHERE name = 'thawed') <> 1 THEN RAISE EXCEPTION 'thawed rows not visible'; END IF;
END $$;
SAVEPOINT s3;
DO $$ BEGIN DELETE FROM ddl_probe WHERE name = 'thawed'; RAISE EXCEPTION 'thawed unit is writable';
EXCEPTION WHEN SQLSTATE 'BE001' THEN NULL; END $$;
ROLLBACK TO s3;
DO $$ BEGIN
  IF NOT besdk_drop_partition('ddl_probe', 'ddl_probe_2025_01') THEN RAISE EXCEPTION 're-freeze drop'; END IF;
  IF NOT besdk_drop_partition('besdk_outbox', 'besdk_outbox_2026w41') THEN RAISE EXCEPTION 'drop'; END IF;
  IF besdk_drop_partition('besdk_outbox', 'besdk_outbox_2026w41') THEN RAISE EXCEPTION 'drop not idempotent'; END IF;
END $$;
SAVEPOINT s4;
DO $$ BEGIN PERFORM besdk_ensure_range_partition('besdk_idempotency', 'besdk_idempotency_x', now(), now()); RAISE EXCEPTION 'accepted a non-partitioned parent';
EXCEPTION WHEN undefined_table THEN NULL; END $$;
ROLLBACK TO s4;
-- the canonical predicate's ACL branch (P6.5)
SELECT count(*) FROM besdk_authz_acl a WHERE a.rtype = 'conformance.widget.widget' AND a.relation = ANY('{viewer}')
   AND a.subject = ANY('{user:u1}') AND (a.expires_at IS NULL OR a.expires_at > now());
COMMIT;
-- be_bus partition and publish (P12.12)
-- the database initialisation's grants to a component's runtime role
GRANT USAGE ON SCHEMA be_bus TO r_widget;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA be_bus TO r_widget;
GRANT USAGE ON SEQUENCE be_bus.message_seq TO r_widget;
GRANT EXECUTE ON FUNCTION be_bus.ensure_partition(timestamptz), be_bus.drop_partition(text, timestamptz) TO r_widget;
SET ROLE r_widget;
-- a publish with no range partition lands in the DEFAULT partition instead of failing
INSERT INTO be_bus.msg_id (stream, msg_id, expires_at) VALUES ('BE_CONFORMANCE', 'm0', now() + interval '10 minutes') ON CONFLICT DO NOTHING;
INSERT INTO be_bus.message (stream, msg_id, subject, headers, data, published_at) VALUES ('BE_CONFORMANCE', 'm0', 'conformance.widget.created.v1', '{"ce-id":"m0"}', '\x7b7d', '2026-09-01T00:00:00Z');
DO $$ BEGIN
  IF (SELECT count(*) FROM be_bus.message_default) <> 1 THEN RAISE EXCEPTION 'default partition'; END IF;
  -- the adapter's partition through the definer function, idempotent, named <isoyear>w<ww> (P16.10)
  IF NOT be_bus.ensure_partition('2026-10-02T12:00:00Z') THEN RAISE EXCEPTION 'be_bus create'; END IF;
  IF be_bus.ensure_partition('2026-10-04T23:59:59Z') THEN RAISE EXCEPTION 'be_bus create not idempotent'; END IF;
  IF to_regclass('be_bus.message_2026w40') IS NULL THEN RAISE EXCEPTION 'be_bus partition name'; END IF;
END $$;
INSERT INTO be_bus.msg_id (stream, msg_id, expires_at) VALUES ('BE_CONFORMANCE', 'm1', now() + interval '10 minutes') ON CONFLICT DO NOTHING;
INSERT INTO be_bus.message (stream, msg_id, subject, headers, data, published_at) VALUES ('BE_CONFORMANCE', 'm1', 'conformance.widget.created.v1', '{"ce-id":"m1"}', '\x7b7d', '2026-10-01T08:00:00Z');
DO $$ BEGIN
  IF (SELECT count(*) FROM be_bus.message WHERE tableoid = 'be_bus.message_2026w40'::regclass) <> 1 THEN RAISE EXCEPTION 'be_bus range partition'; END IF;  -- read through the parent: a new partition belongs to be_bus_owner
  BEGIN
    PERFORM be_bus.drop_partition('message_2026w40', '2026-10-03T00:00:00Z');
    RAISE EXCEPTION 'dropped inside the retention window';
  EXCEPTION WHEN invalid_parameter_value THEN NULL;
  END;
  IF NOT be_bus.drop_partition('message_2026w40', '2026-10-06T00:00:00Z') THEN RAISE EXCEPTION 'be_bus drop'; END IF;
  IF be_bus.drop_partition('message_2026w40', '2026-10-06T00:00:00Z') THEN RAISE EXCEPTION 'be_bus drop not idempotent'; END IF;
END $$;
RESET ROLE;
SQL

  if [ "$major" -ge 16 ]; then
    # a shell's login role reaches a member's runtime role only through SET ROLE (P19.5)
    $P <<'SQL'
CREATE ROLE r_shell LOGIN PASSWORD 'x';
GRANT r_widget TO r_shell WITH INHERIT FALSE, SET TRUE;
SET ROLE r_shell;
DO $$ BEGIN
  IF has_schema_privilege('r_shell', 's_widget', 'USAGE') THEN RAISE EXCEPTION 'the shell role inherits a member''s privileges'; END IF;
END $$;
BEGIN; SET LOCAL ROLE r_widget; SET LOCAL search_path TO s_widget;
SELECT count(*) FROM besdk_outbox;
COMMIT;
RESET ROLE;
SQL
  fi
  echo "ddltest PostgreSQL $major: OK"
}

for image in $IMAGES; do
  tag=${image##*:}; tag=${tag%%-*}
  run_one "$image" "$PREFIX-pg$tag-$$"
done
