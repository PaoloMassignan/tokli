# SPEC 015 — Application API (metrics, compressors, configuration, diagnostics)

Status: Draft · Slices: S1 (`requests/{id}`), S3 (metrics), S4 (config), S9 (diagnostics)
Approved for S1 (2026-09-30): `GET /tokli/api/requests/{id}`, `GET /tokli/health`, API-001, API-002, API-004.
Approved for S3 (2026-10-03): `GET /tokli/api/requests`, `metrics/summary|timeseries|compressors`, read-only `GET /tokli/api/compressors`; API-001…API-004, API-008…API-012.

## Purpose
One JSON API under `/tokli/api` that the dashboard, the CLI and any replacement UI consume.
It exposes application use cases, never storage tables or compressor objects.

## Endpoints (v1)

| Method & path | Returns / does | Slice |
|---|---|---|
| `GET /tokli/api/requests?limit&cursor` | recent request summaries (metadata only), newest first; `limit` default 50, max 500; `cursor` = the last `request_id` seen | S3 |
| `GET /tokli/api/requests/{id}` | trace + decisions + stats for one request (from buffer or DB) | S1 |
| `GET /tokli/api/metrics/summary?from&to&provider&model&compressor&kind&tz` | totals: requests, original/forwarded/saved tokens with methods, saving %, cost block | S3 |
| `GET /tokli/api/metrics/timeseries?…&bucket=hour|day` | same figures per bucket | S3 |
| `GET /tokli/api/metrics/compressors?…` | per-compressor aggregates (TOKLI_TELEMETRY_AND_COST §3) | S3 |
| `GET /tokli/api/compressors` | registry: spec metadata + `enabled`, `available`, `unavailable_reason`, `locked_by` | S3 (read-only), S4 (`locked_by`, evaluation status) |
| `GET /tokli/api/config` | effective config with per-key `source` and `locked` flags (secrets never included) | S4 |
| `PATCH /tokli/api/config` | set UI-override keys (`compression.policy`, `compressors.<id>.enabled`, selected options) | S4 |
| `GET /tokli/api/diagnostics` | doctor report as JSON | S9 |
| `GET /tokli/health` | health (SPEC 014) | S1 |

## Requirements

| ID | EARS requirement |
|---|---|
| API-001 | THE API SHALL return only metadata. No endpoint SHALL return prompt/response content or credential values (debug-content excepted, under OB-008/009 via a separate `/tokli/api/debug/*` namespace). |
| API-002 | EVERY token figure in API responses SHALL be an object `{value, method}`, and every money figure SHALL be `{estimate, low, high, method, currency, price_book_version}` or `{value: null, reason}`. |
| API-003 | THE metrics endpoints SHALL accept the filters `from`, `to`, `provider`, `model`, `compressor`, `kind` and `tz`, and SHALL validate them (400 with field errors). |
| API-004 | THE API SHALL be versioned by a top-level `api_version` field. Breaking changes require a new version. |
| API-005 | WHEN `PATCH /tokli/api/config` targets a key pinned by env/CLI, THE SYSTEM SHALL answer 409 naming the pinning source; WHEN it targets an unknown or non-UI-editable key, 400. |
| API-006 | THE SYSTEM SHALL reject mutating API requests whose `Origin` is present and not the Tokli origin, or whose `Host` is not the bound loopback host:port (403). |
| API-007 | WHEN configuration changes are accepted, THE SYSTEM SHALL persist them to `<data>/ui-overrides.yaml`, apply them atomically to subsequent requests, and return the new effective config and `config_hash`. |
| API-008 | THE API layer SHALL depend only on `tokli.app` use cases (import contract). |
| API-009 | THE SYSTEM SHALL answer 403 to any request under `/tokli/` whose `Host` header is not the bound address and port (or `localhost` / `127.0.0.1` / `[::1]` with that port when bound to loopback). Proxy routes are not affected. |
| API-010 | THE metrics endpoints SHALL interpret `from` and `to` as ISO-8601 instants with offset, half-open `[from, to)`, defaulting to the last 7 days; `tz` as an IANA time-zone name (default `UTC`) that sets the `timeseries` bucket boundaries; and `compressor` / `kind` as restricting the saving to that compressor's (kind's) marginal savings and the requests to those where it was considered. Invalid values SHALL give 400 `{api_version, error: {type: "invalid_parameter", fields: {<name>: <message>}}}`. |
| API-011 | WHEN no matching records exist, THE metrics endpoints SHALL return zero counts and `{value: null, reason: "no_data"}` figures. WHEN telemetry is disabled, they SHALL answer 503 `telemetry_disabled`. A failing query SHALL answer 500 `query_failed`, log one WARNING, and never affect proxied traffic. |
| API-012 | UNTIL a price book exists (S6), THE metrics responses SHALL carry `cost: {value: null, reason: "no_price_book"}`. |

## Acceptance criteria
- AC-API-1: JSON-schema contract tests for every endpoint (golden schemas in `tests/contract/api/`).
- AC-API-2: a canary scan of all API responses after the fixture traffic finds no content or keys.
- AC-API-3: a PATCH on a key pinned by `TOKLI_COMPRESSION__POLICY` → 409 with `source: env`.
- AC-API-4: a cross-origin POST/PATCH → 403. A same-origin one succeeds.
- AC-API-6 (API-009): a request to `/tokli/api/metrics/summary` with `Host: evil.example` gets 403; the same with the bound host succeeds; a proxy request is unaffected.
- AC-API-7 (API-010): `timeseries` day buckets in `Europe/Rome` and `America/New_York` follow local midnight across a DST change.
- AC-API-5: after a PATCH, the next request's `config_hash` changes and its decisions reflect the new setting. In-flight requests use the old snapshot.

## Test scenarios
`test_api_contract_schemas` · `test_api_returns_no_content_or_credentials` · `test_every_api_token_field_has_method` ·
`test_metrics_filters_validated` · `test_patch_pinned_key_conflict` · `test_patch_unknown_key_rejected` ·
`test_mutation_rejects_foreign_origin` · `test_config_change_atomic_snapshot` · `test_import_contracts` ·
`test_requests_list_newest_first_and_paged` · `test_requests_list_metadata_only` · `test_summary_compressor_filter` ·
`test_summary_cost_block_null_until_s6` · `test_summary_empty_database` · `test_timeseries_hour_and_day_buckets` ·
`test_timeseries_buckets_follow_tz_across_dst` · `test_compressors_endpoint_read_only_metadata` ·
`test_tokli_routes_reject_foreign_host` · `test_proxy_routes_ignore_host_check` · `test_metrics_telemetry_disabled` ·
`test_metrics_query_failure_isolated`
