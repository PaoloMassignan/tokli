# S8k — Completion report

Status: **accepted (Gate 2, 2026-10-22).** Nothing is committed yet.

## Requirements implemented

- **`TOKLI_TEST_STRATEGY.md` §2, "Context composition":** `python -m tools.composition`. It is
  local, consented on every run, and prints counters only.
- **P1 (a):** the fixed part is fitted from the exact provider usage in the session files.
- **P2:** a tool in the repository, with tests.
- **P3 (b):** it prints tokens, re-read tokens, rewritten tokens and an input-side cost share. It
  also prints a check against exact usage and the split by kind of cost.
- **P4:** `--days 7` by default; the evidence record uses 14 days.
- **`TOKLI_TEST_STRATEGY.md` §7:** the E5 row points to the new measurement.

**Deferred:** P1 (b), telemetry by segment kind, by the human's decision. It is needed only to
split the fixed part between the system prompt and the tool definitions.

## Tests and evidence

| Command | Result |
|---|---|
| `python -m pytest tests/integration/test_composition.py` | 6 passed |
| `python -m pytest` (full suite) | **954 passed, 6 skipped** in 7 min 6 s on Windows / CPython 3.11 (2026-10-22); the same six skips as before |
| `ruff check .`, `ruff format --check .`, `lint-imports` | clean; 7 contracts kept |
| `mypy --strict tools/composition.py` | no issues (the project's mypy run covers `src` only) |

**RED:** an interface skeleton (empty `Totals`, a `measure` that counts nothing, an empty
`render`, a `main` that returns 0). The six tests failed, each on a behavioural assertion
(counts 0, no fit, no rewrites, an empty table, no consent prompt).

**One expectation was corrected before GREEN.** It was not a spec change. My first test
expectations counted every later request as a cache read. The first request after a block writes
it to the cache instead, so re-reads are L − 1 − R. The module docstring and the tests state the
corrected accounting.

**New tests:** `test_composition_counts_parts`, `test_composition_weights_stop_at_compaction`,
`test_composition_fixed_part_from_usage`, `test_composition_rewrites` (with the exact usage
sums), `test_composition_prints_counters_only`, `test_composition_asks_consent`.

## Architecture changes

- **`tools/composition.py`** is new, outside `src/`, so no import contract changes. It imports
  `tokli` (bootstrap, the S8j shell-read classifier, `normalise_path`) and `tools.replay`
  (`SESSIONS`, `session_files`).
- **Implementation decisions** that differ from the SPEC_REVIEW:
  - **Own session reader.** The SPEC_REVIEW proposed reusing the replay's reader. That reader
    drops the usage and the compaction summaries, which this tool needs, so the tool reads the
    events itself. `tools/replay.py` is unchanged.
  - **The fixed part is fitted by least squares** over all requests of a context (provider input
    against estimated content), not from the first request alone. The intercept is the fixed part
    and the slope is the provider/estimate ratio. It is the same source as P1 (a), and less
    sensitive to one request.
- No ADR: no persisted format, contract or dependency changes.

## Measured performance

14 days, 15,300 requests: 7 s on the development machine.

## Measurement (2026-10-22, 14 days, counters only)

The full record is in `TOKLI_EVIDENCE.md`, "S8k — composition of the cached context". In short:

| Part | Share of input-side cost |
|---|---|
| Writes (`Write`/`Edit` arguments and results) | 27.1 % (code 18.2 %, Markdown 6.6 %) |
| File reads | 20.7 % (code 12.7 %, Markdown 4.0 %) |
| Other tool results | 17.2 % (`Bash` 13.3 %) |
| Fixed part (median 46,961 provider tokens per request) | 16.7 % |
| Other call arguments | 10.0 % (`Bash` 7.4 %) |
| Text | 8.2 % |

- **By kind of cost:** cache reads 62.9 %, full rewrites 30.8 %, first writes 6.3 %.
- **Check:** the modelled re-reads are −6 % from the exact cache reads, and the modelled writes
  +10 % from the exact cache writes.

## Observability evidence

Not applicable: a measurement tool with no proxy code path. The privacy rules hold:
- the output holds part names and numbers only;
- tool names are printed only when they look like a built-in name, and MCP tools are grouped;
- `test_composition_prints_counters_only` checks a canary, paths and commands.

## Known limitations

- One developer and 14 days, on a specification-heavy repository.
- Content tokens are estimates, and the fixed part is a fit, which failed in 6 of 70 contexts.
- The input-side cost leaves out output.
- The proxy telemetry in the default data directory ends on 2026-10-13. Recent traffic did not go
  through this Tokli instance.

## Unresolved questions

None for this slice. The choice of the next lever (S8l, S8m, or the fixed part) is the human's.

Gate 2 record: 2026-10-22. The human's words: "Accept" (translated from Italian).
