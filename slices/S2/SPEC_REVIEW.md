# S2 — Spec review

Slice: **S2 — Exact usage and honest numbers (Anthropic)** (`TOKLI_ROADMAP.md`).
Status: **Human Gate 1 passed 2026-10-02.** Implementation in progress.

Decisions already given by the product owner at S1 Gate 2 (2026-10-02) and applied here:

- a deterministic cache of compressor results per text (allowed by CC-006);
- request header **names** persisted in the request record;
- an optional rotating log file in the data dir (TOKLI_OBSERVABILITY §6).

## Scope

**Roadmap content.** Provider usage from Anthropic responses: the non-streaming JSON body and a
passive copy of the SSE stream. Mapping into the Tokli categories. A calibration factor `k` per
request and a calibrated saving. A method label on every token figure. Experiment E4 (Anthropic
part), with its results written into SPEC 003. The three S1 Gate 2 additions.

Exit (roadmap): the trace shows exact forwarded usage and a calibrated saving for streamed Claude
Code requests.

**Requirements in scope (proposed):**

| Spec | In S2 | Deferred (slice) |
|---|---|---|
| 002 proxy | PX-014 (`accept-encoding: identity` for transformable endpoints) | `/openai` prefix (S5) |
| 003 Anthropic | AN-005, AN-006, AN-007, AN-009; Q3 closed by E4 | Q4 `count_tokens` compression (stays verbatim, AN-008; not S2) |
| 008 tokens | TM-003, TM-004, TM-005 (all methods), TM-009 | E3 tokenizer choice (unscheduled) |
| 009 compression core | CC-006 is the basis of the result cache (no requirement changes) | CC-009, CC-018, CC-019, CC-021 (S4/S8) |
| 013 telemetry | TC-001 usage, `k` and whole-request estimate fields filled; TC-012 first forward migration (schema v2) | TC-004…TC-009 cost (S6); TC-013 metrics API (S3) |
| 014 observability | OB-002 `usage` span with real content; OB-011 calibration-outlier condition; OB-012 persisted (P3) | OB-009 debug-content mode |
| 015 API | `GET /tokli/api/requests/{id}` shows usage, `k` and calibrated figures with methods | metrics endpoints (S3) |
| 017 configuration | new keys `limits.usage_parser_buffer`, the result-cache key, the log-file key (P2, P4) | UI layer (S4) |

## 1. Ambiguities

| Id | Requirement | Question | Proposed reading |
|---|---|---|---|
| A1 | TM-004, TELEMETRY_AND_COST §1 | What is `exact_input_total`? | `input + cache_read + cache_write_5m + cache_write_1h`. Output tokens never enter `k`. |
| A2 | TM-004, §1 | What does the whole-request estimate cover? §1 says "segment texts + `json.dumps(non-text structure)`". Base64 images and documents, and thinking signatures, would add hundreds of thousands of meaningless "tokens" and make `k` useless for any request that contains a screenshot or a PDF (Claude Code's `Read` returns those inside tool results). | Count every segment text plus the JSON of the remaining structure, **with binary payloads excluded**: `source.data` of `image`/`document` blocks, `signature` of `thinking` blocks and `data` of `redacted_thinking` blocks. E4 reports the resulting `k` distribution. See P5. |
| A3 | AN-005, AN-009 | Does the 1 MiB bound also apply to non-streaming bodies? AN-009 speaks of "unparsed event data". | Yes. The non-streaming body is parsed only if it fits the same bound. Beyond it, usage is `unavailable`. Non-streaming answers are well under 1 MiB in practice. |
| A4 | AN-006, AC-AN-3 | What is a "partial" usage and where is the flag stored? The record has only `usage_source ∈ {provider, unavailable}`. | Add the value `provider_partial`: the stream ended (error event, upstream break or client disconnect) after `message_start` but without a final `message_delta`. Input categories are complete at `message_start`, so `k` is still computed. Output is labelled partial. See P6. |
| A5 | AN-006, Q3 | Which `message_delta` value wins when fields repeat? | The last non-null value per field (as the spec already says). E4 confirms whether input fields are repeated. |
| A6 | TM-004 | Is `k` computed for requests that passed through (no saving)? | Yes, whenever usage and the whole-request estimate exist. `k` then says how well the local tokenizer matches the provider, which is useful for E3 and OB-011 even when nothing was saved. The calibrated saving is then `0`. |
| A7 | TM-005 | Which method applies to which figure? | Usage categories: `exact`. Mutable-scope original/forwarded and per-compressor figures: `estimate` (stored as estimates, TELEMETRY_AND_COST §1). Request saving: `calibrated` when `k` exists and is in range, else `estimate`. Original whole-request size: `calibrated` or `estimate`, never `exact`. |
| A8 | OB-011 | "Calibration outliers exceed 20 % of the last 100 requests": over which requests? | Over the last 100 requests for which `k` could be computed. Fewer than 20 such requests → the check reports `ok` with `n`. |
| A9 | TOKLI_OBSERVABILITY §6 | How often is a calibration outlier logged as WARNING? | At most one WARNING per minute (as for sink failures, TC-011). Every outlier is still in its trace. |

## 2. Contradictions

| Id | Where | Contradiction | Proposed resolution |
|---|---|---|---|
| X1 | AC-AN-3 vs TELEMETRY_AND_COST §2 | AC-AN-3 asks for a "partial" flag; the record has no such value. | A4 / P6. |
| X2 | AN-009 vs SPEC 017 | AN-009 names `limits.usage_parser_buffer`, but the configuration key table does not contain it. | Add it to SPEC 017 (default 1 MiB). |
| X3 | TOKLI_OBSERVABILITY §4 vs AN-007 | The closed reason-code set has no codes for "usage unavailable". AN-007 only says `unavailable`. Without a reason, "why is there no usage?" cannot be answered from the trace, which §4 requires for decisions. | Extend the closed set with `usage_unavailable(<why>)`, `<why> ∈ {upstream_status, content_encoding, buffer_limit, parse_error, no_usage, client_disconnected}`, and with `calibration_outlier` and `calibration_unavailable`. See P7. |

## 3. Missing behaviour

- **M1. Log file keys.** TOKLI_OBSERVABILITY §6 describes the file (10 MB × 5, data dir) but no
  configuration key exists. See P4.
- **M2. Result-cache keys and bounds.** No spec describes the cache. It needs a size bound, an
  off switch and visible hit counts. See P2.
- **M3. Persisted header names.** OB-012 covers the trace only. Persisting them adds a column to
  `requests`: schema v2, the first forward migration (TC-012). See P3.
- **M4. Usage of verbatim routes.** `count_tokens` and `models` are relayed verbatim and have no
  record (TC-001 covers transformable requests). Usage is parsed only for `POST /v1/messages`.

## 4. Portability concerns

- **Log file rotation on Windows.** Python's `RotatingFileHandler` renames the file. On Windows the
  rename fails while another process holds the file open (a second Tokli, an editor or `tail`).
  Decision: a rotation failure never stops Tokli; the handler keeps writing to the current file and
  counts the failure. Tested on all 3 OSes with the file held open.
- **Log file encoding and line endings:** UTF-8, `\n` on every OS (fingerprint-friendly, readable
  everywhere).
- **SQLite migration:** `ALTER TABLE … ADD COLUMN` only (no rebuild), the same on every OS.
- **SSE parsing:** lines may end in `\n`, `\r\n` or `\r` (the SSE standard allows all three), and
  events may be split anywhere across chunks, including inside a UTF-8 character. Property test
  over random chunk splits.

## 5. Observability requirements for this slice

- `usage` span: source (`provider`, `provider_partial`, `unavailable`), reason when unavailable,
  categories with method `exact`, number of SSE events seen by type (metadata only), parse time.
- `calibrate` span: `k`, the whole-request estimate, the calibrated saving, outlier flag, time.
- Result cache: hits and misses per compressor in the trace. Nothing in `tokli doctor`, which runs
  without a server.
- Summary log line: `tokens` gains the usage categories and the calibrated saving, each with its
  method (TM-005, OB-010).
- Checklist §8: new paths emit spans; new decisions use reason codes (X3); new telemetry fields in
  schema, API and retention; credential and content scans extended to the usage tee, the log file
  and the cache; the request view shows the new fields.

## 6. Architectural risks

- **R1. The whole-request estimate is expensive.** Tokenizing a 200k-token request costs tens of
  milliseconds, the size of the whole E9 overhead. Decision (I1): compute it **off the latency
  path**, in a worker thread started right after the request is sent upstream, while the model is
  thinking. The client is never delayed, so `ms_tokli_overhead` keeps its meaning. Token counts are
  cached per text, so repeated history costs almost nothing after the first request.
- **R2. The SSE tee must not delay the stream.** The relay yields each chunk **before** feeding the
  parser, so parsing happens while waiting for the next chunk. AC-PX-3/AC-AN-4 (causal relay test)
  runs with the tee active.
- **R3. Result cache correctness.** A cache keyed by less than CC-006's inputs would return wrong
  output. The key includes the compressor id and version, the compressor's effective config, the
  segment's `SegmentView` and the full text (hashed with SHA-256, with the length). Test: the same
  text with a different view (e.g. a verbatim tool) is not served from the cache.
- **R4. New dependency direction.** None. The usage parser lives in `tokli.protocols`
  (`anthropic_messages` usage functions), the calibration in `tokli.tokens`, the cache in
  `tokli.compression`. No new third-party dependency.
- **R5. Schema v2.** ADR 0005 records the migration (persistence format change, CLAUDE.md §6).
- **Seams introduced:** none. The cache is a concrete class inside the engine. The usage parser is
  concrete for Anthropic; a shared interface waits for the second protocol (S5).

## 7. Product questions (for the human)

| # | Question | Recommendation |
|---|---|---|
| **P1** | **E4 and the live acceptance** cost a little money and use your credentials, so you run them. Proposed run: (a) a short Claude Code session through Tokli (API key, streamed); (b) one non-streaming `curl` request with a pretty-printed JSON tool result, so a **non-zero** saving is calibrated live (Claude Code's `Read` and `Bash` are verbatim tools, so its own sessions save almost nothing). Tokli itself records the event types and usage fields: no separate recorder. The "error event mid-stream" case cannot be triggered on purpose; it stays fixture-based and is labelled so in SPEC 003. | Yes, as described. |
| **P2** | **Result cache**: on by default, bounded by memory, with key `compression.result_cache_mb` (default 64; `0` = off). Hits and misses per compressor in the trace only (no new DB columns). The cache is in memory and empties on restart. | Yes. |
| **P3** | **Header names persisted** as a sorted JSON list in a new `requests.header_names` column (schema v2, forward migration of existing DBs, ADR 0005). Names only, never values (OB-012). | Yes. |
| **P4** | **Log file**: key `observability.log_file` (default `false`). When `true`, logs also go to `<data dir>/logs/tokli.log`, rotating at 10 MB, 5 files kept, always JSON lines (machine-readable) whatever `--log-format` says for the console. | Yes. |
| **P5** | **Whole-request estimate** without binary payloads (A2). Images and documents then count 0 in the estimate while the provider counts them, so `k` rises a little on such requests; the outlier rule (TM-009) catches extreme cases. | Yes. The alternative (skip `k` whenever media is present) loses `k` on many Claude Code requests. |
| **P6** | **Partial usage**: new value `usage_source: provider_partial` (A4). | Yes. |
| **P7** | **New reason codes** (X3): `usage_unavailable(<why>)`, `calibration_outlier`, `calibration_unavailable`. | Yes. |
| **P8** | **Scope readings** (table above, A1–A9, X2, M4). | Accept as proposed. |

## 8. Implementation decisions (decided by Claude, recorded)

- **I1.** Whole-request estimate in a worker thread after the request is sent upstream (R1). If
  the response finishes first, the record waits for the estimate before it is written; the client
  is not affected.
- **I2.** Usage parsing yields first, parses second (R2). The parser is an incremental SSE decoder
  with a byte budget (AN-009). When the budget is hit it stops parsing and drops its buffer; it
  never buffers more.
- **I3.** PX-014: on `POST /v1/messages` the forwarded `accept-encoding` is replaced by `identity`.
  If the upstream still answers with a content encoding, the body is relayed unchanged and usage is
  `unavailable(content_encoding)`.
- **I4.** `k` and the calibrated saving are stored per request; per-compressor figures stay
  estimates in storage, and the query side applies `k` (TELEMETRY_AND_COST §1).
- **I5.** Result-cache key and bound as in R3 and P2. Eviction: least recently used. The engine
  still runs its checks on a cached result (protected spans, token non-increase) — they are cheap
  and keep CC-005/CC-007 independent of the cache.
- **I6.** E9 gets a "repeated history" scenario (request n+1 contains request n) so the cache's
  effect is measured. The cold baseline stays as committed in S1 and remains the regression
  reference.
- **I7.** Fixtures for usage come from the public Anthropic documentation shapes, are synthetic,
  and are confirmed (or corrected) by E4 before Gate 2.

## 9. Test plan

| Requirement / AC | Tests |
|---|---|
| PX-014 | `test_transformable_request_asks_identity_encoding`, `test_verbatim_route_keeps_client_accept_encoding` |
| AN-005, TM-003 | `test_anthropic_usage_non_stream` (all categories, 5m/1h split and fallback) |
| AN-006, AC-AN-3 | `test_anthropic_usage_stream`, `test_anthropic_usage_stream_with_error_event` (partial), `prop_usage_stream_any_chunk_split` (`\n`/`\r\n`/`\r`, split UTF-8) |
| AN-007, X3 | `test_usage_parser_failure_is_unavailable` (each `<why>`) |
| AN-009 | `test_usage_parser_memory_bounded` (stream and non-stream) |
| AC-AN-4, R2 | `test_stream_causal_relay` re-run with the usage tee active |
| TM-004, AC-TM-5 | `test_calibration_factor`, `test_whole_request_estimate_excludes_binary_payloads` |
| TM-009, AC-TM-5 | `test_calibration_outlier_falls_back_to_estimate` |
| TM-005, AC-TM-4 | `test_every_api_token_field_has_method` (request view and log line) |
| OB-011 | `test_health_degraded_on_calibration_outliers` |
| OB-012, P3, TC-012 | `test_header_names_persisted`, `test_schema_migration_forward` (v1 DB → v2, no data lost) |
| P2, CC-006 | `test_result_cache_hit_gives_identical_output`, `test_result_cache_key_includes_view_and_config`, `test_result_cache_bounded`, `test_result_cache_off` |
| P4 | `test_log_file_written_when_enabled`, `test_log_file_rotates`, `test_log_file_rotation_failure_does_not_stop_tokli`, `test_log_file_contains_no_credentials_or_content` |
| I1, OB-002 | `test_trace_contains_usage_and_calibrate_spans`, `test_estimate_off_latency_path` |
| Roadmap exit | live run P1 (by the human), recorded in `slices/S2/LIVE_TEST.md` |

Answers 2026-10-02: P1–P8 accepted as recommended ("accetto le tue proposte").
Spec delta (uncommitted): SPEC 003 (AN-007 reasons, AN-009 non-stream bound, new AN-010,
AC-AN-6, Q3 E4 method), SPEC 008 (TM-004 definitions, TM-005 method map, TM-009 reasons, AC-TM-7),
SPEC 009 (new CC-024, AC-CC-13), SPEC 013 (TC-012 v2, AC-TC-9), SPEC 014 (OB-011 window,
OB-012 persisted, new OB-013, AC-OB-6, AC-OB-7), SPEC 017 (keys added in S2),
TOKLI_OBSERVABILITY §4 and §6, TOKLI_TELEMETRY_AND_COST §1 and §2.

Gate 1 record: **approved 2026-10-02**, the human's words: "Approvo s2". Spec status lines set
("Approved for S2 (2026-10-02)") in SPEC 002, 003, 008, 009, 013, 014 and 017.
