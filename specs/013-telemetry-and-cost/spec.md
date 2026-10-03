# SPEC 013 — Telemetry and cost model

Status: Draft · Slices: S1 (records), S3 (queries), S6 (pricing) · Related: TOKLI_TELEMETRY_AND_COST.md (explanatory, incl. schemas)
Approved for S1 (2026-09-30): TC-001, TC-002, TC-003, TC-010, TC-011, TC-012, TC-014. TC-013 API in S3; cost in S6.
Approved for S2 (2026-10-02): TC-001 usage, calibration and whole-request estimate fields; TC-012 schema v2.

## Purpose
Persist the minimum metadata needed to answer "how much is Tokli saving, by which compressor,
at what latency, and roughly how much money", without storing content.

## Requirements

| ID | EARS requirement |
|---|---|
| TC-001 | WHEN a transformable request completes (success, upstream error or client disconnect), THE SYSTEM SHALL persist one `RequestRecord` with the fields defined in TOKLI_TELEMETRY_AND_COST §2. |
| TC-002 | WHEN a compressor is considered for at least one segment of a request, THE SYSTEM SHALL persist one `CompressorStats` row for that request and compressor. |
| TC-003 | THE persisted records SHALL satisfy `Σ marginal_saved = est_original_tokens − est_forwarded_tokens` per request. |
| TC-004 | WHEN model pricing is available in the effective price book, THE SYSTEM SHALL expose forwarded cost, estimated original cost and estimated saving with method `proportional` and bounds `[low, high]`, all labelled as estimates. |
| TC-005 | WHEN model pricing is unavailable, THE SYSTEM SHALL report monetary fields as `null` with reason `no_price_for_model`, and SHALL still report token metrics. |
| TC-006 | WHEN provider usage is unavailable, THE SYSTEM SHALL compute the saving estimate at the uncached input price, labelled `assumes_uncached`, with a lower bound at the cache-read price when known. |
| TC-007 | THE SYSTEM SHALL NOT attribute output-token savings to compression. |
| TC-008 | THE price book SHALL be a versioned file with per-entry `effective_from`, source note and currency. Cost SHALL be computed at query time using the entry effective at the request's timestamp. |
| TC-009 | THE telemetry and pricing modules SHALL NOT be imported by compression modules, and pricing SHALL NOT be imported by telemetry (import contracts). |
| TC-010 | THE SYSTEM SHALL prune records older than `telemetry.retention_days` (default 30; 0 = never) at startup and every 24 h. |
| TC-011 | IF a telemetry sink fails, THEN THE SYSTEM SHALL continue serving, count the failures, report `degraded` in health, and log at most one warning per minute. |
| TC-012 | THE telemetry schema SHALL carry a `schema_version` (v2 from S2: `requests.header_names`, ADR 0005), and startup SHALL migrate older databases forward or refuse with a clear message. It SHALL never silently drop columns. |
| TC-013 | THE metrics API SHALL report the Tokli overhead distribution (`n`, p50, p95, p99, max of `ms_tokli_overhead`) per request-size bucket (estimated input tokens < 10k, 10k–50k, 50k–200k, > 200k), per policy and per `config_hash`. It SHALL show the product target (TOKLI_VISION.md) as a labelled reference value, never as a pass/fail status. |
| TC-014 | THE `RequestRecord` SHALL carry `history_rewritten` (PR-009) and the count of reference stubs forwarded (`reference_stubs`). |

## Acceptance criteria
- AC-TC-1: after 3 fixture requests (compressed, passthrough, upstream 429), the DB contains 3 `RequestRecord`s with the correct outcome and reason, and `CompressorStats` only for considered compressors.
- AC-TC-2: property test for TC-003 across random pipelines.
- AC-TC-3: for a synthetic usage mix (80 % cache_read, 5 % cache_write_5m, 15 % input) and 1,000 saved tokens at the illustrative Sonnet prices, the API returns the expected estimate and bounds (hand-computed in the test).
- AC-TC-4: an unknown model gives `null` cost with the reason, and non-null tokens.
- AC-TC-5: a price-book entry change with a later `effective_from` does not change the cost of earlier requests.
- AC-TC-7 (TC-013): for 300 synthetic records with known overheads across the four buckets, the API returns the hand-computed percentiles per bucket, and the target appears as `{value, kind: "target"}` with no status field.
- AC-TC-8 (TC-014): a request with a superseding stub on an earlier segment persists `history_rewritten: true`. A request with two duplicate stubs persists `reference_stubs: 2` and `history_rewritten: false`.
- AC-TC-9 (TC-012): a v1 database written by S1 opens under S2, is migrated to v2 in place, and keeps every earlier row and column; old rows have `header_names` null.
- AC-TC-6: a read-only DB file → the request succeeds, health is `degraded`, and one warning is logged.

## Test scenarios
`test_request_record_persisted_per_outcome` · `test_compressor_stats_only_for_considered` ·
`prop_marginal_savings_sum_to_total` · `test_cost_proportional_estimate_and_bounds` ·
`test_cost_unavailable_without_price` · `test_cost_assumes_uncached_without_usage` ·
`test_no_output_savings_claimed` · `test_price_effective_dates` · `test_retention_pruning` ·
`test_sink_failure_degrades_not_breaks` · `test_schema_migration_forward` · `test_import_contracts` ·
`test_overhead_percentiles_by_bucket` · `test_target_is_reference_not_status` · `test_request_record_pruning_fields`
