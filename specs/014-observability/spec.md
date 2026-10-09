# SPEC 014 — Observability

Status: Draft · Slice: S1 onward (DoD of every slice) · Related: TOKLI_OBSERVABILITY.md (explanatory)
Approved for S1 (2026-09-30): OB-001…OB-008, OB-010, OB-011 (sink failure, unavailable compressor), OB-012. OB-009 deferred to the first slice that needs debug content.
Approved for S2 (2026-10-02): OB-011 (calibration outliers), OB-012 (persisted), OB-013.

## Requirements

| ID | EARS requirement |
|---|---|
| OB-001 | WHEN a request arrives, THE SYSTEM SHALL assign a ULID `request_id` and attach it to every log line, trace span and telemetry row for that request. |
| OB-002 | THE SYSTEM SHALL record a trace per request with spans `route`, `parse`, each pipeline stage, `render`, `auth`, `upstream` (TTFB and total) and `usage`, including durations and outcomes, and SHALL compute `tokli_overhead_ms`. |
| OB-003 | THE SYSTEM SHALL keep the last `observability.trace_buffer` (default 500) traces in a bounded in-memory buffer and serve them at `GET /tokli/api/requests/{id}`. |
| OB-004 | WHEN the SYSTEM passes through, skips or rejects, THE SYSTEM SHALL record a reason code from the closed set in TOKLI_OBSERVABILITY §4. |
| OB-005 | THE SYSTEM SHALL record upstream correlation identifiers (`request-id`, `x-request-id`) when present. |
| OB-006 | WHEN the upstream returns ≥ 400, THE SYSTEM SHALL log status, provider error type and message field, and SHALL log the raw error body only in debug-content mode. |
| OB-007 | THE SYSTEM SHALL NOT write credential values to any log, trace, telemetry row or API response. |
| OB-008 | THE SYSTEM SHALL NOT write segment text, prompt or response content to any sink unless `observability.debug_content` is true **and** `TOKLI_DEBUG_CONTENT=1` is set. |
| OB-009 | WHILE debug-content mode is active, THE SYSTEM SHALL show a startup banner, a persistent UI banner and a doctor warning, and SHALL store captured content only in `<data>/debug-content/` with a 24 h TTL and a 200 MB cap. |
| OB-010 | THE SYSTEM SHALL emit one INFO summary log line per request (JSON by default) containing request_id, provider, model, outcome, reason, tokens (with methods), status and overhead. |
| OB-012 | THE trace and the persisted `RequestRecord` (`header_names`) SHALL record the **names** of the client's request headers (lower-cased, sorted) and SHALL NOT record any header value. |
| OB-013 | WHERE `observability.log_file` is true, THE SYSTEM SHALL also write log lines as JSON to `<data dir>/logs/tokli.log`, UTF-8 with LF line endings, rotating at 10 MB and keeping 5 files. IF writing or rotating the file fails, THEN THE SYSTEM SHALL keep serving and keep logging to stderr. |
| OB-011 | THE `GET /tokli/health` endpoint SHALL report `degraded` with named checks when a sink fails, an enabled compressor is unavailable, or calibration outliers exceed 20 % of the last 100 requests for which `k` was computed (with fewer than 20 such requests the check is `ok`). It SHALL also report the informational check `applicability`, `ok` or `not_applying: <ids>` (TC-021, over the last 7 days), which never makes the status `degraded`. (S8h P3.) |

## Acceptance criteria
- AC-OB-1: a single request produces log lines, a trace and DB rows sharing one request_id, and the client sees it in the header.
- AC-OB-2: the trace for a compressed streamed request contains every span of OB-002 with non-negative durations, and `overhead ≤ total − upstream`.
- AC-OB-3: the buffer never exceeds its bound under 10k requests.
- AC-OB-4: canary credential and content scans pass for all fixture paths and error paths.
- AC-OB-6 (OB-012): after a restart, the header names of an earlier request are still readable from the DB; no header value is in the DB.
- AC-OB-7 (OB-013): with the key on, request summary lines appear in the file as JSON even with `--log-format text`; the file rotates at the bound; a rotation that fails because the file is held open (Windows) does not stop Tokli; credential and content scans pass on the file.
- AC-OB-5: debug-content needs both switches. The banner is present in UI HTML and doctor output. TTL cleanup works.

## Test scenarios
`test_request_id_propagates_everywhere` · `test_trace_contains_all_spans` · `test_trace_buffer_bounded` ·
`test_reason_codes_closed_set` · `test_upstream_correlation_ids_recorded` · `test_upstream_error_logging_respects_content_rule` ·
`test_logs_never_contain_credentials` · `test_default_logging_contains_no_prompt_text` ·
`test_debug_content_requires_both_switches` · `test_debug_content_banner_visible` · `test_debug_content_ttl_and_cap` ·
`test_request_summary_log_line` · `test_health_degraded_conditions` · `test_trace_records_header_names_only` ·
`test_header_names_persisted` · `test_health_degraded_on_calibration_outliers` · `test_log_file_written_when_enabled` ·
`test_log_file_rotates` · `test_log_file_rotation_failure_does_not_stop_tokli` · `test_log_file_contains_no_credentials_or_content`
