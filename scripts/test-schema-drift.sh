#!/usr/bin/env bash
set -euo pipefail
DPM="${DPM_BIN:?DPM_BIN is required}"
PG_ADMIN="${POSTGRES_ADMIN_URL:-postgres://postgres@localhost:5432/postgres}"
CR_ADMIN="${COCKROACH_ADMIN_URL:-postgresql://root@localhost:26257/defaultdb?sslmode=disable}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
artifacts="$root/artifacts"
mkdir -p "$artifacts"

certify() {
  local engine="$1" admin="$2" target="$3" create_sql="$4" drop_sql="$5"
  eval "$drop_sql" >/dev/null 2>&1 || true
  eval "$create_sql" >/dev/null

  "$DPM" apply --source-sql "$root/fixtures/desired.sql" --target "$target" --shadow "$admin" --yes
  psql "$target" -v ON_ERROR_STOP=1 -c "INSERT INTO app.accounts(id,email) VALUES ('preserved','preserved@example.test')" >/dev/null
  psql "$target" -v ON_ERROR_STOP=1 <<'SQL' >/dev/null
ALTER TABLE app.accounts ADD COLUMN rogue_note text;
CREATE INDEX rogue_note_idx ON app.accounts (rogue_note);
CREATE TABLE app.rogue_table (id text PRIMARY KEY, payload text);
SQL

  set +e
  "$DPM" diff --source-sql "$root/fixtures/desired.sql" --target "$target" --shadow "$admin" --fail-on-diff >"$artifacts/${engine}-drift.sql" 2>&1
  diff_status=$?
  set -e
  [[ "$diff_status" -eq 2 ]] || { echo "$engine drift expected exit 2, observed $diff_status" >&2; exit 1; }
  grep -Eqi 'rogue_note|rogue_table|DROP COLUMN|DROP TABLE|DROP INDEX' "$artifacts/${engine}-drift.sql"

  set +e
  "$DPM" apply --source-sql "$root/fixtures/desired.sql" --target "$target" --shadow "$admin" --yes >"$artifacts/${engine}-gated.out" 2>"$artifacts/${engine}-gated.err"
  gated_status=$?
  set -e
  [[ "$gated_status" -eq 3 ]] || { echo "$engine gated apply expected exit 3, observed $gated_status" >&2; exit 1; }
  grep -q 'NOT CONVERGED' "$artifacts/${engine}-gated.err"
  grep -q 'residual diff' "$artifacts/${engine}-gated.err"
  [[ "$(psql "$target" -Atqc "SELECT count(*) FROM information_schema.columns WHERE table_schema='app' AND table_name='accounts' AND column_name='rogue_note'")" == "1" ]]
  [[ "$(psql "$target" -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_schema='app' AND table_name='rogue_table'")" == "1" ]]

  "$DPM" apply --source-sql "$root/fixtures/desired.sql" --target "$target" --shadow "$admin" --yes --allow-destructive
  "$DPM" diff --source-sql "$root/fixtures/desired.sql" --target "$target" --shadow "$admin" --fail-on-diff >/dev/null
  "$DPM" verify --source-sql "$root/fixtures/desired.sql" --target "$target" --shadow "$admin"
  [[ "$(psql "$target" -Atqc "SELECT count(*) FROM app.accounts WHERE id='preserved'")" == "1" ]]
  [[ "$(psql "$target" -Atqc "SELECT count(*) FROM information_schema.columns WHERE table_schema='app' AND table_name='accounts' AND column_name='rogue_note'")" == "0" ]]
  [[ "$(psql "$target" -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_schema='app' AND table_name='rogue_table'")" == "0" ]]
  eval "$drop_sql" >/dev/null 2>&1 || true
}

trap 'psql "$PG_ADMIN" -c "DROP DATABASE IF EXISTS dm_drift_pg WITH (FORCE)" >/dev/null 2>&1 || true; psql "$CR_ADMIN" -c "DROP DATABASE IF EXISTS dm_drift_cr CASCADE" >/dev/null 2>&1 || true' EXIT
certify postgres "$PG_ADMIN" "postgres://postgres@localhost:5432/dm_drift_pg" \
  'psql "$PG_ADMIN" -v ON_ERROR_STOP=1 -c "CREATE DATABASE dm_drift_pg"' \
  'psql "$PG_ADMIN" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS dm_drift_pg WITH (FORCE)"'
certify cockroach "$CR_ADMIN" "postgresql://root@localhost:26257/dm_drift_cr?sslmode=disable" \
  'psql "$CR_ADMIN" -v ON_ERROR_STOP=1 -c "CREATE DATABASE dm_drift_cr"' \
  'psql "$CR_ADMIN" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS dm_drift_cr CASCADE"'

echo "Schema drift certification passed"
