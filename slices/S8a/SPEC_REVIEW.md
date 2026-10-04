# S8a — Spec review

Slice: **S8a — Claude-complete compressors** (`TOKLI_ROADMAP.md`, split from S8 at the human's
request on 2026-10-03: S8a before S5, Anthropic only; S8b after S5–S7).
Status: **S8a-1 approved 2026-10-03 (Human Gate 1).** S8a-2 and S8a-3 have their own Gate 1.

## Scope

**Roadmap S8, as written:**
- the full evaluation tier (generators, bootstrap CIs, multi-model and multi-provider runs, Tier 3);
- `diff_context_trim` and `log_filter` (SELECTIVE);
- `dictionary` and `search_group` (LOSSLESS);
- `analyze.tool_resources` and `superseded_tool_results`;
- the experiments E7, E8, E2-ext and E10.

**S8a takes the part that needs only Anthropic.** The proposed contents are in P2 below.

**Requirements touched:**

| Spec | Requirement | Item |
|---|---|---|
| 010 | CP-SG-001…004, CP-DI-001…004, CP-DT-001…004, CP-LF-001…004, the assumption ids | compressors |
| 019 | PR-006, PR-007, PR-008, PR-009 (superseding), AC-PR-4…AC-PR-8 | pruning |
| 009 | CC-018 (`history_rewritten`, UI cache marker) | engine, UI |
| 011 | RT-001 for `grep_lines`, `diff_shape`, `leveled_ratio`, `line_count`, `crlf` | features |
| 012 | new case families for the new assumptions (smoke tier) | evaluation |
| 013 | TC-014 (`history_rewritten` set by a real pruner) | telemetry |
| 016 | UI-003 (kinds, assumptions, "may invalidate provider cache") | dashboard |
| 017 | new keys (A9) | config |

**Out of scope** (proposed for S8b or later):
- QE-003 multi-provider full tier;
- PR-014, the Codex shell-command rules: no Codex adapter before S5;
- Tier 3 agent tasks, and with them E8 and E10(b);
- money in E2-ext (S6).

## 1. Ambiguities

| Id | Requirement | Question | Proposed reading |
|---|---|---|---|
| A1 | PR-007 vs SPEC 019 "Design" | Whose age counts? PR-007 says the **superseding** record must be older than `min_age_turns` user turns; the design paragraph says "apply superseding only to results older than the last N user turns" (the **superseded** one). | The superseded result must lie before the last N user turns. That is what keeps the recent cache prefix intact, the purpose of the rule. PR-007 to be reworded (spec delta). |
| A2 | PR-007, PR-009 | What is a "user turn" in an agent conversation? In Claude Code every tool result travels in a `user` message. | A user turn is a `user` message that contains human text (a text block or string content that is not only `tool_result` blocks). `history_rewritten` (PR-009) is true when a stub lands in a message before the last such turn. |
| A3 | PR-007 | Is the saving threshold (8,000 tokens) counted before or after the age filter? | After: it is the sum of the stubs that would be applied in this request. Below the threshold, none is applied (skip reason `below_min_saving`). |
| A4 | CP-DT-001…004 | Where does a hunk end? "Text after the last hunk that is not a valid hunk line" leaves room for interpretation (hazard H10). | A hunk's body is delimited by the line counts of its `@@ -a,b +c,d @@` header. Anything outside a counted body is verbatim. A segment with no well-formed hunk header is `not_applicable(not_diff)`, even if the `diff_shape` feature fired. |
| A5 | CP-DT | "At most `max_context` unchanged lines around each change cluster": before, after, or both? | Up to `max_context` before and up to `max_context` after each cluster, as in `diff -U1`. |
| A6 | CP-LF-003, CP-DT-003 | Line ending of the omission note in a CRLF segment. | The note uses `\r\n` when every line of the segment ends with `\r\n`, otherwise `\n`. |
| A7 | CP-DI-001 | The phrase length has no upper bound, so candidate enumeration is not linear. | `max_phrase_words` = 12 (config, POLICY provisional). Candidates are enumerated in O(n × 12). A linearity test like AC-RT-1 is added. |
| A8 | CP-SG-001 | Does `min_group_lines` count grep lines in the whole segment or per group? | In the whole segment (`grep_lines ≥ 5`). Groups still need ≥ 2 consecutive same-path lines. |
| A9 | SPEC 017 | Options such as `min_group_lines`, `max_context`, `debug_sample`, the dictionary limits, `tool_semantics` and the superseding thresholds have no config keys. | `compressors.<id>.<option>` for compressor options; `pruning.tool_semantics`, `pruning.superseded_min_age_turns`, `pruning.superseded_min_saving_tokens`. None of them is UI-editable. All enter `config_hash`. Listed in SPEC 017 "Keys added in S8a". |

## 2. Contradictions

- **C1** — PR-007 against the SPEC 019 design paragraph (A1).
- **C2** — CC-020 against TOKLI_TEST_STRATEGY §5:
  - CC-020 (approved in S1): "Whether the user may enable a compressor SHALL NOT depend on evaluation records."
  - Test strategy §5: a SELECTIVE compressor is "available" only with "Tier 2 run and published; drop CI upper bound ≤ 5 pp".
  - Proposed: CC-020 governs, being normative and approved. The selective compressors ship available and off, shown as "not evaluated". The §5 column becomes a v1 release criterion (S8b).
- **C3** — QE-003 against the S8a scope. QE-003 asks for ≥ 2 providers in the full tier, so a full-tier record cannot exist in S8a. The full tier moves to S8b (P2).

## 3. Missing behaviour and hazards found

- **M1 — a "file unchanged" re-read must never supersede.**
  - The S4 dogfood showed that Claude Code answers an unchanged re-read with a short message of 93 characters instead of the file. As written, PR-007 treats that re-read as a "full read of X" and would stub the earlier copy: **the only copy of the file in the conversation would disappear.**
  - Results with `is_error` (file not found, permission) have the same problem.
  - Proposed new rule (PR-016): a later read supersedes only if its result is not an error and its estimated tokens are at least `pruning.superseded_min_view_ratio` (default 0.5) of the earlier result's.
- **M2 — `verbatim_tools` hides most Claude Code traffic from the new compressors.**
  - The default `["Read", "Bash", …]` excludes file reads and every shell output: `git diff`, test and build logs, `grep` run through `Bash`. The segment compressors `search_group`, `diff_context_trim`, `log_filter` and `dictionary` would then apply only to Claude Code's `Grep` tool, to MCP tools and to `WebFetch`.
  - The dogfood suggested the gain is precisely in `Read`/`Bash` output.
  - The list is a HEURISTIC that E8 revises, and E8 needs Tier 3. This is product question P3.
- **M3 — no smoke case families for the new assumptions.** SPEC 012 defines families only up to S4. To give the new compressors evidence in S8a, five families are needed, one per new assumption: `reads_grouped_search`, `applies_dictionary_legend`, `outdated_content_not_needed`, `context_lines_not_needed` and `omitted_log_lines_not_needed`.
- **M4 — new reason codes.** The skip and decline reasons must be added to TOKLI_OBSERVABILITY §4 first:
  - `not_applicable(too_few_grep_lines)`, `not_applicable(collision)`, `not_applicable(not_diff)`, `not_applicable(too_few_leveled_lines)`;
  - for the pruner: `not_applicable(too_recent)`, `not_applicable(below_min_saving)`, `not_applicable(not_superseded)`, `not_applicable(unknown_resource)`, `not_applicable(weak_view)` (M1).
- **M5 — PR-014 (Codex shell rules) has nothing to classify before S5.** It moves to S5 or S8b.

## 4. Portability concerns

- `search_group` must recognise Windows drive-letter and UNC paths (CP-SG-003, H03). All
  round-trips must hold for CRLF, LF and mixed endings.
- Path normalisation for resource keys runs with no filesystem access: `\` → `/` and a lowercase
  drive letter. Relative and absolute spellings stay different keys, so they are not superseded.
- The log level keywords are ASCII and case-insensitive, matched on whole words; non-ASCII text
  passes through unchanged.

## 5. Observability requirements for this slice

- The new reason codes (M4) go into §4 before code. The trace shows each pruner decision with its
  reason, as for `duplicate_tool_results`.
- `history_rewritten` becomes really settable: persisted, in the API, in the request view.
- UI: "may invalidate provider cache" next to `superseded_tool_results` (CC-018).
- The content scan tests cover the new stubs and notes: they hold only the template, call ids,
  counts and a resource display name. A file path is user content, so whether the display name is
  allowed in the stub is product question P5.

## 6. Architectural risks

- **R1 — the resource keys need a contract change.** `analyze.tool_resources` is an analyzer stage (SPEC 007). The pruner must see `resource_key` and `action` (PR-006) but not how they were derived. `ToolRecordView` and `StageView` therefore gain fields. This contract is used by the engine, the pipeline and the adapters, so it needs an ADR (CLAUDE.md §6).
- **R2 — Features gains five fields.** They enter the result-cache key, which already contains `Features`. No new seam.
- **R3 — pruners running after an earlier pruner.** `superseded_tool_results` runs after `duplicate_tool_results` (stage, id). Reference integrity (CC-019, AC-PR-8) already covers this case.
- **R4 — no new seam is needed.** Each compressor is a module plus one registry entry (CC-011).

## 7. Product questions → for the human

1. **P1 — measure before choosing? (E5b-lite)**
   - **Method:** with your consent, I run a local script over your Claude Code session files. As in S4, it records **counters and flags only** and never prints or stores content. Per tool name it measures:
     - the tokens of the results;
     - how many results have grep, diff or log shape;
     - how many `Read` results are followed by a later full `Read` of the same file (supersedable), excluding the "unchanged" answers.
   - **What it decides:** which compressors and pruners actually matter on your traffic, before we build them.
   - **Recommended: yes.**
2. **P2 — contents of S8a** (the slice is too large as one block). Recommended split:
   - **S8a-1:**
     - `analyze.tool_resources` (Claude Code only);
     - `superseded_tool_results` with the M1 rule;
     - `history_rewritten` and the cache marker;
     - the smoke family `outdated_content_not_needed`;
     - **E2-ext in tokens** (cache_write vs cache_read from exact usage; money comes in S6).

     Pruning had the largest potential in E5a.
   - **S8a-2:** `search_group` and `dictionary` (LOSSLESS) with their smoke families. E7 is run as a smoke evaluation on Claude models.
   - **S8a-3:** `diff_context_trim` and `log_filter` (SELECTIVE) with their families.

   If P1 is accepted, the order of S8a-1…3 follows the measurement.
3. **P3 — `verbatim_tools` and Claude Code (M2).** Options:
   - (a) leave the default: little gain on Claude Code from the segment compressors;
   - (b) take `Bash` out of the default after a smoke family "edit anchor taken from shell output" (an E8 at smoke level, without Tier 3);
   - (c) per-compressor exemptions. For example `log_filter` and `diff_context_trim` could also apply to `Bash`, since they are selective and off by default, so the user chooses.

   **Recommended: (c)**, the default list unchanged. It needs a spec change to CC-021 / SPEC 010: a per-compressor `apply_to_verbatim_tools` option, off by default.
4. **P4 — accept the M1 rule** (PR-016, `superseded_min_view_ratio` = 0.5, errors never supersede)? **Recommended: yes.**
5. **P5 — resource name in the superseding stub.** SPEC 019 puts `<resource display name>`, a file path, in the stub, which goes to the provider. The path is already in the conversation (in the tool call), so nothing new is disclosed. Keep it? **Recommended: yes**, with the path as written in the call; no new disclosure.
6. **P6 — CC-020 against test strategy §5 (C2):** selective compressors available without Tier 2, shown as "not evaluated"? **Recommended: yes.**
7. **P7 — moving PR-014 (Codex shell rules) and the full tier, Tier 3, E8 and E10 to S8b.** **Recommended: yes.**

### Answers (2026-10-03)

The human: "Ok per tutti ma non posso usare le ultime sessioni di Claude code?" Every
recommendation in P1…P7 is accepted. For P1, the measurement uses the human's most recent Claude
Code sessions, with counters and flags only (E5b-lite, section 10).

## 8. Implementation decisions (Claude decides, recorded)

- Every new compressor is a module in `tokli.compressors` plus one registry entry, with
  `default_enabled: false` and options validated by a pydantic model.
- `analyze.tool_resources` is a pipeline analyzer that runs before `transform.compression`.
  Resource keys reach the engine through the stage view, and the pruner gets them in
  `ToolRecordView`. This goes in ADR 0012.
- The features are computed in one O(n) pass over the text, with no regex backtracking.
- Test order: Tier 0 property and guarantee tests first (CC-015), then integration, then the case
  families and their generators (CI self-test against the fake upstream).

## 9. Test plan

Per compressor, the test lists of SPEC 010 and 019. In addition:
- `test_dictionary_linear_time` (A7);
- `test_unchanged_reread_never_supersedes` and `test_error_result_never_supersedes` (M1);
- `test_user_turn_definition` (A2);
- `test_superseded_age_counts_superseded_result` (A1);
- the reason-code tests (M4);
- `test_ui_marks_cache_invalidating_compressor` (CC-018).

The detailed mapping goes into the traceability after Gate 1, for the sub-slice approved.

## 11. S8a-1: scope and spec delta (P8 and P9 confirmed: "Confermo", 2026-10-03)

**In S8a-1:**
- `search_group`: CP-SG-001…004, with review A8;
- `log_filter`: CP-LF-001…004, with review A6;
- the per-compressor `apply_to_verbatim_tools` (SCR-001: CC-021, CF-009, UI-012, test strategy §5);
- the features `grep_lines`, `leveled_ratio`, `line_count` and `crlf` (RT-001);
- four smoke families: `grep_fact_lookup`, `grep_verbatim_quote`, `log_fact_lookup` and
  `log_verbatim_quote`;
- the config keys in SPEC 017 "Keys added in S8a-1".

**Later:**
- A4, A5 and A7 apply in S8a-2;
- A1, A2, A3, M1 (PR-016) and the pruner reason codes apply in S8a-3, with their spec delta at
  that sub-slice's Gate 1.

**Delta:** the `git diff` of TOKLI_ROADMAP.md, TOKLI_TEST_STRATEGY.md and specs 009, 010, 011,
012, 016 and 017, plus `SCR-001-verbatim-tools-opt-in.md`. The status lines record the approval.

**Additional implementation decisions:**
- per-compressor options live in the `compressors.<id>` section of the config schema, next to
  `enabled`;
- the engine's verbatim filter reads `apply_to_verbatim_tools` from the effective settings;
- the features are computed in one pass in `analyze.features`.

Gate 1 record (S8a-1): **approved 2026-10-03**, the human's words: "Accetto" (answering the request
to approve S8a-1 and SCR-001). Spec delta: TOKLI_ROADMAP.md (S8a/S8b), TOKLI_TEST_STRATEGY.md §5,
SPEC 009 CC-021, SPEC 010 (`search_group`, `log_filter`), SPEC 011 RT-001 features, SPEC 012
families, SPEC 016 UI-012, SPEC 017 CF-009 and the S8a-1 keys; SCR-001 approved.

## 10. E5b-lite: measurement on recent Claude Code sessions (P1, 2026-10-03)

**Method.** A local script read the human's Claude Code session files of the last 14 days, with
consent: 39 sessions, 17,607 requests, 28 compactions. Subagent side-chains were left out. It
kept counters and flags only: no text, path or tool argument was printed or stored.

**Measures:**
- Tokens are estimated as characters / 4.
- "Weighted" = a result's tokens × the number of later requests that resend it. A result stops
  counting at the next compaction boundary.
- Most of this volume is cache reads at the provider. It is a measure of tokens, not of cost.

**Shape flags** (approximate):
- grep: ≥ 5 `path:line:` lines. This also matches compiler and linter output.
- diff: a well-formed `@@` hunk header.
- log: ≥ 10 lines with ≥ 10 % leveled.
- json: the text starts and ends with JSON brackets.

| Item | Weighted tokens | Share of tool-result volume |
|---|---|---|
| All tool results | 1,114.6 M | 100 % |
| `Bash` results | 527.1 M | 47.3 % |
| `Read` results | 414.3 M | 37.2 % |
| `Grep` tool results | 19.9 M | 1.8 % |
| grep-shaped results, all tools (`Bash` 53.0 M, `Read` 8.4 M, `Grep` 4.4 M, others 2.7 M) | ≈ 68.5 M | ≈ 6.1 % |
| log-shaped results, all tools (`Bash` 50.1 M, `Read` 13.2 M, `PowerShell` 3.6 M, others 1.5 M) | ≈ 68.3 M | ≈ 6.1 % |
| JSON-shaped (`Bash` 10.5 M, others 1.3 M) | ≈ 11.9 M | ≈ 1.1 % |
| diff-shaped (`Bash` only) | 4.6 M | 0.4 % |
| Reads superseded under the M1 rule and the 4-turn age rule (85 reads) | 18.9 M (21.2 M without the age rule) | 1.7 % |
| *For comparison:* `Edit`/`Write`/`MultiEdit`/`NotebookEdit` **arguments** resent | 857.9 M | (77 % of the tool-result volume; not a tool result) |

**Findings:**

1. **84.5 % of the tool-result volume comes from `Bash` and `Read`, the default
   `verbatim_tools` (M2).** Without P3, the segment compressors reach at most about 4 % of it
   (`Grep`, MCP, web, agents).
2. **Upper bounds of the new compressors, before their own saving ratio:**
   - grep-shaped output (`search_group`) and log-shaped output (`log_filter`) are about 6 % each;
   - superseded reads are 1.7 %, which is little;
   - diffs are 0.4 %.

   The real saving is a fraction of each: grouping and filtering remove part of the text, not all of it.
3. **The largest item is not a tool result.** It is the arguments of `Edit` and `Write`
   (`old_string`, `new_string`, file contents), resent on every turn. That is E10, not in v1 and
   outside S8a; it would need its own spec and the API-acceptance experiment E10(a).
4. **`superseded_tool_results` is worth little on this traffic.** Claude Code already answers
   unchanged re-reads with a short message, and the M1 rule keeps those from superseding (160
   tiny `Read` results). The pruner also rewrites cached history (H05).

**Consequence for P2:** the order of the sub-slices follows the data:
- S8a-1: `search_group` and `log_filter`, with the P3 opt-in for `Bash`;
- S8a-2: `diff_context_trim` and `dictionary`;
- S8a-3: `analyze.tool_resources` and `superseded_tool_results`, with E2-ext.

The decision belongs to the human (P8).
