# Schema drift end-to-end certification

This repository injects unauthorized table, column, and index drift into live PostgreSQL and CockroachDB databases. It proves that `dpm diff --fail-on-diff` returns exit 2, a gated `dpm apply` returns exit 3 without silently claiming success, and an explicitly destructive apply repairs the catalog while preserving application rows.

Production is pinned to `declarative-migrations/declarative-postgres-migrate.rs@21eb846e356b2a5aff068b21e77903e6cca50452`.
