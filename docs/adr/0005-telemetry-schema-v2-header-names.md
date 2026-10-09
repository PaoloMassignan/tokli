# ADR 0005 — Telemetry schema v2: header names, first forward migration

Status: accepted (S2, 2026-10-02; decided at S1 Gate 2, approved at S2 Gate 1) · Related:
SPEC 013 TC-012, SPEC 014 OB-012, ADR 0003

## Context

S1 recorded the names of the client's request headers in the in-memory trace only (OB-012), so
they were lost on restart and when the trace buffer evicted the request. At S1 Gate 2 the product
owner decided to persist them. This adds a column to `requests`, which is a persistence format
change (CLAUDE.md §6), and it is the first time an existing database must be migrated forward
(TC-012).

## Decision

- **Schema version 2** adds `requests.header_names TEXT`: a JSON array of the client's request
  header names, lower-cased and sorted. Values are never stored. Requests recorded before v2 have
  `NULL`.
- **Forward migration** at startup, in one transaction: for every column of the current record
  types missing from an existing table, `ALTER TABLE … ADD COLUMN`; then `meta.schema_version` is
  set to the current version. Columns are only ever added, never dropped or retyped, and existing
  rows are kept.
- A database with a **newer** version is still refused with a clear message (ADR 0003).
- The usage, calibration and whole-request estimate columns already exist in v1 (ADR 0003); S2
  only fills them.

## Alternatives considered

- **A separate table of header names per request:** normalised, but needs joins for a list that
  is small and always read whole. Rejected.
- **Recreating the database on a version change:** loses the user's history. Rejected (TC-012
  forbids silently dropping data).

## Consequences

- Tests: `test_schema_migration_forward` opens a v1 database written with the S1 column set and
  checks that every earlier row and column survives; `test_header_names_persisted` checks that
  names, and no values, reach the database.
- Portability: `ALTER TABLE … ADD COLUMN` behaves the same on every supported OS and SQLite
  version shipped with CPython 3.11–3.14.
- An S1 build refuses a database that an S2 build has migrated (newer version). Going back needs a
  different `--data-dir`.
