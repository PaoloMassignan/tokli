# S4.5 — Completion report

Slice: **S4.5 — Hardening of the accepted code**. Branch `s4.5-hardening`.
Gate 1: approved 2026-10-03 ("Approvo s4.5"), see `SPEC_REVIEW.md`. No spec change requests.

## Requirements implemented

| Item | Requirement | Change |
|---|---|---|
| D1 | API-007 | One lock over the whole PATCH (read overrides → write → reload → swap); a temporary file per call, removed when the write fails |
| D2 | TC-001, TC-012 | Column types come from the record's field annotations; an annotation with no SQL type is refused at import. Existing column types unchanged, so no schema bump |
| D3 | **PX-015** (new), CC-024 | Parse, pipeline and render run on a worker thread (`anyio.to_thread.run_sync`); `ResultCache` holds a lock; ADR 0011 accepted |
| D4 | TC-011 | Found by CI during this slice (see below): `close()` no longer closes the SQLite connection while the writer thread may still use it; the writer closes it when it reaches the stop marker |
| R1 | CC-004…CC-007 | The segment scope uses the same `_gate()` as the request scope |
| R3 | — | Protocol types instead of `Any` (see below) |
| R4 | API-008 | The record, the per-compressor rows, the trace view and the log line are built in `tokli.app.request_record`; `proxy.py` keeps the HTTP flow |
| R5 | CF-005 | One snapshot per API read (`compressors`, `request_detail`); the outlier range comes from `K_MIN`/`K_MAX`; a comment on the settings the proxy reads once |

R3 in detail:
- `Compressor`, `LosslessCompressor` and `RequestCompressor` are runtime-checkable;
- `AnyCompressor` types the registry and the engine;
- the cache key has a type;
- `_State` in the proxy names `Services`, the compression report and `TokenCounter`, through `tokli.app`;
- `Services.selector` is the concrete `TokenizerSelector`;
- the optional `decode`/`equivalent` pair is checked through `LosslessCompressor` instead of `getattr`.

Typing the engine made `mypy` find three places that were only correct by construction: a declined proposal's `None` text, the cache key when the cache is off, and the doctor's registry type. Each now states the invariant.

**D4, found during VERIFY.** CI run 37150062223, Windows / Python 3.12, crashed with a native
access violation in `tests/unit/test_metrics.py`:
- the writer thread was inside an INSERT (`store.py` `_write`) while the test thread was in
  `close()`;
- `close()` waited at most 10 s for the writer, then closed the connection regardless; the log
  shows the test starting at 20:07:36 and the crash at 20:07:48;
- the defect exists since S1. It only shows on a runner slow enough that 10 s is not enough.

Fix, regression test first:
- `test_close_never_closes_the_connection_under_a_busy_writer` failed before the fix: the record
  was lost and the write failed on the closed connection;
- the wait became `_CLOSE_TIMEOUT_S`, a plain refactoring, so that the test can shorten it.

**Deferred:** nothing. R2 was withdrawn at Gate 1, because the token counter already caches per text.

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **575 passed, 10 skipped**, against S4's 566 passed and 10 skipped. The 9 new tests are listed in the table below. `ruff check`, `ruff format --check`, `mypy --strict` (69 files) and `lint-imports` (5 contracts kept) are clean.
- **CI:** run 37149292060 (commit c2c661a): all 9 jobs green, and the doctor snapshot and rendered corpus are identical across jobs. Ubuntu/3.12: 583 passed, 1 skipped; browser tests 13 passed. Run 37150062223 (commit 2be457c) crashed on Windows / Python 3.12; that crash is D4. **Final run 37150828625 (commit b5ff0bc): all 9 jobs green, cross-job identity check green.**
- **RED first.** Each test failed for the behaviour before the fix:

  | Test | Failure before the fix |
  |---|---|
  | `test_concurrent_patches_keep_every_change` | `[500, 500, 200]`: two PATCHes crossed on the shared temporary file (`PermissionError` on Windows), and the third lost the others' keys |
  | `test_failed_write_leaves_no_temporary_file` | `ui-overrides.yaml.tmp` left behind |
  | `test_column_type_follows_field_annotation` | an integer field created as `TEXT` |
  | `test_unmapped_annotation_is_refused` | `DID NOT RAISE` |
  | `test_slow_transform_does_not_stall_other_streams` (AC-PX-8) | B's stage waited 5 s, because A's next chunk was not relayed |
  | `test_result_cache_is_safe_under_concurrent_requests` | `KeyError` from `move_to_end` after another thread's eviction; 3 of 3 runs |
  | `test_close_never_closes_the_connection_under_a_busy_writer` (D4) | `failures == 1`: the write failed on the connection `close()` had closed |
  | `test_existing_column_types_unchanged` (×2) | passed before the fix, by design: it pins today's types so that D2 changes none |

- **Changed tests:**
  - `_write_v1_database` in `test_telemetry_store.py` built a v1 table with the private `_sql_type`; it now reads the new type maps. No assertion changed.
  - No test was weakened, skipped or deleted.
- **Traceability:** rows for PX-015, CC-024, TC-011, TC-012 and API-007 updated.

## Architecture changes

- **New module:** `tokli.app.request_record` (`Observed`, `record_request`, `usage_categories`, `now_iso`).
- **Re-exports for the HTTP layer:**
  - `tokli.app.measurement` exports `TokenCounter` and `OUTLIER_RANGE`;
  - `tokli.app.api` exports `CompressionReport`;
  - `tokli.http` still never imports `tokli.compression` or `tokli.tokens` directly.
- **Engine:** compressors are split by scope once, in the constructor (`_request_scope`, `_segment_scope`, `_decoders`). The loops no longer filter by scope for every segment.
- **ADR 0011 accepted.** No new dependency, no persisted-format change, no config key.

## Measured performance (E9, reported, not gated)

**On CI, this run against S4's run:** the p95 of `200k_warm` was 42 ms on Linux (S4: 15 ms), 38 ms on Windows (14 ms) and 17 ms on macOS (14 ms). Against the S1 baseline every bucket is within the limits.

These CI numbers do not measure the change; they show the runners' variance. The same code (S4, then `main` right after the merge) gave:

| Runner | S4 run, 200k_warm p95 | `main` run, same code, 200k_warm p95 |
|---|---|---|
| Windows | 14.1 ms | **66.2 ms** |
| Linux | 15.1 ms | 10.1 ms |

So a single CI run cannot separate a 1.3× change from noise.

**Paired local measurement** (same Windows machine, CPython 3.11, run one after the other, 15 iterations, p95; `python -m benchmarks.overhead`):

| Bucket | S4 (5f1c439) | S4.5 final | Ratio |
|---|---|---|---|
| 50k cold | 28.9 ms | 33.0 ms | 1.14× |
| 50k warm | 3.8 ms | 3.8 ms | 0.99× |
| 200k cold | 114.9 ms | 124.6 ms | 1.08× |
| 200k warm | 26.1 ms | 27.2 ms | 1.04× |
| 200k warm, no cache | 51.4 ms | 53.3 ms | 1.04× |

- The benchmark times parse, pipeline and render in-process, so it does not include D3's thread hand-off.
- The hand-off costs one `to_thread` call per transformable request, well under a millisecond. It is included in `ms_tokli_overhead`.
- Splitting the compressors by scope gave no measurable gain (200k warm: 27.14 ms before, 27.16 ms after).

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] No new events or reason codes. The span names `parse`, `pipeline` and `render` and their meaning are unchanged.
- [x] `ms_tokli_overhead` keeps its definition and now includes the hand-off.
- [x] The `config_change` log line is still written once per accepted PATCH; the concurrent test produces three.
- [x] The request log line moved to `tokli.app.request_record` with the same fields. The integration tests that parse it pass unchanged: `test_request_summary_log_line`, `test_stream_metadata_in_summary_log_line`, `test_logs_never_contain_credentials`, `test_default_logging_contains_no_prompt_text` and `test_upstream_error_logging_respects_content_rule`.

## Known limitations

- **CI noise in E9.** E9 on shared CI runners varies up to about 4.7× between runs of the same code. The regression limits (1.25× warn, 2× fail) are therefore only meaningful against a paired local run, or over several CI runs.
- **Transformations are not interrupted.** A transformation on a worker thread cannot be interrupted (CC-008, unchanged). anyio's default limit of 40 threads bounds how many run at once.

## Unresolved questions

1. **Merge:** squash-merge into `main` after acceptance. Recommendation: yes.
2. **E9 noise.** Recommendation: when a slice touches the hot path, record a paired local run as done here, and keep the CI numbers as a sanity check. The comparison policy itself is not changed in this slice; changing it would be a test-strategy change for the human to approve.

Gate 2 record: **accepted 2026-10-03**, the human's words: "Accetto s4.5". The unresolved
questions follow the recommendations: squash-merge into `main`; E9 comparison policy unchanged
(paired local runs recorded when a slice touches the hot path).
