# ADR 0017 — Telemetry schema v6: keepalive rows and bridged requests

Status: accepted (S8l Gate 1, 2026-10-23) · Related: SPEC 013 TC-023…TC-025, SPEC 020, ADR 0005, ADR 0015, ADR 0016

## Context

- **Keepalive requests have a cost** (usage at the price book), and their benefit shows up on a
  later client request: the bridged request reads a cache that would otherwise have been written
  again. Both must be persisted to report a net saving (TC-025).
- **The `requests` table describes client requests.** Its token and overhead aggregates
  (TC-013, TC-015) must not change when keepalive rows are added (S8l SCR-001).

## Decision

- **Schema version 6** adds three columns to `requests`:
  - `keepalive_bridged INTEGER` (0, 1 or `NULL`) on client requests (TC-024);
  - `keepalive_stop_reason TEXT` on keepalive rows, from the closed set of SPEC 020 KA-010, `NULL`
    when the ping did not stop the conversation (TC-023);
  - `cache_ttl_s REAL`, the request's cache lifetime (SPEC 003 AN-011), so a bridged request's
    saving is priced at the write price of its lifetime (TC-025). Added during S8l GREEN: the
    lifetime is not otherwise stored.
- **Keepalive rows** use the existing `outcome` column with the new value `keepalive`, and the
  existing usage, status, timing, `credential_kind` and `stop_reason` columns. Token-estimate and
  segment columns are `NULL`; no `compressor_stats` rows.
- **Aggregates** filter on `outcome`: every existing query adds `outcome != 'keepalive'`, and the
  keepalive block (TC-025) reads only those rows and the bridged flag.
- **Migration:** the forward migration of ADR 0005 adds the three columns; rows written before v6 have
  `NULL`. Retention (TC-010) applies to keepalive rows as to the others.

## Alternatives considered

- **A separate `keepalive` table:** a second retention job, a second migration path and a join
  for the request view, for rows that have the same columns. Rejected.
- **Not persisting pings, only counters in memory:** the net saving would vanish at each restart
  and could not be shown per range. Rejected.
- **Pricing the saving at write time and storing it:** the price book is applied at query time
  everywhere else (TC-008). Rejected.

## Consequences

- **Tests:** the v5 → v6 migration (AC-TC-21); the existing summary tests stay unchanged; a new
  test shows the totals are equal with and without keepalive rows (AC-TC-20).
- **Portability:** SQLite column additions only.
- **Downgrade:** an older Tokli refuses a v6 database, as with every schema change (TC-012).
