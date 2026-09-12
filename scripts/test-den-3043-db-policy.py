#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "den-3043/db-table-policy.json").read_text())
DPM = ROOT / "vendor/declarative-postgres-migrate.rs/src/introspect.rs"
CLIENTS = ROOT / "vendor/declmig-clients/.zpkg.toml"


def rust_string_array(source: str, constant: str) -> set[str]:
    match = re.search(
        rf"pub const {re.escape(constant)}:\s*&\[&str\]\s*=\s*&\[(.*?)\];",
        source,
        flags=re.S,
    )
    if not match:
        raise AssertionError(f"missing Rust string array {constant}")
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def zpkg_scalar(text: str, key: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\"([^\"]+)\"\s*$", text)
    if not match:
        raise AssertionError(f"missing .zpkg.toml key {key}")
    return match.group(1)


def classify(schema: str, table: str) -> set[str]:
    findings: set[str] = set()
    canonical_schema = schema.lower()
    canonical_table = table.lower()
    if schema != canonical_schema or table != canonical_table:
        findings.add("uppercase")
    if canonical_schema in set(POLICY["internalSchemas"]) or any(
        canonical_schema.startswith(prefix) for prefix in POLICY["internalPrefixes"]
    ):
        findings.add("internal_namespace")
    if canonical_schema in set(POLICY["managedSchemasFromDeclarativeMigrations"]):
        findings.add("managed_namespace")
    if canonical_table in set(POLICY["migrationBookkeepingTables"]):
        findings.add("migration_bookkeeping")
    return findings


def main() -> None:
    assert POLICY["schema"] == "ores.db-table-policy/v1"
    assert POLICY["identifierPolicy"] == {
        "case": "lowercase",
        "canonicalIdentity": "schema.table",
        "implicitSchema": "public",
    }

    source = DPM.read_text()
    upstream_excluded = rust_string_array(source, "DEFAULT_EXCLUDED_SCHEMAS")
    expected_managed = set(POLICY["managedSchemasFromDeclarativeMigrations"])
    missing = sorted(expected_managed - upstream_excluded)
    assert not missing, f"managed-schema policy drifted from declarative-migrations: {missing}"
    assert "information_schema" in upstream_excluded

    clients = CLIENTS.read_text()
    assert zpkg_scalar(clients, "name") == "declmig-clients"
    assert zpkg_scalar(clients, "version") == POLICY["declmigClients"]["version"]

    cases = {
        ("ledger", "journal_entry"): set(),
        ("Ledger", "journal_entry"): {"uppercase"},
        ("public", "JournalEntry"): {"uppercase"},
        ("auth", "user_shadow"): {"managed_namespace"},
        ("pg_catalog", "users"): {"internal_namespace"},
        ("crdb_internal", "ranges"): {"internal_namespace"},
        ("public", "__diesel_schema_migrations"): {"migration_bookkeeping"},
        ("public", "seaql_migrations"): {"migration_bookkeeping"},
    }
    for identity, expected in cases.items():
        actual = classify(*identity)
        assert actual == expected, f"{identity}: expected {expected}, got {actual}"

    print(
        json.dumps(
            {
                "schema": POLICY["schema"],
                "status": "passed",
                "managedSchemasChecked": len(expected_managed),
                "upstreamExcludedSchemas": len(upstream_excluded),
                "bookkeepingTablesChecked": len(POLICY["migrationBookkeepingTables"]),
                "declmigClientsVersion": POLICY["declmigClients"]["version"],
                "cases": len(cases),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
