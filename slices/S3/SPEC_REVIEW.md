# S3 — Spec review

Slice: **S3 — Metrics API + minimal dashboard** (`TOKLI_ROADMAP.md`).
Status: **Human Gate 1 passed 2026-10-03.** Implementation in progress.

## Scope

**Roadmap content.**
- `MetricsQuery` and `/tokli/api/metrics/summary|timeseries|compressors` plus
  `/tokli/api/requests` (API-001…API-004).
- Dashboard v0: totals (original, forwarded, saved, %), the per-compressor table
  (TOKLI_TELEMETRY_AND_COST §3), recent requests (metadata) and method labels.

Exit: a developer can answer "how much, and which compressor" from the UI during dogfooding.
E5 (b) dogfood starts here.

**Requirements in scope (proposed):**

| Spec | In S3 | Deferred (slice) |
|---|---|---|
| 013 telemetry | TC-013 (overhead distribution per size bucket, policy, `config_hash`; target as a reference) | TC-004…TC-009 cost (S6) |
| 015 API | `GET /tokli/api/requests`, `metrics/summary`, `metrics/timeseries`, `metrics/compressors`; API-001…API-004, API-008; read-only `GET /tokli/api/compressors` (P2) | `PATCH /config`, `GET /config`, API-005…API-007 (S4); `diagnostics` (S9) |
| 016 dashboard | Overview, Compressors (read-only), Recent requests with trace detail; UI-001, UI-002, UI-003 (kind, equivalence, assumptions), UI-006, UI-008, UI-009 | toggles and Settings: UI-004, UI-005, UI-010, AC-UI-3 (S4); evaluation status in UI-003 (P3); Diagnostics page (S9); debug banner UI-007 (with OB-009); money figures (S6) |
| 014 observability | API reads are metadata only (OB-007, OB-008 already hold) | — |

## 1. Ambiguities

| Id | Requirement | Question | Proposed reading |
|---|---|---|---|
| A1 | TELEMETRY_AND_COST §3, TM-005 | Which requests enter the token totals? | Only records of the transformable endpoint (`protocol` not null). Verbatim routes (`count_tokens`, `models`, other paths) count in the request totals by outcome, never in token figures. |
| A2 | §3, TM-005 | How is a total built when some requests are calibrated and others are not? | Per request, the best figure (calibrated when an in-range `k` exists, else the estimate). The total is their sum. Its label is `calibrated` only when every contributing request is calibrated; otherwise `estimate`, with `calibrated_share` (the share of the total that is calibrated). See P4. |
| A3 | §3 | What are "forwarded tokens (exact when possible)"? | Per request, the provider's input total (input + cache read + cache writes) when usage exists, else the whole-request estimate. Same labelling rule as A2 (`exact` only when every request has usage). |
| A4 | §3 | What is "original tokens"? | Per request, forwarded + saving (each in its best method). Saving % = saved / original. |
| A5 | API-003 | What do `compressor` and `kind` mean on `summary` and `timeseries`? | They restrict the **saving** to that compressor's (or kind's) marginal savings, and the request set to requests where it was considered. Without them, figures cover all requests. |
| A6 | API-003 | Format and defaults of `from`, `to`, `tz`. | `from`/`to`: ISO-8601 with offset, half-open `[from, to)`. Default: the last 7 days. `tz`: an IANA name (default `UTC`), which sets bucket boundaries in `timeseries` (P5). Bad values give 400 with per-field errors. |
| A7 | TC-013 | Percentile definition; which estimate sets the size bucket; rows without it. | Nearest-rank percentiles. Bucket by `est_request_tokens_original` (whole request, from S2). Rows without it (S1-era, parse errors) go into an `unknown` bucket, shown separately. |
| A8 | §3 | Formulas of the per-compressor figures. | As written in §3: zero-benefit = (applicable − accepted) / applicable; failure = failed / applicable; share = marginal saved / total saved; average saving % per accepted call = Σ(tokens_in − tokens_out) / Σ tokens_in over accepted calls (from the stats rows); tokens saved per ms = marginal saved / `ms_total`. Fewer than 1 applicable → `null` with a reason. The "latency without benefit" flag: ≥ 90 % zero-benefit, ≥ 1 ms average, ≥ 100 applicable. |
| A9 | API `requests` | Paging. | Newest first. `limit` default 50, maximum 500. `cursor` = the last `request_id` seen; ULIDs sort by time. |

## 2. Contradictions

| Id | Where | Contradiction | Proposed resolution |
|---|---|---|---|
| X1 | SPEC 016 Overview ("estimated money saved") and API-002 money fields vs. pricing in S6 | Money is part of the page and the response, but no price book exists before S6. | A `cost` block `{value: null, reason: "no_price_book"}` in S3; the UI shows "—" with the reason (UI-002). See P6. |
| X2 | SPEC 016 Compressors page (enabled toggle) vs. S4 | Toggles need `PATCH /config` (S4). | The S3 page shows `enabled` and availability read-only. |
| X3 | UI-003 (evaluation record status) vs. packaging | Records live in `evals/records/` in the repository, not in the installed package, so a running Tokli cannot read them. | Show the status from S4 (with the full registry endpoint), when the records' packaging is decided. See P3. |
| X4 | TC-013 "per policy" vs. a fixed policy | Only LOSSLESS_ONLY exists until S4. | Group by policy anyway (one group today); no special case. |

## 3. Missing behaviour

- **M1. Error format for bad parameters:**
  `{api_version, error: {type: "invalid_parameter", fields: {<name>: <message>}}}` with status 400.
- **M2. Empty or missing database:** figures are 0 requests and `null` token values with the
  reason `no_data`; never an error. With telemetry disabled (benchmarks, tests), the metrics
  endpoints answer 503 `telemetry_disabled`.
- **M3. Dashboard URL:** `GET /tokli/` serves the dashboard and `/tokli/ui/*` its assets.
  `/` stays a Tokli 404 (unknown route). See P8.
- **M4. Host check for reads (DNS rebinding):** API-006 protects only mutations (S4). A malicious
  web page could use DNS rebinding to read `/tokli/api` metadata (models, token counts, header
  names) from the browser. See P7.

## 4. Portability concerns

- **Time zones on Windows:** Python's `zoneinfo` has no time-zone database on Windows. IANA names
  need the `tzdata` package (P5).
- **Static file types on Windows:** `mimetypes` reads the Windows registry, where `.js` is
  sometimes mapped to `text/plain`, and browsers then refuse the script. Decision: serve the UI
  with explicit content types.
- **SQLite:** aggregates use only portable SQL (no window functions needed). Percentiles are
  computed in Python, the same on every OS.
- **Bucket boundaries across DST** are tested in two zones (`Europe/Rome` and `America/New_York`).

## 5. Observability requirements for this slice

- API endpoints return metadata only (API-001). The canary scan covers every new endpoint.
- Every token figure is `{value, method}` or `{value: null, reason}` (API-002, TM-005), checked
  by a schema test over every new response.
- A metrics query that fails logs one WARNING (no content) and answers 500 `query_failed`; the
  proxy is never affected.
- Checklist §8: no new proxy code path or telemetry field; the recent-requests view shows the
  S2 fields (usage, `k`, saving with method).

## 6. Architectural risks

- **R1. Query cost.** A 30-day database can hold hundreds of thousands of rows. Decision: queries
  run in a worker thread on their own read-only SQLite connection (WAL allows concurrent readers),
  so the proxy's event loop never waits on them. Measured with a 100k-row synthetic database and
  reported (not gated).
- **R2. Layering (API-008, ARCH §5).** `tokli.app.metrics.MetricsQuery` owns the use cases; SQL
  lives in `tokli.telemetry` (read functions); `tokli.http` only routes. Today the import
  contracts let `tokli.http` import `tokli.telemetry` directly (the proxy builds `RequestRecord`).
  A new contract keeps the API routes off storage: `tokli.http.app` (routes) may not import
  `tokli.telemetry`, so they go through `tokli.app` (API-008). The proxy flow is unchanged.
- **R3. Browser test infrastructure** (AC-UI-2): Playwright with headless Chromium is a large new
  development dependency. See P9.
- **R4. Packaging of UI assets:** static files must be in the wheel (`test_wheel_contains_ui_assets`)
  and load with the network blocked (AC-UI-4).
- **Seams introduced:** none beyond the spec's `MetricsQuery`. No plugin points.

## 7. Product questions (for the human)

| # | Question | Recommendation |
|---|---|---|
| **P1** | **Dashboard pages in S3:** Overview (totals with methods, saved-tokens time series, overhead per size bucket with the target as a reference line), Compressors (read-only table), Recent requests (list and trace detail). Settings and Diagnostics come later. | Yes. |
| **P2** | **Read-only `GET /tokli/api/compressors` already in S3** (registry metadata, `enabled`, availability), because the Compressors page needs kind, equivalence and assumptions (ARCH: the UI reads them from this endpoint). Changing settings stays in S4. | Yes. |
| **P3** | **Evaluation status on the Compressors page (UI-003)** waits for S4, when the records' packaging is decided (X3). | Yes. |
| **P4** | **Labels of mixed totals (A2, A3):** `calibrated` (or `exact`) only when every request in the total is; otherwise `estimate` with `calibrated_share` shown next to it (e.g. "estimate · 92 % calibrated"). Conservative: never claims more precision than the weakest part. | Yes. |
| **P5** | **Time zones:** IANA names, with the `tzdata` package as a new runtime dependency (pure data, maintained by the Python core team, Apache-2.0). Without it, Windows would support only UTC. The dashboard sends the browser's zone. | Yes. |
| **P6** | **Money in S3:** a `cost` block with `null` and the reason `no_price_book` until S6; the UI shows "—". | Yes. |
| **P7** | **Host check on every `/tokli/*` route now** (not only on mutations in S4): requests whose `Host` is not the bound loopback address and port get 403. That closes DNS-rebinding reads of metadata. The proxy routes `/anthropic/*` are not affected. | Yes. |
| **P8** | **Dashboard at `http://127.0.0.1:8787/tokli/`.** `tokli serve` prints this address at startup. | Yes. |
| **P9** | **Browser test (AC-UI-2):** Playwright with headless Chromium as a development dependency, run in **one** CI job (Ubuntu, Python 3.12) and locally only when installed. The other 8 jobs check the API and the static files without a browser. ADR 0006. | Yes. The alternative (no browser test) leaves the method-label rule untested in the real UI. |
| **P10** | **Scope readings** (table above, A1–A9, X1–X4, M1–M4). | Accept as proposed. |

## 8. Implementation decisions (decided by Claude, recorded)

- **I1.** `MetricsQuery` in `tokli.app.metrics`. It takes validated filters and returns API
  dictionaries; `tokli.telemetry.queries` holds the SQL and returns rows.
- **I2.** Calibration is applied at query time, per request (TELEMETRY_AND_COST §1): stored
  figures stay estimates.
- **I3.** UI: vanilla HTML, CSS and ES modules in `src/tokli/ui/`, charts as hand-written SVG,
  no external resources. The only strings it knows are field names of the API, never compressor
  ids (AC-UI-1 lint).
- **I4.** JSON schemas for every endpoint in `tests/contract/api/`, checked with `jsonschema` as a
  development dependency (ADR 0006 together with P9).
- **I5.** Read-only SQLite connections per query (`mode=ro` URI), opened in the worker thread.
- **I6.** A synthetic 100k-row database for the query-time measurement, generated by a benchmark
  script (`benchmarks/metrics.py`), reported in the completion report.

## 9. Test plan

| Requirement / AC | Tests |
|---|---|
| API `requests` (A9) | `test_requests_list_newest_first_and_paged`, `test_requests_list_metadata_only` |
| `metrics/summary` (A1–A5, P4, P6) | `test_summary_totals_hand_computed` (mixed calibrated, estimate, exact and missing usage), `test_summary_labels_mixed_totals_as_estimate_with_share`, `test_summary_compressor_filter`, `test_summary_cost_block_null_until_s6`, `test_summary_empty_database` |
| `metrics/timeseries` (A6, P5) | `test_timeseries_hour_and_day_buckets`, `test_timeseries_buckets_follow_tz_across_dst` |
| `metrics/compressors` (A8) | `test_compressor_aggregates_hand_computed`, `test_latency_without_benefit_flag` |
| TC-013 / AC-TC-7 | `test_overhead_percentiles_by_bucket` (300 records, hand-computed), `test_target_is_reference_not_status`, `test_unknown_size_bucket` |
| API-002, TM-005, AC-TM-4 | `test_every_api_token_field_has_method` (extended to every new endpoint) |
| API-003 | `test_metrics_filters_validated` |
| API-001, AC-API-2 | `test_api_returns_no_content_or_credentials` (extended) |
| AC-API-1, API-004 | `test_api_contract_schemas` (JSON schemas for every endpoint) |
| API-008 | `test_import_contracts` (new contract) |
| P2 | `test_compressors_endpoint_read_only_metadata` |
| P7 | `test_tokli_routes_reject_foreign_host`, `test_proxy_routes_ignore_host_check` |
| M2 | `test_metrics_telemetry_disabled`, `test_metrics_query_failure_isolated` |
| UI-001, AC-UI-1 | `test_ui_has_no_compressor_specific_code` |
| UI-002, AC-UI-2 | `test_ui_renders_method_labels` (Playwright, one CI job) |
| UI-003 | `test_ui_shows_kind_equivalence_and_assumptions` (Playwright) |
| UI-006, AC-UI-4 | `test_wheel_contains_ui_assets`, `test_ui_assets_load_offline`, `test_ui_assets_served_with_explicit_content_types` |
| UI-008 | `test_ui_usable_at_360px` (Playwright) |
| UI-009 | `test_ui_overhead_target_is_reference_line` (Playwright) |
| R1 | `benchmarks/metrics.py` (reported) |
| Roadmap exit | dogfood check by the human: open the dashboard during a Claude Code session |

Answers 2026-10-03: P1–P10 accepted as recommended ("accetto le tue proposte").
Spec delta (uncommitted): SPEC 013 (TC-013 percentiles and `unknown` bucket; new TC-015 totals and
labels, TC-016 per-compressor aggregates; AC-TC-11, AC-TC-12), SPEC 015 (requests paging,
read-only compressors endpoint in S3; new API-009 host check, API-010 filters, API-011 empty /
disabled / failure, API-012 cost block; AC-API-6, AC-API-7), SPEC 016 (new UI-011 URL and content
types; AC-UI-5; browser tests in one CI job; evaluation status from S4), TOKLI_TELEMETRY_AND_COST
§3 (labels of mixed totals).

Gate 1 record: **approved 2026-10-03**, the human's words: "Approvo s3. Test live alla fine" (the live
dogfood check runs at the end of the slice). Spec status lines set in SPEC 013, 015 and 016.
