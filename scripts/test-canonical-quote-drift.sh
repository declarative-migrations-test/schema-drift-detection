#!/usr/bin/env bash
set -euo pipefail

DPM="${DPM_BIN:?DPM_BIN is required}"
API_DIR="${CANONICAL_API_DIR:?CANONICAL_API_DIR is required}"
ADMIN="${POSTGRES_ADMIN_URL:-postgres://postgres:quote-drift@localhost:5432/postgres}"
DB="canonical_quote_schema_drift"
TARGET="postgres://postgres:quote-drift@localhost:5432/${DB}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACTS="$ROOT/artifacts/canonical-quote-drift"
SCHEMA="$API_DIR/db/schema.sql"
mkdir -p "$ARTIFACTS"

cleanup() {
  psql "$ADMIN" -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup
psql "$ADMIN" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${DB}" >/dev/null

apply_and_verify() {
  "$DPM" apply \
    --source-sql "$SCHEMA" \
    --target "$TARGET" \
    --shadow "$ADMIN" \
    --yes
  "$DPM" diff \
    --source-sql "$SCHEMA" \
    --target "$TARGET" \
    --shadow "$ADMIN" \
    --fail-on-diff \
    >/dev/null
  "$DPM" verify \
    --source-sql "$SCHEMA" \
    --target "$TARGET" \
    --shadow "$ADMIN"
}

expect_drift_and_repair() {
  local name="$1"
  local inject_sql="$2"
  local assertion_sql="$3"
  local expected="$4"

  psql "$TARGET" -v ON_ERROR_STOP=1 -c "$inject_sql" >/dev/null

  set +e
  "$DPM" diff \
    --source-sql "$SCHEMA" \
    --target "$TARGET" \
    --shadow "$ADMIN" \
    --fail-on-diff \
    >"$ARTIFACTS/${name}.sql" 2>&1
  local status=$?
  set -e
  if [[ "$status" -ne 2 ]]; then
    echo "${name}: expected dpm drift exit 2, observed ${status}" >&2
    cat "$ARTIFACTS/${name}.sql" >&2
    exit 1
  fi
  test -s "$ARTIFACTS/${name}.sql"

  apply_and_verify

  local observed
  observed="$(psql "$TARGET" -Atv ON_ERROR_STOP=1 -c "$assertion_sql")"
  if [[ "$observed" != "$expected" ]]; then
    echo "${name}: repair assertion expected ${expected}, observed ${observed}" >&2
    exit 1
  fi
  test "$(psql "$TARGET" -Atqc "SELECT count(*) FROM canonical_quote WHERE id = '22222222-2222-4222-8222-222222222222'")" = "1"
}

apply_and_verify

# Preserve a durable quote row through every repair so a schema fix cannot be
# called successful merely because it rebuilt an empty database.
psql "$TARGET" -v ON_ERROR_STOP=1 <<'SQL' >/dev/null
INSERT INTO canonical_context (
  id, owner_subject, name, context_markdown, context_json
) VALUES (
  '11111111-1111-4111-8111-111111111111',
  'drift-owner',
  'Drift fixture',
  '# Drift fixture',
  '{"region":"us"}'::jsonb
);
INSERT INTO canonical_quote (
  id,
  owner_subject,
  context_record_id,
  request_json,
  application_context_markdown,
  context_snapshot_markdown,
  context_snapshot_json,
  gemini_model,
  status
) VALUES (
  '22222222-2222-4222-8222-222222222222',
  'drift-owner',
  '11111111-1111-4111-8111-111111111111',
  '{"frameworks":["soc2"],"organization":{"employee_count":42,"industry":"Software","legal_name":"Drift Fixture"}}'::jsonb,
  '# application',
  '# Drift fixture',
  '{"region":"us"}'::jsonb,
  'gemini-3.6-pro',
  'queued'
);
SQL

expect_drift_and_repair \
  "missing-owner-policy" \
  "DROP POLICY canonical_quote_owner_policy ON canonical_quote" \
  "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='canonical_quote' AND policyname='canonical_quote_owner_policy'" \
  "1"

expect_drift_and_repair \
  "force-rls-disabled" \
  "ALTER TABLE canonical_quote NO FORCE ROW LEVEL SECURITY" \
  "SELECT relforcerowsecurity FROM pg_class WHERE oid='public.canonical_quote'::regclass" \
  "t"

expect_drift_and_repair \
  "missing-event-owner-fk" \
  "ALTER TABLE canonical_quote_event DROP CONSTRAINT canonical_quote_event_quote_owner_fk" \
  "SELECT count(*) FROM pg_constraint WHERE conname='canonical_quote_event_quote_owner_fk' AND convalidated" \
  "1"

expect_drift_and_repair \
  "missing-active-context-index" \
  "DROP INDEX canonical_context_one_active_per_owner_idx" \
  "SELECT to_regclass('public.canonical_context_one_active_per_owner_idx') IS NOT NULL" \
  "t"

expect_drift_and_repair \
  "missing-model-finish-check" \
  "ALTER TABLE canonical_model_attempt DROP CONSTRAINT canonical_model_attempt_status_finished_check" \
  "SELECT count(*) FROM pg_constraint WHERE conname='canonical_model_attempt_status_finished_check' AND convalidated" \
  "1"

printf 'Canonical quote policy, RLS, owner-FK, index, and check drift certification passed.\n'
