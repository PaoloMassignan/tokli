# S1 — Completion report

Slice: **S1 — Anthropic Messages, passthrough auth, one lossless compressor** · Branch
`s1-anthropic-proxy` (squash-merged into `main`) · Status: **accepted 2026-10-02 (Human Gate 2)**

## Requirements implemented

Everything marked "Approved for S1" in the specs (`slices/S1/SPEC_REVIEW.md`, Gate 1 record):

| Spec | Requirements |
|---|---|
| 001 | CM-001…CM-012 (Anthropic) |
| 002 | PX-001…PX-013 (`/anthropic` prefix) |
| 003 | AN-001…AN-004, AN-008 |
| 006 | UP-001, UP-002, UP-005, UP-006, UP-008, UP-009, UP-010; live tests E1a and E1b |
| 007 | PL-003…PL-008 (fixed stage list, C2), `analyze.reminders` |
| 008 | TM-001, TM-002, TM-005, TM-008 |
| 009 | CC-001…CC-008, CC-010…CC-017, CC-020, CC-022, CC-023 |
| 010 | CP-JM-001…CP-JM-005 |
| 011 | RT-001 (S1 features), RT-002…RT-006 |
| 012 | QE-016 provisional record for `json_minify` |
| 013 | TC-001, TC-002, TC-003, TC-010, TC-011, TC-012, TC-014 |
| 014 | OB-001…OB-008, OB-010, OB-011, OB-012 |
| 015 | `GET /tokli/api/requests/{id}`, `GET /tokli/health`, API-001, API-002, API-004 |
| 017 | S1 keys, N-level key paths, named flags (`--port`, `--allow-remote`, `--log-format`) |
| 018 | PT-008 (port in use), `serve` fresh-machine scenarios, MD-09/10/12/22/23/24/25 |

Deferred as approved: usage parsing (S2), PX-014 (S2), CM-013 and chains (S4), OB-009, inject mode
(S5), metrics API (S3).

## S1 acceptance checks

| # | Check | Result |
|---|---|---|
| 1 | Compression disabled → byte-identical bodies; responses and streams identical and unbuffered | **Met.** `test_passthrough_forwards_original_bytes` (10 fixtures, unit and end to end); `test_response_bytes_identical`; the causal `test_stream_chunks_identical_and_unbuffered` |
| 2 | With `json_minify` on, only pretty JSON results of non-verbatim tools change, all round-trip, structure identical | **Met.** `test_only_json_tool_results_of_non_verbatim_tools_change` (per fixture), `test_expected_changes_in_tool_use_fixture`, `prop_json_minify_decode_roundtrip` |
| 3 | Claude Code session E1a (API key) completes 3 scripted prompts; per-compressor figures recorded | **Met** on 2026-10-02 (live results below). E1b (Pro/Max) also **met**. |
| 4 | No credential or canary content in logs or the DB | **Met.** `test_logs_never_contain_credentials`, `test_default_logging_contains_no_prompt_text` (logs, API and database bytes) |
| 5 | Rendered corpus identical in all 9 CI jobs (decision P3) | **Met.** CI job "Doctor snapshot and rendered corpus identical in all 9 jobs" (run 36694873665 and later) |
| 6 | Overhead distribution reported against the Vision target | **Reported** below (not gated) |

## Tests and evidence

- **Suite:** 342 tests (unit, property, contract, compat, streaming, integration, regression,
  packaging). Locally (Windows, CPython 3.11): 341 passed, 1 skipped (packaging, which runs in CI).
- **CI** on {Windows, Ubuntu, macOS} × {3.11, 3.12, 3.13}: run 36694873665 was green, with 340 tests
  per job, 0 skipped, `ruff`, `mypy --strict` and 4 import contracts. Later runs: see "Process
  deviations".
- **Token counts** reproduce tiktoken's own `get_encoding` exactly for both tokenizers (11
  reference strings plus 200 generated strings).
- **RED before GREEN, per block:**
  - Block A (engine, compressor, pipeline, counter): 65 failures, all `NotImplementedError`.
  - Block B (adapter): 64 failures.
  - Proxy: 89 failures plus 1 missing module, which was then stubbed.
  - `serve`: 3 failures (command absent).
  - Ctrl+C regression: failed with the reported `KeyboardInterrupt`.

### Live tests (product owner, 2026-10-02; metadata read with consent)

31 requests went through Tokli in two sessions (`%LOCALAPPDATA%\Tokli\tokli.db`):

| Session | Requests | Status | Notes |
|---|---|---|---|
| E1a, API key | 11 | 6 × 200, 5 × 400 | The 400s are the provider rejecting an organisation-level key ("not scoped to a workspace"), relayed verbatim. With a workspace key, all prompts passed. |
| E1b, Pro/Max | 16 | 14 × 200, 2 × 429 | `credential_kind = oauth`. The two 429s are provider rate limits on non-streaming background requests, relayed verbatim. No error was visible to the user. |
| Verbatim route | 4 | 4 × 200 | Claude Code calls `GET /anthropic/api/hello`, relayed unchanged |

- **No Tokli error codes.** Models seen: `claude-opus-5-5` and `claude-sonnet-5`.
- **Q2 resolved:** Claude Code keeps the `/anthropic` path prefix on every request.
- **Compression: 0 tokens saved, as expected.**
  - `json_minify` considered 104 segments: 66 `too_small`, 35 `not_applicable(not_json)`,
    3 `verbatim_tool`.
  - The prompts produced no pretty JSON from non-verbatim tools. This is risk R3 in practice: the
    real saving has to come from duplicate tool results (S4) and from evidence gathered by E5b.

## Measured performance (TOKLI_TEST_STRATEGY §8; reported, not gated)

| Source | p50 | p95 | max |
|---|---|---|---|
| Live E1a (Tokli overhead per request) | 5.8 ms | 15.3 ms | 15.3 ms |
| Live E1b | 7.0 ms | 9.9 ms | 14.9 ms |

Against these, upstream time to first byte was 1.1–1.6 s (median). Tokli added well under 1 %.

E9 benchmark (CI, Python 3.13, p95; committed as baselines in `benchmarks/baseline/`):

| Request size | Linux | Windows | macOS |
|---|---|---|---|
| 10k, warm / cold | 3 / 7 ms | 3 / 6 ms | 8 / 21 ms |
| 50k, warm / cold | 15 / 27 ms | 14 / 24 ms | 35 / 68 ms |
| 200k, warm / cold | 53 / 114 ms | 55 / 102 ms | 110 / 205 ms |

The Vision target (p95 ≤ 25 ms up to 200k tokens, default pipeline) is met by live traffic and by
requests up to about 50k tokens. It is **missed for large requests**. The cost is dominated by
`json_minify` re-checking and re-minifying JSON results that repeat in every turn. Per §8 this
triggers a review, not a rejection (see question 2).

## Architecture changes

- **New packages:** `domain`, `protocols.anthropic_messages`, `pipeline`, `compression`,
  `compressors.json_minify`, `tokens.counter`, `upstream`, `auth`, `telemetry`, `observability`,
  `http`, plus `app.bootstrap` (composition root), `app.api` and `app.serve`.
- **ADR 0002:** starlette, uvicorn, httpx, certifi and tiktoken; encodings are built from verified
  local files.
- **ADR 0003:** SQLite telemetry schema v1. It adds `ms_total`, `history_rewritten` and
  `reference_stubs`.
- **ADR 0004 (needs your review):** enforced dependency rules. `tokli.app` is the composition root
  and imports what it builds. Hop-by-hop header rules live in `tokli.domain.headers`. Every
  forbidden edge of ARCH §5 still holds.

## Observability evidence (`TOKLI_OBSERVABILITY.md §8`)

- **Spans:** route, parse, analyze.reminders, analyze.features, transform.compression, render,
  auth, upstream, usage (`test_trace_contains_all_spans`).
- **Reason codes:** closed set (`test_reason_codes_closed_set` over all fixtures and error paths).
- **Logs:** one JSON summary line per request, with redaction as defence in depth.
- **Persistence and API:** SQLite records; `/tokli/api/requests/{id}`; `/tokli/health`
  (degraded on sink failure or an unavailable compressor).
- **Leak scans:** credential and content canary scans over logs, API and database bytes.

## Known limitations

- **No log file:** logs go to the console only. The optional rotating log file of
  TOKLI_OBSERVABILITY §6 was not built. After a crash only the database remains.
- **Header names are not persisted:** they live only in the in-memory trace, so they are lost when
  Tokli stops. E1 could not record the list of headers Claude Code sends.
- **Performance** above target for large requests (see above).
- **The record appears just after the response:** Tokli writes the request record right after
  relaying the last byte, so for a few milliseconds `/tokli/api/requests/{id}` can answer 404.
  The tests wait for it.
- **Platform label:** Windows 11 is shown as "Windows 10" on Python 3.11 (a CPython limitation).
- **CI deprecation warning:** GitHub Actions warns that the action versions used target Node.js 20.

## Process deviations (reported honestly)

1. **Tests written after the code.** Some tests for S1 requirements were written after the
   implementation, while checking traceability:
   - `test_oversize_body_relayed_verbatim`, `test_patches_visible_to_later_stages`,
     `test_routing_inputs_closed_and_no_ml`, `test_features_linear_time`,
     `test_request_record_pruning_fields`;
   - `test_new_transformer_through_adapter_end_to_end` and the store tests of TC-014;
   - the RED run for the S1 configuration keys was checked retroactively, against the previous
     loader: 9 behavioural failures.
2. **Test defects found and fixed:**
   - a race (reading the database before the record existed): failed in 7 of 9 CI jobs on the
     first run;
   - two timing-based tests that were flaky. `test_features_linear_time` measured the wrong
     variable (number of segments instead of segment length) and was redesigned;
   - one wrong assertion about `user-agent`, made stricter.
3. **Personal path in a public file:** the runbook contained the developer's home path and was
   pushed on this branch. It is fixed, and a new contract test scans every tracked file. The path
   remains in the branch history (see question 5).
4. **Bug found in the live test:** `Ctrl+C` printed a `KeyboardInterrupt` traceback. Fixed with
   regression test `test_serve_ctrl_c_stops_cleanly`.
5. **SCR-001 (approved):** the linear-time checks failed intermittently on one CI job because the
   approved sizes (0.5 MB and 5 MB) straddle the CPU cache. They now use 5 MB and 50 MB. The
   change also exposed a slow regex in `json_minify` (8–10 MB/s), replaced by an equivalent form
   that is up to 5× faster.
6. **Tooling:** shell-written files had their backslashes changed in a few places. All such files
   were checked; one test regex was affected and fixed before it could give false confidence.

## Unresolved questions (for the product owner)

1. **ADR 0004:** accept the enforced dependency rules, and update ARCH §5 to point to them?
2. **Performance for large requests.** Options:
   - (a) accept for now and revisit with E5b data;
   - (b) a small deterministic cache of compressor results per text, which makes repeated history
     almost free (allowed by CC-006);
   - (c) both. Recommendation: (b) in S2.
3. **Persist header names** (names only) in the request record, so E1-style questions survive a
   restart? Recommendation: yes, in S2.
4. **Optional log file** in the data dir (rotating, 10 MB × 5)? Recommendation: yes, small, in S2.
5. **Merging into `main`:** squash S1 into one commit on `main` and delete the remote branch, so
   the personal path does not stay in any public branch? Recommendation: yes.

## Gate 2 record

Accepted on 2026-10-02 by the product owner: "accetto S1" (after the final CI run 37039638547:
9/9 jobs green, 342 tests each). Answers to the unresolved questions, given in advance ("accetterò
tutte le tue proposte"):

| Question | Decision |
|---|---|
| 1. ADR 0004 | Accepted; ARCH §5 now points to it |
| 2. Performance on large requests | (b) a deterministic cache of compressor results, in S2 |
| 3. Persist header names | Yes, names only, in S2 |
| 4. Optional log file | Yes, rotating, in the data dir, in S2 |
| 5. Merge | Squash into one commit on `main`; delete the remote branch `s1-anthropic-proxy` |
