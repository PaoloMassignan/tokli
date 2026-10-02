# S1 — Spec review

Slice: **S1 — Anthropic Messages, passthrough auth, one lossless compressor** (`TOKLI_ROADMAP.md`).
Status: **Human Gate 1 passed 2026-09-30.** Implementation in progress.

Decisions already given by the product owner (2026-09-29/30) and applied in this review:

- **C2:** the pipeline stage list is fixed in S1. User configuration of stages waits until a second
  ordering exists.
- **C3:** multi-compressor chain behaviour is tested in S4, with the second real compressor.
- **Live tests:** E1a (API key) and then E1b (Pro/Max OAuth), each in a separate terminal session
  that sets `ANTHROPIC_BASE_URL` only for that session.

## Scope

**Roadmap content.** Anthropic `POST /anthropic/v1/messages` (streaming and non-streaming),
every other `/anthropic/*` path relayed verbatim, passthrough auth, canonical model for user text
and tool results, the `analyze.reminders` analyzer, the `json_minify` compressor under a fixed
LOSSLESS_ONLY policy, token estimates, telemetry (log line and SQLite schema v1), trace buffer
and `GET /tokli/api/requests/{id}`, overhead measurement with the E9 baseline, and live test E1a.

**Requirements in scope (proposed; see P8 for the deferrals):**

| Spec | In S1 | Deferred (slice) |
|---|---|---|
| 001 canonical model | CM-001…CM-012 (Anthropic) | CM-013 `ToolRecord` list (S4, first consumer); OpenAI parts (S5/S7) |
| 002 proxy | PX-001…PX-013; `/anthropic` prefix only | PX-014 `accept-encoding: identity` (S2, first usage parser); `/openai` prefix (S5) |
| 003 Anthropic | AN-001…AN-004, AN-008 | AN-005…AN-007, AN-009 usage (S2) |
| 006 upstream/auth | UP-001, UP-002, UP-005, UP-006, UP-008, UP-009, UP-010; `credential_kind` | UP-003, UP-004, UP-007 inject mode (S5) |
| 007 pipeline | PL-003…PL-006, PL-008 (fixed list, C2), PL-007 (test-built stage) | PL-001 user-configured order and PL-002 (with configurability, C2) |
| 008 tokens | TM-001, TM-002, TM-005 (estimate label), TM-008 | TM-003, TM-004, TM-009 (S2) |
| 009 compression core | CC-001…CC-008, CC-010…CC-017, CC-020 (provisional record) | CC-009 chain/terminal (S4, C3), CC-018 (first non-prefix-stable compressor, S8), CC-019, CC-021, request scope (S4) |
| 010 compressors | CP-JM-001…CP-JM-005 | others (S4/S8) |
| 011 routing | RT-002…RT-006; RT-001 for the features with a consumer (`tokens`, `json_candidate`) | other features (with their compressors) |
| 012 evaluation | QE-016 `provisional` record for `json_minify` | smoke tier (S2.5) |
| 013 telemetry | TC-001, TC-002, TC-003, TC-010, TC-011, TC-012, TC-014 (fields present) | TC-004…TC-009 cost (S6); TC-013 metrics API (S3; S1 reports percentiles from the DB with a script) |
| 014 observability | OB-001…OB-008, OB-010, OB-011 (sink failure, unavailable compressor) | OB-009 debug-content mode (first slice that needs it); calibration outliers (S2) |
| 015 API | `GET /tokli/api/requests/{id}`, `GET /tokli/health`, API-001, API-002, API-004 | metrics, config and diagnostics endpoints (S3/S4/S9) |
| 017 configuration | new keys (table §3), N-level keys | UI layer (S4) |
| 018 portability | PT-008 port in use, remaining fresh-machine scenarios (alternative port, offline serve, hostile environment), MD-09, MD-10, MD-12, MD-22, MD-23, MD-24, MD-25 | PT-006 fingerprint CLI (S9, see P3) |

## 1. Ambiguities

| # | Where | Question | Proposed reading |
|---|---|---|---|
| A1 | CC-008 per-call timeout | A pure Python function cannot be interrupted safely in-process. | The engine measures each call and **discards** a result that took longer than `per_call_timeout_ms` (`failed(timeout)`). Hang protection comes from construction: cheap compressors are linear-time (CP-JM-005, tested). Real preemption needs a worker process; it will be reconsidered only for an `expensive` compressor. |
| A2 | CF-006 config hash "compression, pipeline, tokens, limits" | `compressors.<id>.enabled` changes behaviour but is not listed. | The hash covers `compression`, `compressors`, `tokens` and `limits`. `pipeline` has no keys in S1 (C2). |
| A3 | SPEC 017 keys are two-level (`section.key`), but `compressors.json_minify.enabled` and `upstreams.anthropic.base_url` are three-level | — | Keys may have any depth. Env names use `__` per level: `TOKLI_COMPRESSORS__JSON_MINIFY__ENABLED`, `TOKLI_UPSTREAMS__ANTHROPIC__BASE_URL`. |
| A4 | SPEC 009 `min_segment_tokens` | No default is given, and none is given for `json_minify.min_tokens` either. | See P1. |
| A5 | `verbatim_tools` when the tool name cannot be resolved | `None not in verbatim_tools` → it would be compressed. | See P2. |
| A6 | `analyze.reminders` "configured literal markers" | No config key exists, and C2 defers pipeline configuration. | S1 protects only `<system-reminder>` spans. Configurable markers wait for a real need. |
| A7 | RequestRecord `policy` | Policy switching arrives in S4. | Recorded as the constant `LOSSLESS_ONLY`, with no config key. |

## 2. Contradictions

| # | Between | Problem | Proposed fix |
|---|---|---|---|
| X1 | Roadmap S1 acceptance 5 ("fingerprint equal across the 3 CI OSes") vs SPEC 018 (fingerprint PT-006 in S9) | The fingerprint command does not exist in S1. | See P3. |
| X2 | AC-PX-3 ("chunk arrival times track upstream within 20 ms") vs TOKLI_TEST_STRATEGY §8 (no absolute ms thresholds before a baseline) and shared CI runners (tens of ms of jitter) | A timing threshold would be flaky, and it tests buffering only indirectly. | See P4. |
| X3 | PX-014 (`accept-encoding: identity` upstream) vs S1 (no response parsing) | In S1 it would change forwarded headers with no benefit. | Apply it in S2 with the usage parser. In S1 the client's `accept-encoding` is forwarded unchanged. |

## 3. Missing behaviour: new configuration keys (defaults from the specs unless marked)

| Key | Default | Source |
|---|---|---|
| `server.host` / `server.port` | `127.0.0.1` / `8787` | PX-001, fresh-machine scenario |
| `server.allow_remote` (also `--allow-remote`) | `false` | PX-001 |
| `upstreams.anthropic.base_url` | `https://api.anthropic.com` | UP-001 |
| `upstreams.anthropic.connect_timeout_s` / `read_timeout_s` | `10` / `600` | UP-009 |
| `tls.ca_bundle` | `null` (system/certifi bundle) | UP-008 |
| `limits.max_transform_bytes` | `33554432` (32 MiB) | CM-012 |
| `compression.segment_kinds` | `["TOOL_RESULT", "USER_TEXT"]` | SPEC 001 |
| `compression.verbatim_tools` | `["Read", "Bash", "shell", "shell_command", "container.exec"]` | SPEC 010 |
| `compression.min_segment_tokens` | **P1** | SPEC 009 |
| `compression.min_gain_tokens` / `min_gain_ratio` | `4` / `0.01` | CC-004 |
| `compression.request_budget_ms` / `per_call_timeout_ms` | `50` / `200` (provisional) | CC-014, CC-008 |
| `compression.verify_lossless` | `false` (tests turn it on) | CC-016 |
| `compressors.json_minify.enabled` | `true` (provisional) | SPEC 010 |
| `observability.trace_buffer` / `response_header` | `500` / `true` | OB-003, PX-012 |
| `observability.log_format` (also `--log-format`) | `json` (`text` optional) | TOKLI_OBSERVABILITY §6 |
| `telemetry.retention_days` | `30` | TC-010 |

## 4. Portability concerns

- **Streaming on Windows:** uvicorn and httpx behave the same, but socket close and cancel timing
  differ. Client-disconnect tests (PX-009) use events, not sleeps.
- **Paths in the SQLite location:** the data dir can contain non-ASCII characters (a user name).
  `sqlite3` gets a `str` path, and a test covers a non-ASCII data dir.
- **Port-in-use behaviour** differs (Windows allows some re-binds). The test binds the port with a
  plain socket first and asserts Tokli's one-line error, without relying on `SO_REUSEADDR` details.
- **CRLF in tool results** (MD-12): `json_minify` round-trip tests include CRLF and mixed input.
- **Tokenizer loading:** tiktoken's own loader writes a cache in the system temp directory
  (a machine-state side effect, MD-02). Tokli reads the verified file itself and builds the
  encoding from it, so no cache is written and no network is used (ADR 0002).

## 5. Observability requirements for this slice

Everything in `TOKLI_OBSERVABILITY.md §8`: spans for `route`, `parse`, `analyze.reminders`,
`analyze.features`, `transform.compression`, `render`, `auth`, `upstream` (TTFB and total) and
`usage` (recorded as `unavailable` until S2); reason codes from the closed set; one JSON summary
log line per request; the `x-tokli-request-id` header; the trace ring buffer and
`GET /tokli/api/requests/{id}`; credential and content canary scans over logs, SQLite and API
output; health `degraded` on sink failure. **P6** adds request header *names* to the trace.

## 6. Architectural risks

- **New modules** (ARCH §2): `tokli.domain`, `tokli.protocols.anthropic_messages`,
  `tokli.pipeline`, `tokli.compression`, `tokli.compressors.json_minify`, `tokli.upstream`,
  `tokli.auth`, `tokli.telemetry`, `tokli.observability`, `tokli.http`. The import contracts of
  ARCH §5 are added for each.
- **Seams (`CLAUDE.md §5`).** `ProtocolAdapter` and `CredentialPolicy` stay concrete (one adapter,
  one auth mode) until S5.
  - `Stage` is a real interface: S1 has 3 stages.
  - `Compressor` contract and registry: required by SPEC 009 in S1 (CC-001, CC-011, CC-012). The
    registry is an explicit list with one entry.
  - `TelemetrySink`: two sinks exist in S1 (SQLite, log line), so the interface is justified.
- **ADR 0002** (runtime dependencies): `starlette`, `uvicorn`, `httpx` (ARCH §9) and `tiktoken`.
  The tokenizer encoding is built from the verified local file with the published pattern and
  special tokens, and a test checks the counts against known reference values.
- **ADR 0003** (persistence format): SQLite schema v1 = `RequestRecord` + `CompressorStats`
  exactly as in TOKLI_TELEMETRY_AND_COST §2, plus `schema_version`, `history_rewritten` and
  `reference_stubs` (TC-012, TC-014). Writes happen off the request path, in a writer thread with a
  bounded queue.
- **Fail-open everywhere** except credentials (ARCH §6): parse, pipeline, render and telemetry
  errors never change what the client gets.

## 7. Product questions (for the human)

| # | Question | Recommendation |
|---|---|---|
| **P1** | **Minimum segment size** before a compressor is tried (`compression.min_segment_tokens`; `json_minify` has no own minimum). | **64 tokens.** It matches the duplicate threshold and skips small results, where savings are negligible and risk is not. POLICY, provisional; revised with E5b data. |
| **P2** | **Unresolved tool name.** A tool result whose tool call is not in the request (the name cannot be resolved): compress it or not? | **Do not compress** (skip with reason `verbatim_tool`, detail `unresolved`). Conservative: we cannot know whether it is a file read (H04). |
| **P3** | **S1 acceptance 5 (fingerprint)** vs the fingerprint command in S9. | In S1, prove the underlying property: the rendered output of the Anthropic compat and golden corpus is byte-identical across the 9 CI jobs (a cross-job hash comparison, like S0's doctor check). The `doctor --fingerprint` command stays in S9. |
| **P4** | **Streaming test (AC-PX-3).** Replace "within 20 ms" with a causal test. | The fake upstream sends chunk *n+1* only after the test client has received chunk *n*. If Tokli buffers, the test deadlocks and fails after 5 s. This is deterministic, with no timing threshold. |
| **P5** | **Live test E1b (Pro/Max OAuth) in S1**, after E1a. | Yes, as you asked. If it passes, the SPEC 006 matrix row becomes SUPPORTED with the evidence (AC-UP-7). If it fails, S1 still closes on E1a, and E1b becomes a documented finding. |
| **P6** | **Request header names in the trace** (names only, never values), e.g. `x-api-key`, `anthropic-beta`, `authorization`. E1 asks "which headers does Claude Code send?". | Yes. Names are metadata, and values are never recorded (UP-006, OB-007). New requirement OB-012. |
| **P7** | **`/openai` prefix in S1.** | Not routed: `404 tokli_unknown_route` with the hint listing `/anthropic`. It arrives in S5. |
| **P8** | **Scope readings** (deferrals in the scope table, A1–A7, X3). | Accept as proposed. |

## 8. Implementation decisions (decided by Claude, recorded here)

- HTTP: Starlette app served by uvicorn. Forwarding uses one shared `httpx.AsyncClient` created in
  bootstrap (no global state). Streams are relayed chunk by chunk as received.
- Request IDs: ULIDs generated in Tokli (timestamp + `os.urandom`), no dependency.
- Rendering: patched string values are replaced through the locators on a parsed copy, then the
  body is serialised once as UTF-8 JSON with `ensure_ascii=False` and compact separators (CM-011).
  With no patches, the original bytes are forwarded (CM-001).
- Logging: one JSON line per request to stderr through the stdlib `logging` module with a
  structured-field formatter. Log records never receive segment text.
- Telemetry: the SQLite file is `<data dir>/tokli.db`, in WAL mode, written by a single writer
  thread. Retention runs at startup and every 24 h.
- E9 benchmark: `benchmarks/overhead.py`, run once per OS on Python 3.13 in CI. The results are
  committed in `benchmarks/baseline/` as the first baseline, and a scheduled weekly workflow
  compares against it (warn at 1.25×, fail at 2×; TOKLI_TEST_STRATEGY §8).
- Compat corpus: synthetic Anthropic fixtures in `tests/compat/fixtures/anthropic_messages/`,
  shaped after the public API documentation. They contain canary strings and no real content.

## 9. Test plan (requirement → tests)

| Requirement(s) | Tests (spec names; new names are added to specs after Gate 1) |
|---|---|
| CM-001, CM-007, CM-008, CM-012, PX-010 | `test_passthrough_forwards_original_bytes`, `test_malformed_body_relayed_verbatim`, `test_content_encoded_body_relayed_verbatim`, `test_oversize_body_relayed_verbatim`, `test_internal_error_forwards_original` |
| CM-002…CM-006, CM-009, CM-011, AN-001…AN-004 | `test_render_changes_only_patched_values`, `test_structure_preserved_after_compression`, `test_unknown_block_types_roundtrip`, `test_anthropic_segment_mapping`, `test_anthropic_tool_name_resolution`, `test_anthropic_block_attributes_preserved`, `test_anthropic_cache_control_count_preserved`, `test_forbidden_parts_never_mutable`, `test_patched_body_utf8_and_length` |
| PX-001…PX-013, AN-008 | `test_default_bind_is_loopback`, `test_remote_bind_requires_flag`, `test_routing_table`, `test_unknown_prefix_returns_tokli_404`, `test_headers_forwarded_except_hop_by_hop`, `test_response_bytes_identical`, `test_stream_chunks_identical_and_unbuffered` (causal, P4), `test_upstream_errors_relayed_verbatim`, `test_upstream_unreachable_returns_tokli_502`, `test_client_disconnect_cancels_upstream`, `test_large_body_not_rejected`, `test_request_id_header`, `test_health_endpoint`, `test_anthropic_other_endpoints_verbatim` |
| UP-001, UP-002, UP-005, UP-006, UP-008, UP-009, UP-010 | `test_passthrough_forwards_client_credentials`, `test_inherited_provider_env_is_ignored_unless_configured`, `test_logs_never_contain_credentials`, `test_body_independent_of_auth_mode` (passthrough variant), `test_tls_verification_default_on`, `test_read_timeout_between_chunks`, `test_credential_kind_classification` |
| PL-003…PL-008, SPEC 007 reminders | `test_stage_exception_isolated`, `test_stage_timeout_isolated`, `test_analyzer_cannot_patch`, `test_new_transformer_needs_no_adapter_change`, `test_reminder_spans_protected`, `test_default_stage_list` |
| TM-001, TM-002, TM-005, TM-008 | `test_tokenizer_selected_by_model_map`, `test_token_counts_stable_fixture`, `test_token_counts_match_reference_values`, `test_every_api_token_field_has_method` |
| CC-001…CC-008, CC-010…CC-017, CC-020 | the SPEC 009 scenarios except chain and terminal (S4), plus `test_registry_default_enabled_requires_eval_record` with the provisional `json_minify` record |
| CP-JM-001…005 | the SPEC 010 `json_minify` tests (`prop_json_minify_decode_roundtrip` adds `hypothesis` as a dev dependency) |
| RT-002…RT-006 | `test_cheap_filters_before_applicable`, `test_prose_only_request_passthrough`, `test_routing_inputs_closed_and_no_ml`, `test_trace_shows_routing_counts` |
| TC-001…TC-003, TC-010…TC-012, TC-014 | `test_request_record_persisted_per_outcome`, `test_compressor_stats_only_for_considered`, `prop_marginal_savings_sum_to_total`, `test_retention_pruning`, `test_sink_failure_degrades_not_breaks`, `test_schema_migration_forward`, `test_request_record_pruning_fields` |
| OB-001…OB-008, OB-010, OB-011, OB-012 (P6) | `test_request_id_propagates_everywhere`, `test_trace_contains_all_spans`, `test_trace_buffer_bounded`, `test_reason_codes_closed_set`, `test_upstream_correlation_ids_recorded`, `test_upstream_error_logging_respects_content_rule`, `test_default_logging_contains_no_prompt_text`, `test_request_summary_log_line`, `test_health_degraded_conditions`, `test_trace_records_header_names_only` |
| API-001, API-002, API-004 | `test_api_returns_no_content_or_credentials`, `test_api_contract_schemas` (requests/{id}, health) |
| PT-008, fresh-machine scenarios, MD rows | `test_port_in_use_fails_clearly`, `test_alternative_port`, `test_no_outbound_connections_except_upstream`, `test_hostile_environment_ignored` (serve variant), `test_json_minify_crlf_roundtrip` |
| Acceptance 1–2, 5 (P3) | compat corpus suite; CI job "rendered corpus identical in all 9 jobs" |
| Acceptance 3 (E1a), E1b (P5) | live runbook `slices/S1/LIVE_TEST.md`, run by the product owner in separate sessions |
| Acceptance 6 | E9 benchmark + E1a session DB → percentile script → completion report |

## Gate 1 record

Answers (2026-09-30), product owner: "accetto le tue proposte" (P1–P8 as recommended), plus the earlier
decisions C2, C3 and the live-test plan.

Spec delta: status lines of specs 001–003, 006–015, 017, 018 ("Approved for S1"); SPEC 009 CC-008
clarified, new CC-022 (min segment tokens 64) and CC-023 (unresolved tool name = verbatim);
SPEC 017 N-level keys, hash sections, "Keys added in S1"; SPEC 002 causal AC-PX-3 and the `/openai`
note; SPEC 014 OB-012 (header names only); roadmap S1 acceptance 3 (E1b) and 5 (cross-job
corpus identity); traceability rows.

Slice approval: **approved 2026-09-30**, product owner: "approvo S1".
