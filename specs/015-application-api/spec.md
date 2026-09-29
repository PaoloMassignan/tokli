# SPEC 015 — Application API (metrics, compressors, configuration, diagnostics)

Status: Draft · Slices: S1 (`requests/{id}`), S3 (metrics), S4 (config), S9 (diagnostics)

## Purpose
One JSON API under `/tokli/api` that the dashboard, the CLI and any replacement UI consume.
It exposes application use cases, never storage tables or compressor objects.

## Endpoints (v1)

| Method & path | Returns / does | Slice |
|---|---|---|
| `GET /tokli/api/requests?limit&cursor` | recent request summaries (metadata only) | S3 |
| `GET /tokli/api/requests/{id}` | trace + decisions + stats for one request (from buffer or DB) | S1 |
| `GET /tokli/api/metrics/summary?from&to&provider&model&compressor&kind&tz` | totals: requests, original/forwarded/saved tokens with methods, saving %, cost block | S3 |
| `GET /tokli/api/metrics/timeseries?…&bucket=hour|day` | same figures per bucket | S3 |
| `GET /tokli/api/metrics/compressors?…` | per-compressor aggregates (TOKLI_TELEMETRY_AND_COST §3) | S3 |
| `GET /tokli/api/compressors` | registry: spec metadata + `enabled`, `available`, `unavailable_reason`, `locked_by` | S4 |
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

## Acceptance criteria
- AC-API-1: JSON-schema contract tests for every endpoint (golden schemas in `tests/contract/api/`).
- AC-API-2: a canary scan of all API responses after the fixture traffic finds no content or keys.
- AC-API-3: a PATCH on a key pinned by `TOKLI_COMPRESSION__POLICY` → 409 with `source: env`.
- AC-API-4: a cross-origin POST/PATCH → 403. A same-origin one succeeds.
- AC-API-5: after a PATCH, the next request's `config_hash` changes and its decisions reflect the new setting. In-flight requests use the old snapshot.

## Test scenarios
`test_api_contract_schemas` · `test_api_returns_no_content_or_credentials` · `test_every_api_token_field_has_method` ·
`test_metrics_filters_validated` · `test_patch_pinned_key_conflict` · `test_patch_unknown_key_rejected` ·
`test_mutation_rejects_foreign_origin` · `test_config_change_atomic_snapshot` · `test_import_contracts`
