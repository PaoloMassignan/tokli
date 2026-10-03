# TOKLI — Observability

Normative requirements: `specs/014-observability`. Observability is part of the Definition of
Done of **every** vertical slice (see `TOKLI_ROADMAP.md`).

## 1. Two different questions, two different outputs

| | Product telemetry | Diagnostic observability |
|---|---|---|
| Question | "How much is Tokli saving, and with which compressor?" | "Why did *this* request behave like that?" |
| Shape | Aggregatable rows (`RequestRecord`, `CompressorStats`) | Per-request trace: spans, decisions, errors |
| Storage | SQLite, 30-day retention | In-memory ring buffer (last N = 500 traces) + structured log lines |
| Consumers | Dashboard, metrics API | Recent-request view, `GET /tokli/api/requests/{id}`, log files, doctor |
| Content | Never | Never by default; opt-in debug-content mode only |

## 2. Request correlation

- Every request gets a ULID `request_id` at the HTTP edge. It goes into every log line, every
  trace span and every telemetry row, and back to the client as `x-tokli-request-id`
  (config `observability.response_header`, default on).
- Upstream correlation IDs (`request-id` from Anthropic, `x-request-id` from OpenAI) are recorded
  in the trace so a provider-side support case can be matched.

## 3. Trace format

```text
Request 01J8Z…A83F  anthropic_messages  model=claude-sonnet-4-…  stream=true  policy=LOSSLESS_ONLY
  0.3 ms  route                 → provider=anthropic endpoint=/v1/messages
  1.9 ms  parse                 → 212 segments (37 mutable)
  0.6 ms  analyze.reminders     → 9 protected spans
  0.4 ms  analyze.features      → json:4 grep:0 diff:1 log:0
  3.1 ms  transform.compression
            json_minify   considered=37 applicable=4 accepted=3 saved=1,882 est  2.2 ms
                          skipped: too_small=29 verbatim_tool=4 ; rejected_no_gain=1
  0.8 ms  render                → 3 patches, body 812,344 → 805,101 bytes
  0.0 ms  auth                  → passthrough (credential_kind=oauth)
  —       upstream              → 200, ttfb 1,240 ms, total 9,880 ms, upstream_req_id=req_…
  —       usage                 → input 1,905  cache_read 142,330  cache_write_5m 2,210  output 612 (exact)
          tokli_overhead 7.1 ms
          saving 1,882 est → 1,964 calibrated (k=1.044); cost saved ≈ $0.0012 [0.0006–0.0074] proportional
```

Each span has a name, start offset, duration, attributes, and a status of `ok`, `skipped` or
`error(code)`.

## 4. Decision records

Decisions that change what is forwarded are always recorded, with a machine-readable reason:

| Decision | Reason codes (closed set, extended only by spec change) |
|---|---|
| Route | `known_endpoint`, `verbatim_path`, `unknown_prefix` |
| Pass-through (whole request) | `policy_off`, `no_mutable_segments`, `no_applicable_compressor`, `no_gain`, `parse_error`, `content_encoding`, `too_large`, `render_error`, `pipeline_error` |
| Compressor skipped for a segment | `disabled`, `policy_forbids(kind)`, `unavailable(dep)`, `kind_not_supported`, `too_small`, `verbatim_tool`, `not_applicable(<compressor-specific short code>)`, `after_terminal`, `budget_exhausted` |
| Compressor result rejected | `no_gain`, `below_min_gain`, `protected_span_changed`, `reference_target_modified`, `exception`, `timeout`, `decode_mismatch` (debug verification mode) |
| Stage failure | `stage_exception(<stage id>)` |
| Upstream | `upstream_status(<code>)`, `upstream_unreachable`, `upstream_timeout`, `client_disconnected` |
| Usage | `usage_unavailable(<why>)`, `<why>` ∈ `upstream_status`, `content_encoding`, `buffer_limit`, `parse_error`, `no_usage`, `client_disconnected` (AN-007) |
| Calibration | `calibration_outlier`, `calibration_unavailable` (TM-009) |

"Why didn't `json_minify` run on my request?" is answered from the trace alone.

## 5. Privacy-safe logging

| Rule | Mechanism | Test |
|---|---|---|
| Credentials are never logged | Header allow-list for logging (credential headers are never in it) + a redaction filter on the root logger masking `sk-…`, `sk-ant-…`, `Bearer …`, `x-api-key` values | `test_logs_never_contain_credentials` feeds known tokens through every code path and scans all log output and the SQLite file |
| Prompt content is never logged by default | Log calls take structured fields. No logger call receives segment text, except the debug-content writer | `test_default_logging_contains_no_prompt_text` (canary strings in fixtures) |
| Debug-content mode is explicit and visible | `observability.debug_content: true` **and** env `TOKLI_DEBUG_CONTENT=1` (both required). Startup banner, a persistent red UI banner, doctor warning. Writes to a separate directory with a 24 h TTL and a 200 MB cap. | `test_debug_content_requires_both_switches`, `test_debug_content_banner_visible` |
| Upstream error bodies | Logged truncated to 2 KB only for 4xx/5xx; these may echo prompt fragments, so they are subject to the same content rule (stored only in debug-content mode; otherwise status + provider error type + message field are logged) | `test_upstream_error_logging_respects_content_rule` |

## 6. Log output

- Format: JSON lines (default) or human-readable (`--log-format text`), to stderr and optionally
  to a rotating file in the data dir (10 MB × 5) when `observability.log_file` is true. The file
  is always JSON lines, UTF-8 with LF line endings, at `<data dir>/logs/tokli.log`. A failed write or
  rotation (for example a file held open on Windows) never stops Tokli (OB-013).
- Levels: `INFO` per request summary (one line), `DEBUG` per-stage lines, `WARNING` for degraded
  states (tokenizer calibration outliers, sink failures), `ERROR` for Tokli faults.
- No log line exceeds 8 KB (a guard truncates and marks it).

## 7. Health and degraded-state signals

- `GET /tokli/health` → `{"status":"ok"|"degraded", "checks": {...}}` without auth. It never
  contains config values beyond version.
- Degraded if: telemetry sink failing, tokenizer unavailable (startup would normally fail),
  a compressor `unavailable` while enabled, or clock skew > 5 min against upstream `date` header.

## 8. Definition of Done — observability checklist per slice

- [ ] New code paths emit spans with durations.
- [ ] Every new decision uses a reason code from §4 (or the spec is extended first).
- [ ] New telemetry fields are in the schema, the API contract and the retention job.
- [ ] Credential and content scan tests cover the new paths.
- [ ] The recent-request view shows the new information, or the slice explains why not.
