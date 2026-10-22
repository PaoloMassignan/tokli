# S8j — Completion report

Status: **accepted (Gate 2, 2026-10-22).** Nothing is committed yet.

## Requirements implemented

- **SPEC 019:**
  - PR-040…PR-046 (`outline_first_read`, version 1, SELECTIVE, prefix-stable, off by default);
  - "Shell file reads (Claude Code)";
  - AC-PR-27…AC-PR-33.
- **SPEC 009:** CC-021 (c) (S8j SCR-001).
  - `CompressorSpec.target_tools` is new.
  - The engine now applies the verbatim filter (CC-021, CC-023) in the request-scope path too, with
    the exceptions (a), (b) and (c).
  - Before S8j that path had no such filter. It made no difference, because no non-reference
    pruner read tool results (`edit_args_on_resume` reads argument segments only). The behaviour of
    every existing compressor is unchanged.
  - The registry rejects `target_tools` on a compressor that is not SELECTIVE and off by default.
- **SPEC 010:** the catalogue row and the assumption `outline_suffices_until_reread`.
- **SPEC 017:** the "Keys added in S8j".
- **SPEC 003 AN-012:** the response's `stop_reason`, read by both usage parsers. A plain token is
  kept, any other value becomes `other`, and unknown is `null`.
- **SPEC 013 TC-022:** `requests.stop_reason`. It is shown in the request API view, in schema v5
  (ADR 0015, forward migration).

**Deferred:** none. Out of scope by the human's decisions are:
- Markdown and other non-code files;
- partial reads;
- outlines at a resume;
- summaries written by a model;
- the stub of long shell commands.

## Tests and evidence

| Command | Result |
|---|---|
| `python -m pytest`, with `TEST_TOKLI_PROVISIONED_DATA_DIR` set to a scratch copy of the tokenizer files | **948 passed, 6 skipped** in 7 min 8 s on Windows / CPython 3.11 (2026-10-22) |
| `ruff check .`, `ruff format --check .` | clean |
| `mypy` (strict) | no issues in 81 source files |
| `lint-imports` | 7 contracts kept, 0 broken |

The skips are the same six as before: the browser test, three packaging tests, and two
`cl100k_base` tests. The CI matrix has not run, because nothing is committed.

**The first full run failed three tests and two static checks.** All were fixed before the green
run above:
- **three registry listings without the new compressor:** `test_every_compressor_has_a_real_format_expectation`,
  `test_keys_marked_ui_editable` and `test_chain_order_by_stage_then_id`;
- **a ruff warning:** an unused variable in a test;
- **a mypy type error:** in the default of `pruning.outline_rules`.

**RED:** after an interface skeleton with no behaviour (the empty pruner, the new fields and keys),
47 tests failed, each on a behavioural assertion:
- the shell rules returned `None`;
- the expected skeletons and reasons were missing;
- `stop_reason` was `None`;
- the schema version was 4;
- the registry contract did not raise.

**Two test expectations were corrected while going green.** Neither was a spec change.
- **The runs were wrong in my expected outlines.** The spec's run is the maximal run of lines that
  are not kept, and the two blank lines after a function belong to it ("lines 11-18", not
  "11-16"). E10(f) built its forms the same way.
- **The protected-span test used a file too small to save anything.** With the test counter (one
  token per character) the skeleton was not shorter, so the engine's gain gate rightly rejected
  it (`no_gain`). The test now uses a longer function body.

**New tests:**
- `tests/unit/test_outline_first_read.py` and `tests/integration/test_outline_first_read.py`:
  62 cases together, the shell rules table included;
- `test_anthropic_stop_reason_non_stream`, `test_anthropic_stop_reason_stream`, and the stop reason
  in `prop_usage_stream_any_chunk_split`;
- `test_migration_v4_to_v5`;
- `test_stop_reason_persisted_and_in_api`.

**Changed because the spec changed** (no assertion was weakened):
- the config-loader key tables and the pinned default behaviour JSON;
- the registry listings: `test_registry_lists_the_s8e_compressors`, `test_chain_order_by_stage_then_id`
  (the engine orders pruners by stage, then id, so `duplicate_tool_results` runs before
  `outline_first_read`; CC-019 then reverts a duplicate stub that names an outlined read), and
  `test_keys_marked_ui_editable` (the new toggle, CF-009);
- the real-format fixture (`tests/fixtures/agent_formats`): a `cat` through `Bash` of a synthetic
  module, the shape measured on 2026-10-17, and its expectation in `test_agent_formats.py`;
- the schema version pins (4 → 5) in two migration tests;
- the two doctor goldens: hash `66a272fc366d554b`, five key lines and one compressor line.

## Architecture changes

- **`tokli.compressors.outline_first_read`** is new. It holds the pruner, the Claude Code
  shell-read classifier and the outline. It reuses `normalise_path` from `reread_by_reference`.
- **`tokli.compression`:**
  - `CompressorSpec.target_tools`;
  - the engine's request-scope verbatim filter;
  - `validate_registry`.
- **`tokli.protocols.anthropic_usage`, `tokli.domain.usage`, `tokli.app.request_record`,
  `tokli.telemetry`:** the stop reason, and schema v5.
- **ADR 0015** (schema v5) is accepted. There is no new dependency direction, and the import
  contracts are green.

## Measured performance

`benchmarks.overhead` was run with 30 iterations, compared with the run of the code before S8i on
2026-10-16 on the same machine.
- **Every case is "ok"** (0.43×–0.90×).
- **This is not a clean A/B comparison.** The estimate-only cases, which S8j does not touch, are
  also about twice as fast. So the machine was less loaded today, and the run shows no regression
  rather than a speed-up.
- **With the default configuration** the pruner is disabled, so its cost is the engine's
  `disabled` pre-filter.

## Real-traffic replay (2026-10-22, the human's last 7 days, counters only)

`python -m tools.replay --yes --set compressors.outline_first_read.enabled=true`: 5 session files,
12 contexts, 910,111 tool-result tokens (estimate).

| | Considered | Applicable | Accepted | Saved | Share of tool-result tokens |
|---|---|---|---|---|---|
| `outline_first_read` | 1,383 | 6 | 6 | 11,579 | 1.27 % |

**Skip reasons:**

| Reason | Count |
|---|---|
| `not_file_read` | 1,302 |
| `partial_read` | 36 |
| `error_result` | 26 |
| `no_outline_rule` | 11 |
| `below_min_tokens` | 1 |

**Reading the replay:**
- Most shell results are not a simple read of one file: pipes, several files, scripts, tests.
- No read was skipped as `seen_before` in these contexts: the 6 outlined reads were first reads.
- The replay cannot show re-reads that the skeleton would cause, because the transcripts record
  what the agent did with whole files.
- The compressor is off by default, so the "0 % applicability" rule (S8h P4) does not apply.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] **New code paths emit spans with durations:** the pruner runs inside
  `transform.compression`, with per-compressor timing as every compressor.
- [x] **New decisions use reason codes from §4:** `not_applicable(<code>)` with the codes listed in
  SPEC 019 PR-041/PR-042/PR-043, and `verbatim_tool` for the request-scope filter.
- [x] **New telemetry fields:** `stop_reason` is in the record (schema v5), the forward migration
  and the request API view. The retention job deletes whole rows, so it needs no change.
- [x] **Credential and content scans:** the stop reason is restricted to `^[a-z_]{1,32}$` or
  `other`, so no response text can be stored. The outline's notes hold only line numbers.
- [x] **Recent-request view:** the record and the per-compressor rows show the outline's
  statistics and the stop reason.

## Known limitations

- **Damage detected (E10(f)):** more refusals on questions about an outlined file. With the
  compressor on, the refusal rate in real use is now measurable from `stop_reason`, but no
  aggregate shows it yet. It is a query over `requests` and `compressor_stats`.
- **Little volume on the developer's traffic:** most file reads go through ranges or pipes.
- **Paths:** a relative path inside a `cd <dir> &&` command and the same file spelled differently
  elsewhere are matched only by suffix. A miss means a file counts as new, so it can be outlined
  although the agent saw it before. That costs a re-read, not a wrong answer.

## Unresolved questions

None for this slice.

Gate 2 record: 2026-10-22. The human's words: "I accept and I want to proceed with S8k" (translated from Italian), given after both reports were presented together.
