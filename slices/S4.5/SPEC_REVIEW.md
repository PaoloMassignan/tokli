# S4.5 — Spec review

Slice: **S4.5 — Hardening of the accepted code (S0–S4)** (`TOKLI_ROADMAP.md`, added after P1).
Status: **Approved 2026-10-03 (Human Gate 1).**

## Scope

**Origin.** A code review of `main` at `5f1c439` (S4 accepted), run on 2026-10-03. State at review
time: `ruff check`, `mypy --strict` (68 files) and `lint-imports` (5 contracts kept) green;
`pytest`: 566 passed, 10 skipped (packaging and provisioned-tokenizer tests, which need
`RUN_PACKAGING_TESTS` / `TEST_TOKLI_PROVISIONED_DATA_DIR`).

**Roadmap entry.** Added to `TOKLI_ROADMAP.md` between S4 and S5 (P1 = yes). It includes the
transformation off the event loop (P2 = a) and excludes the tokenisation memo (R2 withdrawn).

**Requirements touched.** One new requirement, PX-015 (approved for S4.5). The others are already approved and do not change:

| Spec | Requirement | Item |
|---|---|---|
| 015 application API | API-007 (atomic apply, file written atomically) | D1 |
| 013 telemetry | TC-001, TC-012 (schema, forward migration, no silent drop) | D2 |
| 002 transparent proxy | **PX-015 (new, Draft for S4.5)**, AC-PX-8 | D3 |
| 009 compression core | CC-004…CC-008 (acceptance gate, invariants, timeout), CC-024 (result cache) | R1, D3 |
| 002 transparent proxy | PX-010 (fail to pass-through), AC-PX-3 (unbuffered streaming) | D3, R4 |
| 015 application API | API-008 (routes reach storage only through `tokli.app`) | R4 |

**Out of scope.** Everything in S5 and later. Any change to a compressor's output, to the
persisted record's meaning, to the API shape or to the dashboard.

## 1. Ambiguities

| Id | Requirement | Question | Proposed reading |
|---|---|---|---|
| A1 | API-007 | "Apply them atomically" — does atomicity cover two PATCHes that arrive together, or only one PATCH against in-flight requests? | It covers both: PATCHes are serialised, so each one reads the overrides written by the previous one. The second PATCH never loses the first one's keys. |
| A2 | TC-012 | "Never silently drop columns": is a column created with a wrong SQL type a violation? | Yes in spirit: the type of every column follows the type of its record field, and a field whose type has no SQL mapping fails a test instead of falling back to `TEXT`. |

## 2. Contradictions

None found between specs. The items below are differences between the code and the approved
specs or between two copies of the same rule in the code.

## 3. Defects and refactorings found by the review

### Defects (regression test first, then the fix — CLAUDE.md §2)

- **D1. Concurrent configuration changes can lose an update** (`src/tokli/app/config_service.py`,
  `apply_patch`). The use case runs in the thread pool (`anyio.to_thread.run_sync`). It reads
  `ui-overrides.yaml`, merges the change and writes the file without a lock covering the whole
  read → write → reload sequence; `Runtime`'s lock covers only the swap. Two concurrent PATCHes
  can therefore lose one change. Both also write the same temporary file
  (`ui-overrides.yaml.tmp`), so on Windows two crossing `os.replace` calls can fail with
  `PermissionError` and answer 500. Fix: one lock around the whole of `apply_patch` (and a
  per-call temporary name). Regression test: N concurrent PATCHes of different keys → every key
  present in the final view and in the file.
- **D2. Telemetry column types are derived from column names** (`src/tokli/telemetry/store.py`,
  `_sql_type`). Prefixes and hand-written lists decide `INTEGER`/`REAL`/`TEXT`. A new integer
  field whose name matches no rule is silently created as `TEXT`, and the forward migration
  (TC-012, ADR 0005) never retypes a column, so the error would persist in users' databases.
  Fix: derive the type from the dataclass field annotation; an unmapped annotation raises.
  Regression test: every field of `RequestRecord` and `CompressorStatsRecord` maps to the SQL type
  of its annotation; an unmapped annotation is refused. The existing column types do not change
  (verified by the test against the current mapping), so no schema version bump is needed.

### Behaviour-relevant design point (product question P2)

- **D3. The request transformation runs on the event loop** (`src/tokli/http/proxy.py`,
  `_transform`). `parse`, `pipeline.run` and `render` run synchronously inside the async handler.
  On a body near `limits.max_transform_bytes`, with the repeated tokenisations, the loop stops,
  and so do the SSE relays of every other request in flight (AC-PX-3 holds per request, not
  across requests). CC-008 already accepts that calls are not preempted; the issue is the shared
  loop, not preemption. Moving the transformation to a worker thread needs `ResultCache`
  (CC-024) to become thread-safe, changes the proxy's concurrency characteristics and therefore
  needs an ADR (CLAUDE.md §6). **Decided P2 = (a):** new requirement PX-015 and AC-PX-8 in SPEC
  002; ADR 0011 describes the design (accepted at Gate 1).

### Refactorings (behaviour unchanged, tests green before and after)

- **R1. The acceptance gate exists twice** (`src/tokli/compression/engine.py`). `_gate()` is used
  by the request scope; `_run_segment` repeats the same checks inline (no gain, protected spans,
  minimum gain). The segment scope should call `_gate()`, so that a future change to the rule
  cannot apply to one scope only.
- ~~**R2. The same text is tokenised several times per request.**~~ **Withdrawn (2026-10-03).**
  The review claim was wrong: `TokenCounter.count` already keeps an LRU cache keyed by text
  (`src/tokli/tokens/counter.py`), so repeated counts of the same text are cache hits, not new
  tokenisations. A second memo would add nothing measurable. P3 was answered "yes" before this
  was found; the item is dropped and the human is told so.
- **R3. `Any` where protocols exist.** `proxy._State.engine`, `.counter`, `.services` and the
  engine's `registry`, `compressor`, `_pre_filter(compressor)` are typed `Any`, and
  `getattr(compressor, "decode", None)` hides an optional interface. Typing them with the
  protocols of `tokli.compression.contract` lets `mypy --strict` check the module boundary that
  matters most. An optional `decode`/`equivalent` pair becomes an explicit protocol.
- **R4. `proxy.py` mixes three concerns** (597 lines; `_complete` about 140). The HTTP flow stays
  in `tokli.http.proxy`; building the `RequestRecord`, the stats rows and the structured log line
  moves to a use case in `tokli.app` next to `measurement`. Import contracts unchanged.
- **R5. Small consistency fixes.**
  - `http/app.py` `compressors`: reads `runtime.current()` twice, so it can mix two snapshots
    during a PATCH. Read it once.
  - `http/app.py` `request_detail`: uses the `services` captured at startup instead of
    `runtime.current()`. Correct today only because `rebuild` keeps `traces` and `store`.
  - `proxy.py` `_record_calibration`: the outlier range `[0.5, 2.0]` is written by hand in the
    log line; take it from the constant used by `measurement`.
  - `ProxyHandler.__init__` reads `limits` and `observability.response_header` once. Correct while
    those keys are not UI-editable (CF-009); state it in a comment.

## 4. Portability concerns

- D1 is mostly a Windows hazard (`os.replace` onto a file another thread is replacing). The
  regression test must run on the whole CI matrix, not only on Windows.
- D3 adds work on worker threads; tokenizers (`tiktoken`) are already used from a
  worker thread by the whole-request estimate, so no new thread-safety assumption about them.

## 5. Observability requirements for this slice

- No new events or reason codes. D1 keeps the `config_change` event, one per accepted PATCH.
- With D3, the trace spans `parse`, `pipeline`, `render` keep their names and meaning;
  `ms_tokli_overhead` keeps its definition. The checklist of `TOKLI_OBSERVABILITY.md §8` is
  re-run in VERIFY.

## 6. Architectural risks

- R4 moves code between `tokli.http` and `tokli.app`; the layers contract already allows
  `http → app`. No new dependency direction, no new seam.
- R3 introduces no new abstraction: the protocols already exist in `tokli.compression.contract`.
  The optional decode interface (`decode`, `equivalent`) becomes a named protocol only because two
  concrete behaviours already exist (compressors with and without it) — CLAUDE.md §5.
- D3 changes runtime concurrency → ADR 0011 (`proposed`, reviewed at this gate).

## 7. Product questions (answered 2026-10-03)

1. **P1 — Add S4.5 to the roadmap?** Answer: **yes**. Entry added to `TOKLI_ROADMAP.md`.
2. **P2 — D3: move the request transformation off the event loop in this slice?** Answer:
   **(a) yes**, with an ADR and a thread-safe result cache. PX-015, AC-PX-8, ADR 0011.
3. **P3 — R2 (tokenisation memo): include it?** Answer: **yes** — but R2 was then withdrawn
   because the token counter already caches per text (section 3). Nothing to implement.

## 8. Implementation decisions (decided by Claude, recorded)

- D1: a `threading.Lock` owned by the config use case (not by `Runtime`), held from reading the
  overrides to the swap; temporary file named per call (`<file>.<pid>.<thread id>.tmp`) and
  removed on failure.
- D2: annotation → SQL type map `int → INTEGER`, `float → REAL`, `bool → INTEGER`,
  `str → TEXT`, `tuple[str, ...]` (JSON column) → `TEXT`, each also as `X | None`.
- R1–R5 are done one per commit-sized step, tests green after each.
- D3: as in ADR 0011 (`anyio.to_thread.run_sync` for the whole transformation, a lock in
  `ResultCache`).
- Order: D1, D2 (defects first), then R1, R3, R4, R5, then D3.

## 9. Test plan

| Item / requirement | Test (to be written; RED before GREEN for D1, D2) |
|---|---|
| D1 / API-007, A1 | `tests/integration/test_config_api.py::test_concurrent_patches_keep_every_change` |
| D1 / API-007 | `tests/unit/test_config_ui_layer.py::test_failed_write_leaves_no_temporary_file` |
| D2 / TC-012, A2 | `tests/unit/test_telemetry_store.py::test_column_type_follows_field_annotation`, `::test_unmapped_annotation_is_refused`, `::test_existing_column_types_unchanged` |
| D3 / PX-015, AC-PX-8 | `tests/integration/test_proxy.py::test_slow_transform_does_not_stall_other_streams` |
| D3 / CC-024 | `tests/unit/test_engine.py::test_result_cache_is_safe_under_concurrent_requests` |
| R1, R3, R4, R5 | existing unit, integration, compat and golden tests unchanged and green |
| D3 performance | E9 overhead re-measured against `benchmarks/baseline/` (reported, not gated) |

Gate 1 record: **approved 2026-10-03**, the human's words: "Approvo s4.5". Spec delta: SPEC 002
PX-015 and AC-PX-8 (status line "Approved for S4.5"), roadmap entry S4.5, traceability row
PX-015, ADR 0011 accepted.
