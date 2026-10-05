# SPEC 013 — Telemetry and cost model

Status: Draft · Slices: S1 (records), S3 (queries), S6 (pricing) · Related: TOKLI_TELEMETRY_AND_COST.md (explanatory, incl. schemas)
Approved for S1 (2026-09-30): TC-001, TC-002, TC-003, TC-010, TC-011, TC-012, TC-014. TC-013 API in S3; cost in S6.
Approved for S2 (2026-10-02): TC-001 usage, calibration and whole-request estimate fields; TC-012 schema v2.
Approved for S3 (2026-10-03): TC-013, TC-015, TC-016.
Approved for S4 (2026-10-03): TC-014 `reference_stubs` filled.
Approved for S6 (2026-10-04): TC-004…TC-009, TC-017…TC-020; AC-TC-3…AC-TC-5, AC-TC-13…AC-TC-16; schema v4 (ADR 0014).

## Purpose
Persist the minimum metadata needed to answer "how much is Tokli saving, by which compressor,
at what latency, and roughly how much money", without storing content.

## Requirements

| ID | EARS requirement |
|---|---|
| TC-001 | WHEN a transformable request completes (success, upstream error or client disconnect), THE SYSTEM SHALL persist one `RequestRecord` with the fields defined in TOKLI_TELEMETRY_AND_COST §2. |
| TC-002 | WHEN a compressor is considered for at least one segment of a request, THE SYSTEM SHALL persist one `CompressorStats` row for that request and compressor. |
| TC-003 | THE persisted records SHALL satisfy `Σ marginal_saved = est_original_tokens − est_forwarded_tokens` per request. |
| TC-004 | WHEN model pricing is available in the effective price book and provider usage is known, THE SYSTEM SHALL expose forwarded cost (every usage category, output included, at the price book), estimated saving and estimated original cost (forwarded + saving), all labelled as estimates. THE saving SHALL be priced with method `positional`: each saved token at the price of the usage region in which its segment sits in the forwarded request (TC-017). WHEN the request has no region split, THE saving SHALL be priced with method `proportional`: at the forwarded request's input-side usage mix. Bounds `[low, high]` SHALL price the whole saving at the lowest and the highest input-side price among the categories present in the request's usage. A cache-write region with both 5-minute and 1-hour tokens SHALL be priced at their mix. (S6, P1.) |
| TC-005 | WHEN model pricing is unavailable, THE SYSTEM SHALL report monetary fields as `null` with reason `no_price_for_model`, and SHALL still report token metrics. |
| TC-006 | WHEN provider usage is unavailable, THE SYSTEM SHALL compute the saving estimate at the uncached input price, labelled `assumes_uncached`, with a lower bound at the cache-read price when known. |
| TC-007 | THE SYSTEM SHALL NOT attribute output-token savings to compression. |
| TC-008 | THE price book SHALL be a versioned file with per-entry `effective_from`, source note and currency. Cost SHALL be computed at query time using the entry effective at the request's timestamp. WHEN several entries match a model, THE entry with the most specific `match` pattern SHALL apply (fewest `*`, then most literal characters), and among those the latest `effective_from` not after the request's `ts_start`. |
| TC-009 | THE telemetry and pricing modules SHALL NOT be imported by compression modules, and pricing SHALL NOT be imported by telemetry (import contracts). |
| TC-010 | THE SYSTEM SHALL prune records older than `telemetry.retention_days` (default 30; 0 = never) at startup and every 24 h. |
| TC-011 | IF a telemetry sink fails, THEN THE SYSTEM SHALL continue serving, count the failures, report `degraded` in health, and log at most one warning per minute. |
| TC-012 | THE telemetry schema SHALL carry a `schema_version` (v2 from S2: `requests.header_names`, ADR 0005), and startup SHALL migrate older databases forward or refuse with a clear message. It SHALL never silently drop columns. |
| TC-013 | THE metrics API SHALL report the Tokli overhead distribution (`n`, p50, p95, p99, max of `ms_tokli_overhead`, nearest-rank percentiles) per request-size bucket (`est_request_tokens_original` < 10k, 10k–50k, 50k–200k, > 200k; rows without it in a separate `unknown` bucket), per policy and per `config_hash`. It SHALL show the product target (TOKLI_VISION.md) as a labelled reference value, never as a pass/fail status. |
| TC-014 | THE `RequestRecord` SHALL carry `history_rewritten` (PR-009) and the count of reference stubs forwarded (`reference_stubs`). |
| TC-015 | THE metrics API SHALL compute token totals over requests of transformable endpoints only (verbatim routes count in request totals by outcome, never in token figures), from per-request best figures: forwarded = provider input total (input + cache read + cache writes) when usage exists, else the whole-request estimate; saving = calibrated when an in-range `k` exists, else the estimate; original = forwarded + saving; saving % = saving / original. A total SHALL be labelled `exact` or `calibrated` only when every contributing figure has that method; otherwise it SHALL be labelled `estimate` and carry `calibrated_share` (or `exact_share`), the share of the total with the stronger method. |
| TC-016 | THE per-compressor aggregates SHALL follow TOKLI_TELEMETRY_AND_COST §3: zero-benefit rate = (applicable − accepted) / applicable; failure rate = failed / applicable; share = marginal saved / total saved; average saving % per accepted call; tokens saved per ms = marginal saved / `ms_total`. A rate whose denominator is 0 SHALL be `{value: null, reason}`. A compressor with ≥ 90 % zero-benefit, ≥ 1 ms average latency and ≥ 100 applicable invocations SHALL carry the flag `latency_without_benefit`. |
| TC-017 | WHEN a compressed request completes with provider usage, a whole-request estimate and an in-range `k`, THE SYSTEM SHALL record its estimated saving split into the three usage regions (`saved_cache_read`, `saved_cache_write`, `saved_input`, estimate units), for the request and for each compressor stats row. Each changed segment SHALL be placed at its offset in the forwarded request in provider order (tool definitions, system, messages), and the region sizes SHALL be the usage categories divided by `k`, in the order cache read, cache write, uncached input. A segment that straddles a boundary SHALL be split in proportion to its forwarded length on each side. The three parts SHALL sum exactly to the saving they split. Otherwise the split SHALL be null. (S6, P1, P2.) |
| TC-018 | THE SYSTEM SHALL ship a price book with dated, sourced entries for the Anthropic models, AND SHALL read an optional user price book at `<data>/price-book.yaml` in the same format, whose entries take precedence over the shipped ones. An invalid user price book SHALL be a startup error naming the file and the problem. THE doctor SHALL report the shipped price-book version and whether a user price book is active, with its version. (S6, P4, P5.) |
| TC-019 | WHEN a request's credential is OAuth (a subscription), THE money figures that include it SHALL carry `basis: "api_equivalent"`, and THE dashboard SHALL label them "value at API prices"; otherwise `basis: "billed"`, labelled "estimated money saved". (S6, P3.) |
| TC-020 | THE summary's cost block SHALL carry as caveats, for its range, the number of requests with `history_rewritten` and the number of `config_hash` changes between consecutive requests, because Tokli does not deduct the provider cache rewrites they cause. (S6, P8.) |

## Acceptance criteria
- AC-TC-1: after 3 fixture requests (compressed, passthrough, upstream 429), the DB contains 3 `RequestRecord`s with the correct outcome and reason, and `CompressorStats` only for considered compressors.
- AC-TC-2: property test for TC-003 across random pipelines.
- AC-TC-3 (TC-004): for a synthetic request with usage (cache read, 5-minute cache write, input) and a saving split over the three regions, at the shipped `claude-sonnet-5` prices, the API returns the hand-computed positional estimate and bounds; the same request without a split returns the hand-computed proportional estimate.
- AC-TC-4: an unknown model gives `null` cost with the reason, and non-null tokens.
- AC-TC-5: a price-book entry change with a later `effective_from` does not change the cost of earlier requests.
- AC-TC-7 (TC-013): for 300 synthetic records with known overheads across the four buckets, the API returns the hand-computed percentiles per bucket, and the target appears as `{value, kind: "target"}` with no status field.
- AC-TC-8 (TC-014): a request with a superseding stub on an earlier segment persists `history_rewritten: true`. A request with two duplicate stubs persists `reference_stubs: 2` and `history_rewritten: false`.
- AC-TC-9 (TC-012): a v1 database written by S1 opens under S2, is migrated to v2 in place, and keeps every earlier row and column; old rows have `header_names` null.
- AC-TC-11 (TC-015): for a hand-built set of records (calibrated, outlier, no usage, verbatim route), the summary returns the hand-computed totals; a total with one estimated request is labelled `estimate` with the correct `calibrated_share`.
- AC-TC-12 (TC-016): for hand-built stats rows the compressor aggregates and the flag match hand-computed values; a compressor with 0 applicable invocations has `null` rates with a reason.
- AC-TC-13 (TC-017): for a hand-built request (segment offsets, usage, `k`) the recorded split is hand-computed, including a segment that straddles a boundary; a property test shows that the parts sum to the saving, per compressor and per request.
- AC-TC-14 (TC-018): a user price book with another price for a model changes that model's cost and no other; an invalid user price book stops startup with the file and the problem; the doctor names both versions.
- AC-TC-15 (TC-019): a range with one OAuth request gives `basis: "api_equivalent"`; a range of API-key requests gives `billed`.
- AC-TC-16 (TC-020): for hand-built records the caveat counts are hand-computed.
- AC-TC-6: a read-only DB file → the request succeeds, health is `degraded`, and one warning is logged.

## Test scenarios
`test_request_record_persisted_per_outcome` · `test_compressor_stats_only_for_considered` ·
`prop_marginal_savings_sum_to_total` · `test_cost_proportional_estimate_and_bounds` ·
`test_cost_unavailable_without_price` · `test_cost_assumes_uncached_without_usage` ·
`test_no_output_savings_claimed` · `test_price_effective_dates` · `test_retention_pruning` ·
`test_sink_failure_degrades_not_breaks` · `test_schema_migration_forward` · `test_import_contracts` ·
`test_overhead_percentiles_by_bucket` · `test_target_is_reference_not_status` · `test_request_record_pruning_fields` ·
`test_unknown_size_bucket` · `test_summary_totals_hand_computed` · `test_summary_labels_mixed_totals_as_estimate_with_share` ·
`test_compressor_aggregates_hand_computed` · `test_latency_without_benefit_flag` ·
`test_cost_positional_estimate_and_bounds` · `test_cost_proportional_without_split` · `test_price_match_most_specific` ·
`test_saving_regions_hand_computed` · `prop_saving_regions_sum_to_saving` · `test_user_price_book_overrides_shipped` ·
`test_invalid_user_price_book_stops_startup` · `test_oauth_cost_basis_api_equivalent` · `test_cost_caveats_hand_computed` ·
`test_schema_migration_v3_to_v4`
