# S8i — Completion report

Status: **accepted (Gate 2, 2026-10-22).** Nothing is committed yet.

## Requirements implemented

- **SPEC 003 AN-011:** the Anthropic adapter sets `cache_ttl_s`. It is the longest lifetime among
  the `cache_control` markers of `system`, `tools` and message blocks, including blocks inside a
  `tool_result`. A marker without `ttl` or with `"5m"` is 300 s, and `"1h"` is 3,600 s. When a
  marker is unrecognised, the lifetime is absent and the trace records `cache_ttl_unrecognised`.
- **SPEC 001:** `CanonicalRequest.cache_ttl_s` (read-only). It comes with an internal flag,
  `cache_ttl_unrecognised`, so that the proxy can trace AN-011's reason.
- **SPEC 019:**
  - PR-021 (changed): a resume is an unknown conversation, or a pause longer than the lifetime
    plus `pruning.resume_margin_s`;
  - PR-024 (changed): the store keeps the last request's `cache_ttl_s`;
  - PR-027: the lifetime fallback is the protocol default;
  - PR-028: the decision is in the trace;
  - AC-PR-17 (as corrected by SCR-002), AC-PR-18, AC-PR-19.
- **SPEC 009 CC-006 (changed):** pruners receive `is_resume` in the read-only conversation view.
  `edit_args_on_resume` no longer has a threshold of its own.
- **SPEC 017:**
  - `pruning.cache_ttl_default_s.anthropic_messages` (3,600) and `pruning.resume_margin_s` (60);
  - `pruning.resume_after_s` is removed from the schema;
  - CF-013: the old key is still accepted from a file, an environment variable or `--set`, with a
    warning at startup and in `tokli doctor`. Setting both names in one layer refuses to start.
- **ADR 0012 amendment 1:** accepted, with an implementation note.
- **S8i SCR-003** (approved 2026-10-22): the conversation key ignores `cache_control`. It was
  found by the timeline simulation; ADR 0012 amendment 2. A regression test was written first and
  failed (three keys for one conversation), then the fix.

**Deferred:** none. Part B of the review (outlines of old reads) was set aside by the human
before Gate 1. It is not part of this slice.

## Tests and evidence

| Command | Result |
|---|---|
| `python -m pytest`, with `TEST_TOKLI_PROVISIONED_DATA_DIR` set to a scratch copy of the tokenizer files | **870 passed, 6 skipped** in 7 min 46 s on Windows / CPython 3.11 (2026-10-22, after SCR-003; first run 869 passed) |
| `ruff check .` | clean |
| `ruff format --check .` | clean |
| `mypy` (strict) | no issues in 80 source files |
| `lint-imports` | 7 contracts kept, 0 broken |

The six skips are the same as before this slice:
- the browser test (`RUN_BROWSER_TESTS`);
- three packaging tests (`RUN_PACKAGING_TESTS`);
- two `cl100k_base` tests (that tokenizer is not provisioned locally).

The CI matrix (Windows, Linux and macOS × 3.11–3.14) runs on push. **It has not run yet**,
because nothing is committed or pushed.

**RED:** after an interface skeleton with no new behaviour, 81 tests failed, each on a
behavioural assertion:
- the adapter tests: `None == 3600` and `None == 300`;
- the resume boundary tests: `True is False` and `False is True`;
- the trace tests: an empty attribute set, and no `cache_ttl_unrecognised` decision;
- the renamed-key tests: the old key was refused as an unknown setting;
- the doctor golden: a different hash.

None failed on an import error, a fixture or a typo.

**New tests:**
- `tests/unit/test_resume_cache_ttl.py`:
  - `test_adapter_exposes_cache_ttl`, over all 64 combinations of no marker, no `ttl`, `"5m"` and
    `"1h"` in `system`, `tools` and a message block;
  - `test_adapter_unrecognised_cache_marker_leaves_ttl_absent`, with 4 kinds of unknown marker;
  - `test_adapter_reads_markers_inside_tool_results`;
  - `test_resume_uses_previous_request_ttl_1h` (3,661 s → resume, 3,660 s → not) and
    `test_resume_uses_previous_request_ttl_5m` (361 s / 360 s);
  - `test_resume_longest_ttl_wins`;
  - `test_resume_without_cache_marker_uses_protocol_default`;
  - `test_resume_margin_is_configurable`;
  - `test_unknown_conversation_view`;
  - `test_store_keeps_ttl_of_last_request_only`.
- `tests/integration/test_resume_pruning.py`:
  - `test_resume_trace_attributes`;
  - `test_resume_unknown_ttl_uses_protocol_default_and_traces`.
- `tests/unit/test_config_loader.py`:
  - `test_renamed_key_resume_after_s`, through the file, the environment and `--set`;
  - `test_renamed_key_and_new_key_in_one_layer_refused`;
  - `test_keys_changed_in_s8i_defaults`.
- `tests/unit/test_doctor.py::test_doctor_prints_renamed_key_warning`.
- `tests/integration/test_serve_cli.py::test_serve_prints_renamed_key_warning`.

**Changed because the spec changed** (no assertion was weakened):
- `tests/unit/test_resume_pruning.py`:
  - the view now comes from a real store with an injected clock;
  - the "after one hour" case moved from 3,601 s to 3,661 s, because of the 60 s margin;
  - "two hours → pruned" and "one hour minus a second → nothing" are unchanged.
- The config-loader key tables and the pinned default behaviour JSON, which sets the
  `config_hash`.
- The two doctor goldens: the new hash `33c7dc45aa821df5`, and two key lines in place of one.

`TOKLI_TRACEABILITY.md` has rows for:
- `cache_ttl_s` (SPEC 001);
- AN-011;
- CC-006;
- PR-021, PR-024, PR-027 and PR-028;
- CF-013.

## Architecture changes

- **`tokli.domain`:**
  - `CanonicalRequest` has `cache_ttl_s` and `cache_ttl_unrecognised`;
  - `ConversationView` is now `is_resume`, `pruned_call_ids`, `seconds_since_last`,
    `cache_ttl_s` and `cache_ttl_source`.
- **`tokli.protocols.anthropic_messages`:** `_cache_ttl` reads the markers. It does not search
  tool inputs or schemas: a field named `cache_control` there is opaque. A test covers this.
- **`tokli.app.conversations`:**
  - the store keeps `(time, cache_ttl_s, pruned ids)`;
  - `view(key, protocol)` makes the resume decision;
  - the defaults and the margin come from the config.
- **`tokli.http.proxy`:** a new `conversation` span after `parse` carries the decision.
- **`tokli.config`:** `RENAMED_KEYS` and a per-layer rename with warnings;
  `EffectiveConfig.warnings`.
- **`tokli.compressors.edit_args_on_resume`, registry, bootstrap:** the threshold parameter is
  gone.
- **No new dependency direction** (the import contracts are green), no new seam, no persistence
  change, no telemetry schema change.

## Measured performance

`benchmarks.overhead` was run with 30 iterations on the development machine (Windows), in an A/B
comparison on that same machine.
- **Code before S8i vs after:** every case is within noise. Cold: 10k 1.00×, 50k 1.00×,
  200k 1.01×. Warm: 0.83×–1.21×.
- **Against the stored CI baseline,** both the before and the after code show "warn" or "FAIL" on
  cold requests. For example, 50k cold is 80 ms before S8i and 80 ms after, against 24 ms in the
  baseline. This is the development machine, not the slice. The CI performance job on its own
  runner is the reference.

## Real-traffic replay

**Not run.** No compressor's output changed. Only *when* `edit_args_on_resume` acts changed. The
replay tool (`tools.replay`) passes no conversation state, so it treats every request as a resume.
Its counters would therefore be identical before and after S8i. The roadmap's exit for S8i
already records that the replay is not required.

### Timeline simulation (asked for by the human, 2026-10-17; counters only)

A script outside the repository simulated the timeline. It replays every request of the human's
Claude Code sessions in order, at its real time: 11 sessions over the last 7 days, 5,106 requests.
- **Tokli side:** each request goes through the real pipeline, with a real conversation store
  driven by the transcript clock and the human's effective configuration
  (`edit_args_on_resume` on).
- **Provider side:** a model of the prefix cache. A request reads the previous prefix when the
  pause is within the lifetime and the prefix did not change. Otherwise it writes it again.
- **Costs** use the shipped `claude-opus-5-5` prices: a 1 h write $8, a 5 min write $5, a read
  $0.20 per MTok.
- **Not counted:** the system prompt, tools and output (the same in every scenario); quality.

| Scenario | Resumes | Rewrites | Rewrites with a warm cache | Cost | Saved |
|---|---|---|---|---|---|
| no Tokli, client asks "1h" | — | — | — | $1,051.11 | — |
| S8i rule, "1h" | 91 | 43 | 0 | $1,008.02 | $43.10 (4.1 %) |
| S8c rule (fixed 3,600 s), "1h" | 68 | 46 | 0 | $1,007.66 | $43.45 (4.1 %) |
| no Tokli, client asks "5m" | — | — | — | $2,083.89 | — |
| S8i rule, "5m" | 447 | 174 | 0 | $1,946.00 | $137.89 (6.6 %) |
| S8c rule, "5m" | 68 | 46 | 0 | $1,988.42 | $95.48 (4.6 %) |

- **With Claude Code's 1 h lifetime, S8i changes nothing measurable.** Neither rule ever rewrote
  a still-valid cache.
- **For a 5-minute client, S8i saves 44 % more than the S8c rule.**
- **Where the saving comes from:** 99.4 % of the tokens not sent come from
  `edit_args_on_resume`. Its higher refusal rate, measured in S8c (E10(c)), is not modelled here.
- **Finding: the conversation key changes between a conversation's first and second request.**
  The key hashes the first message including its `cache_control`, and Claude Code moves the marker
  to the last block. So the second request looks unknown and counts as a resume. This adds to the
  91 against 68 (not separately counted). It causes no rewrite, because no call is old enough yet. The cause
  predates S8i (ADR 0012). **Fixed by S8i SCR-003** (2026-10-22).

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] **New code paths emit spans with durations:** the `conversation` span (the store lookup and
  the decision).
- [x] **New decisions use a reason code from §4:** `cache_ttl_unrecognised` was added to §4 under
  "Cache lifetime". It is the code specified by AN-011.
- [x] **New telemetry fields:** none. The facts go to the trace only (SCR-001 §7).
- [x] **Credential and content scans:** the span holds only booleans, numbers and a closed set of
  source names. `test_resume_trace_attributes` also asserts that the
  trace JSON does not contain the request's text. The existing scan tests go through the same
  proxy path.
- [x] **Recent-request view:** the dashboard prints every span's attributes, so the
  `conversation` span appears there without a UI change.

Sample span, from the integration test's synthetic conversation 360 s after a request with
5-minute markers:

```text
conversation  ok {"resume": false, "cache_ttl_s": 300, "cache_ttl_source": "previous_request", "since_last_s": 360}
```

## Docs updated

- `TOKLI_COMPRESSORS.md` (`edit_args_on_resume`: how a resume is decided; settings);
- `TOKLI_OBSERVABILITY.md` (§3 the `conversation` span; §4 the reason code);
- `TOKLI_TRACEABILITY.md`;
- ADR 0012 (amendment 1 with the implementation note);
- the SPEC 001, 003, 009, 017 and 019 status lines.

## Known limitations

- **The decision uses the previous request's lifetime.** If a client switches from `"1h"` to
  `"5m"` within one conversation, the switch takes effect from the following request. This
  follows PR-027 by design (ADR 0012 amendment 1, "Alternatives").
- **A protocol without an adapter has no default.** The schema has a field only for
  `anthropic_messages`. A new adapter must add its own field (SPEC 017: "one entry per protocol
  with an adapter").
- **The resume rule changes no output by default,** because `edit_args_on_resume` is off by
  default. On the human's machine it is on, and it stays on as they configured it.

## Unresolved questions

None for this slice. After acceptance, the human asked to discuss reducing files read through
the shell at a resume.

Gate 2 record: 2026-10-22. The human's words: "I accept and I want to proceed with S8k" (translated from Italian), given after both reports were presented together.
