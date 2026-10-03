# S3 — Completion report

Slice: **S3 — Metrics API + minimal dashboard**. Branch `s3-metrics-dashboard`.
Gate 1: approved 2026-10-03 ("Approvo s3. Test live alla fine"), see `SPEC_REVIEW.md`.

## Requirements implemented

| Spec | Requirements |
|---|---|
| 013 telemetry | TC-013 (overhead per size bucket, policy and `config_hash`; nearest-rank; `unknown` bucket; target as a reference), TC-015 (totals and honest labels), TC-016 (per-compressor aggregates and the "latency without benefit" flag) |
| 015 API | `GET /tokli/api/requests`, `metrics/summary`, `metrics/timeseries`, `metrics/compressors`, read-only `GET /tokli/api/compressors`; API-001…API-004, API-008…API-012 |
| 016 dashboard | Overview, Compressors (read-only), Recent requests with trace detail; UI-001, UI-002, UI-003 (kind, equivalence, assumptions), UI-006, UI-008, UI-009, UI-011 |

**Deferred, as approved:**
- S4: settings, toggles and locks (UI-004, UI-005, UI-010, AC-UI-3, API-005…API-007); the
  evaluation status in UI-003;
- S6: money figures;
- S9: diagnostics;
- the debug banner (UI-007) waits for OB-009.

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **448 passed, 9 skipped**. The skipped tests
  need the browser, the real tokenizer files or packaging, and run in CI. The browser tests also
  ran locally with Playwright installed in the session's temporary folder: 7 passed. `ruff`,
  `mypy --strict` and `lint-imports` are clean (5 contracts kept, one of them new).
- **CI run 37105132529** (commit d8c73ef): all 9 jobs green, cross-job identity check green. The
  browser job (Ubuntu, Python 3.12) ran `tests/ui`: 7 passed, none skipped. CI run 37108638710
  (commit 5316e70, plain-language labels): all 9 jobs green, browser job included.
- **RED first** for the API, metrics, engine and store tests: 42 failed on missing behaviour.
  Two API tests had passed vacuously against the missing routes (404 bodies without figures);
  they were tightened to require 200 before GREEN.
- **The browser tests were not run before the dashboard existed.** Playwright was not installed
  at that point. They were written first and first run against the finished page.
- **Contract schemas:** `tests/contract/api/*.schema.json` (JSON Schema 2020-12), one per
  endpoint, validated after real proxied traffic.
- **Traceability:** rows for TC-013, TC-015, TC-016, API-001…API-004 and API-008…API-012, and
  UI-002, UI-003, UI-006, UI-008, UI-009 and UI-011.

## Live check (roadmap exit), 2026-10-03

The product owner used the dashboard with real traffic and found it correct ("mi pare tutto
bene"). One finding: the overhead chart's p50/p95 labels were unclear. Asked for simpler reading
without technical terms, Claude reworded the presentation (commit 5316e70). The data and the
method labels are unchanged:

- the chart reads "typical" (half of the requests take less) and "slowest" (only 1 in 20 takes
  longer), with named size groups ("small (< 10k tokens)" and so on) and request counts;
- a legend under the totals explains exact / calibrated / estimate in plain words;
- the compressor columns have plain titles, each with an explanation on hover;
- common reason codes show plain words with the code in brackets (e.g. "prices not set up yet
  (no_price_book)").

## Architecture changes

- **New modules:**
  - `tokli.app.metrics` (`MetricsQuery`, `parse_filters`);
  - `tokli.telemetry.queries` (read-only SQL, one connection per call);
  - `tokli/ui/` (static `index.html`, `style.css`, `app.js`).
- **Changed modules:**
  - `tokli.http.app`: new routes, a host-check middleware, static assets with explicit content
    types;
  - `tokli.app.api`: `compressors_view`;
  - `tokli.compression.engine`: counts `tokens_in_accepted`;
  - `tokli.telemetry.store`: schema v3.
- **New import contract:** `tokli.http.app` may not import `tokli.telemetry` (API-008).
- **ADR 0006:**
  - `tzdata` (runtime);
  - `jsonschema` (development);
  - Playwright as the `ui-test` extra, in one CI job;
  - the host-check rules.
- **ADR 0007, schema v3:** `compressor_stats.tokens_in_accepted`. TC-016's "average saving % per
  accepted invocation" cannot be computed from the v2 columns. Rows from before v3 are ignored
  for that figure, with a reason.
- **Reading of API-009 for wildcard binds:** with `--allow-remote` on `0.0.0.0` or `::`, the
  `Host` cannot be compared with an address, so only the port is checked (ADR 0006).

## Measured performance (reported, not gated)

**Metrics queries** on a synthetic database of 100,000 requests over 30 days
(`benchmarks/metrics.py`), CI medians:

| | Linux | macOS | Windows |
|---|---|---|---|
| Summary, 7 days | 285 ms | 204 ms | 289 ms |
| Summary, 30 days | 1.22 s | 0.89 s | 1.29 s |
| Time series, 30 days (days) | 1.12 s | 1.22 s | 1.20 s |
| Compressors, 30 days | 1.19 s | 1.49 s | 1.60 s |
| Recent requests (one page) | 20 ms | 31 ms | 1 ms |

- **Initial cost and optimisation.** The first implementation took 3.4 s for a 30-day summary
  locally. Three changes brought it down:
  - stats rows are read only when a filter or the compressors page needs them;
  - the compressors page uses one joined query;
  - rows are fetched without sorting, as plain tuples.
- **Where the rest goes:** reading 100k rows into Python. Aggregating in SQL is the next step if
  dogfood shows larger databases. Queries run in a worker thread on their own read-only
  connection, so the proxy never waits on them; they compete only for the interpreter lock while
  they run.

**Proxy overhead E9**, p95 against the S1 baseline, CI run 37105132529:
- **200k with repeated history:** Linux 33.3 ms (0.63×), macOS 23.8 ms (0.22×), Windows 16.8 ms
  (0.31×).
- **Requests that are entirely new ("cold"):** within limits, except Linux 50k at 1.44× ("warn").
  S3 adds one counter to the proxy path. The previous run of the same path showed 1.05×, so the
  likely cause is runner variance. The weekly performance job keeps watching it.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] New code paths: API requests are not proxied traffic and have no trace. A failing metrics
  query logs one WARNING (`metrics_failure`, error type only) and answers 500 `query_failed`.
- [x] No new decision reason codes; API errors use typed error bodies (`invalid_parameter`,
  `telemetry_disabled`, `query_failed`, `forbidden_host`, `method_not_allowed`).
- [x] New telemetry field `tokens_in_accepted`: in the schema (v3), the stats records, the
  aggregates; retention deletes whole rows.
- [x] Credential and content scans cover every new endpoint
  (`test_api_returns_no_content_or_credentials_s3`); the dashboard renders only API metadata.
- [x] The recent-requests view shows outcome, status, the saving and the forwarded tokens with
  their methods, the overhead, and the trace detail.

## Known limitations

- **Query time grows with the database:** about 1.2–1.6 s for 30 days at 100k requests (see
  above).
- **The overhead chart shows the most used configuration** when a range spans several; the
  others are counted in a note.
- **The dashboard reads the browser's time zone.** The API defaults to UTC when none is given.
- **Request detail after a restart:** it shows the database record, not the trace; traces live
  in memory.
- **No settings, toggles or evaluation status** until S4. **No money figures** until S6.

## Unresolved questions

1. **Merge:** squash-merge `s3-metrics-dashboard` into `main` after acceptance, as before.
   Recommendation: yes.
2. **Dogfood (E5b) starts now.** Recommendation: keep Tokli on during normal work for about a
   week, then read the dashboard together (metadata only) before S2.5/S4 priorities are set.

Gate 2 record: **accepted 2026-10-03**, the human's words: "Accetto s3". The unresolved questions
follow the recommendations, under the product owner's standing statement that they accept
Claude's proposals: squash-merge into `main`, and the dogfood (E5b) starts now.
