# S4 — Completion report

Slice: **S4 — Compressor registry, policy and configuration API**. Branch `s4-registry-config`.
Gate 1: approved 2026-10-03 ("Approvo s4"), see `SPEC_REVIEW.md`.

Spec changes (both approved 2026-10-03):
- **SCR-001:** the policy is a shortcut, not a gate.
- **SCR-002:** `config_hash` includes `pruning`.

## Requirements implemented

| Spec | Requirements |
|---|---|
| 001 | CM-013 (`ToolRecord`, Anthropic) |
| 009 | CC-002 (after SCR-001), CC-003, CC-009, CC-015/CC-016 for `reference`, CC-019, CC-021, the request scope (ADR 0010) |
| 010 | `duplicate_tool_results` and its assumptions; **default-enabled** after E11 |
| 012 | families `reference_fact_lookup`, `reference_verbatim_quote`; checker `verbatim_line`; QE-012 after SCR-001 |
| 013 | TC-014 `reference_stubs` filled |
| 015 | `GET`/`PATCH /tokli/api/config`; `GET /tokli/api/compressors` with `locked_by` and evaluation status; API-005, API-006, API-007 |
| 016 | the Settings page; UI-003 (evaluation status), UI-004, UI-005, UI-010 (after SCR-001), AC-UI-3; saved tokens per compressor on the Overview |
| 017 | layer 5 (UI overrides), CF-002 `ui` source, CF-006 (after SCR-002), CF-009, keys added in S4 |
| 019 | PR-001…PR-005, PR-009 (duplicates never set it), PR-010…PR-013, PR-015 |

**Deferred, as approved:** `superseded_tool_results`, `analyze.tool_resources` and the shell rules
(PR-006…PR-008, PR-014: S8); diagnostics (S9); the debug banner (OB-009); money (S6).

## Exit criteria

1. **Toggling a compressor in the UI changes the next request's `config_hash` and attribution.**
   - Covered by `test_ui_toggle_changes_next_config_hash_and_attribution` (API) and
     `test_ui_toggle_patches_config` (browser).
   - Checked live by the product owner: the pruner switched on from Settings, its stubs then
     appeared in the records.
2. **The dashboard shows pruning and text-compression savings separately.** The Overview has
   "Saved tokens per compressor", each figure with its method (the product owner's choice at
   Gate 1, P10).
3. **`duplicate_tool_results` is default-enabled only with a `no_measurable_damage` smoke record
   (E11).** The record exists, so the pruner is now on by default.

## E11: smoke evaluation of `duplicate_tool_results`, 2026-10-03

Run by the product owner: `tokli eval smoke --compressor duplicate_tool_results --model
claude-opus-5-5 --temperature default --max-calls 300`; 264 calls.

| Family | Assumption | n | b | c | errors | verdict |
|---|---|---|---|---|---|---|
| `reference_fact_lookup` | `resolves_result_reference` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |
| `reference_verbatim_quote` | `quotes_from_reference_target` | 22 | 0 | 0 | 0 / 0 | `no_measurable_damage` |

- **Outcomes:**
  - candidate (stubs on): 132 of 132 pass;
  - baseline: 130 pass, and 2 fail on copying the exact line.
- **Exact saving:** 51,684 input tokens (22.4 %) on these re-read cases (baseline 231,198 →
  candidate 179,514). Report: `evals/results/2026-10-03-duplicate_tool_results-claude-opus-5-5/report.md`.
- **A replication of the `json_minify` evaluation** ran on the S4 build by mistake: the S2.5
  script was started instead of E11. It gave the same verdict, 44 of 44 with no damage and 0
  errors, and the same exact saving. The committed S2.5 report was kept; this run is recorded
  here only.

## Live use with Claude Code (dogfood), 2026-10-03

All of it is metadata from the telemetry database. The two Claude Code session files were read
with the product owner's consent, metadata only: lengths, hashes and flags, no content.

- **The pruner works on real traffic.** A repeated `git log` gave a byte-identical result; Tokli
  replaced the later copy in the forwarded request.
  - The model understood the stub: it answered correctly and named the marker.
  - Every later request of that conversation carried the same stub (prefix-stable), saving
    about 58 estimated, about 85 calibrated, tokens each.
- **Claude Code already de-duplicates `Read`.** A second `Read` of an unchanged file returned a
  93-character "unchanged" message in Claude Code's own session file, before Tokli; the first
  read was 6,840 characters.
  - Verified because the product owner suspected a Tokli bug. In that turn Tokli forwarded every
    request byte-identical (`passthrough`, 0 segments changed).
  - The session without Tokli looked different only because the model read the file with
    `cat` instead of `Read` there.
- **Repeated `Grep` searches** returned the same length but different bytes, most likely the
  same files in a different order. They are correctly not stubbed.
- **The S4 review's P7 rule (whole results only) blocks nothing on Claude Code traffic:** 0
  `multi_block` in 54 considered results.
- **Consequence:** on Claude Code the pruner's real saving is modest. It applies to repeated
  shell output, not to file re-reads. `json_minify` still finds nothing to do on this traffic:
  results are too small, not JSON, or from `Read`/`Bash`.

## Findings fixed during the slice

1. **The pruner's trace could only say `no_proposal`.** A proposal can now carry a reason, and
   the pruner records why it leaves a result alone: `no_earlier_copy`, `multi_block`,
   `small_duplicate`, `not_same_call` or `no_call_id`. Test first; ADR 0010 updated.
2. **The adapter regression found during GREEN:** a single-block tool result lost its own
   `cache_control` on parsing. It was caught by `test_anthropic_block_attributes_preserved` and
   fixed before commit.
3. **`prop_compression_is_deterministic` was flaky under a loaded run.** The wall-clock request
   budget (CC-014) made two engines differ. The property now lifts the budget, which concerns
   time, not determinism.

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **566 passed, 10 skipped** (packaging,
  real tokenizers and the browser tests run in CI). Browser tests locally (Playwright in the
  session's temporary folder): 13 passed. `ruff`, `mypy --strict` and `lint-imports` (5
  contracts) are clean.
- **CI:** run 37134577306 (commit 1ff8cdd): all 9 jobs green, cross-job identity check green; the
  browser job ran `tests/ui`, 13 passed.
- **RED first:**

  | Block | Failed first | Passed before the code |
  |---|---|---|
  | Pruner and engine | 16 | 14: properties (decode, prefix stability, structure, attribution) that hold trivially when nothing is pruned |
  | Configuration | 22 | — |
  | Browser | 8 | — |
  | Eval | — (KeyError on the missing checker) | — |
  | Skip reasons | 1 | — |
  | SCR-002 hash test | — | written after the code: the section was added before the SCR |

- **Tests that changed because the spec changed:**
  - SCR-001 rewrote the policy tests;
  - E11 changed the default, so the S1 acceptance tests for "compression disabled" and
    "`json_minify` alone" now set the pruner off explicitly, and the toggle tests switch it off
    instead of on;
  - no assertion was weakened.
- **Traceability:** rows for CM-013, CC-002, CC-009, CC-019, CC-021, PR-001…PR-005, PR-009…PR-013,
  PR-015, CF-006, CF-009, API-005…API-007, UI-003…UI-005, UI-010, QE-017 and QE-020.

## Architecture changes

- **New modules:**
  - `tokli.compressors.duplicate_tool_results`;
  - `tokli.app.runtime` (`Runtime`);
  - `tokli.app.config_service`;
  - `tokli.app.evaluations`.
- **Changed modules:**
  - `RequestCompressor`, `SegmentRef`, `ToolRecordView` and `Proposal` in the contract;
  - the engine's request scope and reference integrity;
  - `ToolRecord` and `whole_result` in the domain;
  - the UI layer and `reload()` in the config loader;
  - the proxy reads a snapshot per request.
- **ADR 0009:** runtime configuration changes, UI overrides, packaged evaluation records,
  Origin check.
- **ADR 0010:** request-scope compressors and reference integrity.
- **The policy filter and the `policy_forbids` reason are gone** (SCR-001); the request's
  `policy` is derived.

## Measured performance

E9 on CI run 37134577306, p95 against the S1 baseline. Every value is within the regression limits;
there is no warning this time.

| OS | 50k cold | 50k warm | 200k cold | 200k warm |
|---|---|---|---|---|
| Linux | 32.4 ms (1.20×) | 3.6 ms (0.23×) | 113.4 ms (1.00×) | **15.1 ms** (0.29×) |
| macOS | 29.7 ms (0.44×) | 3.5 ms (0.10×) | 117.4 ms (0.57×) | **13.9 ms** (0.13×) |
| Windows | 25.9 ms (1.09×) | 3.9 ms (0.28×) | 104.6 ms (1.03×) | **14.1 ms** (0.26×) |

With the pruner on by default, a conversation resent with one new turn is now under the Vision
target (25 ms) at 200k tokens on all three runners. The pruner adds one pass over the tool
results per request. Its plan cost is in `ms_total`: 1.6 ms in total over the 132
E11 candidate requests.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] **Request-scope proposals are traced:** accepted, rejected with reason, and declined with
  `not_applicable(<code>)`. Chains appear per segment, and `reference_stubs` is in the record.
- [x] **Reason codes:** `reference_target_modified` from the closed set; `policy_forbids`
  removed (SCR-001).
- [x] **Every accepted PATCH logs one INFO line** with the keys and the new `config_hash`.
- [x] **Credential and content scans** cover the config API and the stubs: a stub holds only the
  template, a call id and protected spans.
- [x] **The UI shows the stubs' effect** in the per-compressor table and the request trace.

## Known limitations

- **Modest gain on Claude Code** (see the dogfood section). The larger potential is in `Read` and
  `Bash` output, which today's lossless compressors deliberately leave alone.
- **The smoke tier detects gross damage only;** the full tier (S8) adds scale and models.
- **Settings changes rebuild the pipeline;** the result cache starts empty after a change.
- **Grep output order is not stable in Claude Code,** so repeated searches are not deduplicated.

## Unresolved questions

1. **Default of `duplicate_tool_results`.** The rule (CC-020, roadmap) makes it default-on
   after E11, and it is on. The dogfood shows a small real saving on Claude Code.
   Recommendation: keep it on. It is lossless, its behaviour is evaluated, and it costs about
   0.01 ms per request.
2. **Merge:** squash-merge into `main` after acceptance. Recommendation: yes.
3. **Next slice.** The roadmap says S5 (OpenAI Responses / Codex). The dogfood suggests that the
   biggest saving on Claude Code would come from `Read`/`Bash` output (S8 compressors and E8,
   which tests transformations of those outputs). Recommendation: decide at the start of the
   next slice, with the dogfood numbers.

Gate 2 record: **accepted 2026-10-03**, the human's words: "accetto S4". The unresolved questions
follow the recommendations, under the product owner's standing statement that they accept
Claude's proposals:
- `duplicate_tool_results` stays on by default;
- the branch is squash-merged into `main`;
- the next slice is chosen when it starts.
