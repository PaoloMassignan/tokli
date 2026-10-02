# ADR 0003 — Telemetry persistence: SQLite schema v1

Status: accepted (S1, 2026-09-30) · Related: SPEC 013, TOKLI_TELEMETRY_AND_COST.md §2

## Context

S1 persists `RequestRecord` and `CompressorStats` (TC-001, TC-002). A persistence format is a
significant decision (`CLAUDE.md §6`): later slices (metrics API, dashboard, cost) read it, and
TC-012 forbids silent schema changes.

## Decision

- **File:** `<data dir>/tokli.db`, stdlib `sqlite3`, WAL journal.
- **Tables:**
  - `meta(key, value)` holds `schema_version = 1`;
  - `requests` has one column per `RequestRecord` field (TOKLI_TELEMETRY_AND_COST §2), plus
    `ms_total`, `history_rewritten` and `reference_stubs`;
  - `compressor_stats` has one row per request × compressor considered; `skip_reasons` is stored
    as sorted JSON.
- **Additions to the documented field list:**
  - `ms_total` (arrival to last relayed byte), needed to check
    `overhead = total − upstream wall time` (AC-OB-2);
  - `history_rewritten` and `reference_stubs` (TC-014). Both are present from v1, so S4 and S8 need
    no migration.
- **Writes:** one background writer thread, a bounded queue (10,000 entries), no disk I/O on the
  request path. A failed write is counted, health reports `degraded`, and at most one warning is
  logged per minute (TC-011).
- **Retention:** records older than `telemetry.retention_days` are deleted at startup and every
  24 h (TC-010).
- **Versioning:** opening a database with a newer `schema_version` is refused with a clear message
  (TC-012). Future versions migrate forward additively and never drop columns.

## Consequences

- Timestamps are ISO-8601 UTC strings with milliseconds. Range queries compare strings, which is
  correct for this fixed format.
- No content and no credentials can reach the database: the record types carry neither, and
  `test_logs_never_contain_credentials` / `test_default_logging_contains_no_prompt_text` scan the
  database bytes.
