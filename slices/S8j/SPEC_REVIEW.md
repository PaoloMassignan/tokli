# S8j — Spec review: a skeleton at the first read of a code file (optional)

Status: **Gate 1 passed (2026-10-22).** S8i awaits its Gate 2, after its SCR-003.

**History of the request:**
- **2026-10-17:** "I would rather have this summary behaviour, and have it optional. Go
  ahead" (translated from Italian). A first draft outlined old reads at a resume. P1…P8 were answered ("ok to the
  recommendations" (translated from Italian)).
- **2026-10-22, the request was redefined:** "I want the strategy that, when a new file is
  requested, say code for now, sends only the skeleton at first, and the whole copy only if it is
  asked for again for an edit" (translated from Italian). Claude proposed A–D below, and the human answered "I
  confirm everything" (translated from Italian).
- **The human's decision:** the behaviour exists although E10(f) did not promote it, optional and
  off by default. This is recorded as a product decision, as for `edit_args_on_resume`.

**Slice scope.**
- **A new request-scope pruner, `outline_first_read`:** the first whole read of a code file in a
  conversation, through `Read`, `Bash` or `PowerShell`, is forwarded as its skeleton. Every later
  read of the same file is forwarded whole. It is SELECTIVE, prefix-stable and off by default.
- **The response's `stop_reason` in telemetry,** so that refusals in real use become visible.

**Specs in scope:**
- SPEC 019: PR-040…PR-046, "Shell file reads (Claude Code)", AC-PR-27…AC-PR-33;
- SPEC 009: CC-021 (c) (SCR-001);
- SPEC 010: the catalogue row and `outline_suffices_until_reread`;
- SPEC 017: "Keys added in S8j";
- SPEC 003: AN-012, AC-AN-8;
- SPEC 013: TC-022, AC-TC-18;
- TOKLI_TELEMETRY_AND_COST §2;
- ADR 0015 (schema v5).

**Explicitly out of scope:**
- Markdown and other non-code files;
- partial reads (`offset`/`limit`, `sed -n`, `head`, `tail`);
- outlines at a resume (the first draft);
- summaries written by a model;
- the stub of long shell commands;
- refusal aggregates in the API or the dashboard.

## 0. Evidence (TOKLI_EVIDENCE §2, counters only)

- **Value.** Whole reads of code files through the shell are about 72k tokens a week on the
  developer's traffic, 5.5 % of shell file reads.
- **An upper bound,** if the agent never read such a file again: about $3 a week at list prices.
- **The break-even point:** the saving turns negative when the agent reads more than about 75 %
  of the skeletons again. 70 % of shell-read volume concerns files that are read again anyway.
- **E10(f), skeleton of a Python module, on `claude-opus-5-5`:**
  - on questions it drew 11 refusals in 30 calls, against 5 for the original;
  - on the edit task it drew none, and the agent read the file again in 10 of 10 calls;
  - in no call was there a wrong answer, a bad edit or a blind write.
- **Real refusals cannot be measured today:** the telemetry has no `stop_reason`.

## 1. Ambiguities

- **A1. "File nuovo" (a new file).** No earlier tool record of the request reads, writes or edits
  it. A file the agent wrote itself is therefore never outlined. Two paths match when their
  normalised forms are equal or one ends with the other at a `/` boundary, which errs towards
  "seen".
- **A2. "Only if asked for again for an edit" (translated from Italian).** Tokli cannot see why the agent reads again. Every later read of the file is whole,
  whatever the reason.
- **A3. Which reads.** Whole reads only (answer B): `Read` without `offset`/`limit`, `cat`,
  `type`, `Get-Content` without range options, `cat -n`, `nl`, and one leading `cd <dir> &&`.

## 2. Contradictions

- **C1. TOKLI_EVIDENCE says** the skeleton "is not viable in this form". The compressor's
  documentation says "damage detected; do not switch it on", with the numbers. It exists by the
  human's decision.
- **C2. CC-021: `Read`, `Bash` and `PowerShell` are verbatim tools.** Resolved by SCR-001 (c),
  one switch (answer P3).

## 3. Missing behaviour

- **Later reference stubs.** A later identical read (`duplicate_tool_results`) or a re-read after
  an edit (`reread_by_reference`) would name the outlined first read as target or source. CC-019
  already decides this case: the earlier segment's change wins, and the stub is not forwarded. So
  the later read goes whole, as the human asked. AC-PR-31 makes this explicit.
- **The stop reason** of a response: AN-012 and TC-022, schema v5.

## 4. Portability concerns

- Line handling must be CRLF-aware, with UTF-8 only and no filesystem access.
- The rules are regular expressions; no new dependency.

## 5. Observability requirements for this slice

- **Reason codes,** within `not_applicable(<code>)` of TOKLI_OBSERVABILITY §4: `not_file_read`,
  `partial_read`, `error_result`, `no_outline_rule`, `below_min_tokens`, `seen_before`,
  `no_omission`.
- **Telemetry:** the `stop_reason` column (schema v5) and the per-compressor statistics as for
  every compressor.
- TOKLI_OBSERVABILITY §8 checklist at Verify, including the new telemetry field in the schema,
  the API contract and the retention job.

## 6. Architectural risks

- **`CompressorSpec.target_tools`** is read by the engine's verbatim filter (SCR-001).
- **The outline rules** are config data keyed by extension (`pruning.outline_rules`). They live
  in one concrete module, with no new seam.
- **The Claude Code shell-read classifier** extends the existing table.
- **Schema v5** follows the forward migration of ADR 0005 (ADR 0015).
- **No conversation state:** the pruner is prefix-stable.

## 7. Product questions → answered

1. **P1, tools:** `Read`, `Bash` and `PowerShell` (answered 2026-10-17).
2. **P2, shell reads:** the Claude Code rules, narrowed to whole reads by B.
3. **P3:** one switch, CC-021 (c).
4. **P4, the outline:** the E10(f) forms, code only by C. That is the first 8 lines, the
   declarations and the unindented lines, with each omitted run of at least 3 lines becoming a
   note.
5. **P5:** at least 500 tokens; never errors. The per-file age no longer applies, being replaced
   by "seen before".
6. **P6:** the conversation key is fixed in S8i (S8i SCR-003). It is not needed by this pruner.
7. **P7:** the stub of long shell commands in a later slice.
8. **P8, replay:** today's replay suffices. The pruner is prefix-stable and needs no timeline,
   because each context's last state decides every read exactly as it was decided at its first
   send. `tools.replay --timeline` is no longer in this slice.
9. **A (2026-10-22):** at the first send, replacing the resume variant.
10. **B:** whole reads only.
11. **C:** code only for now.
12. **D:** the response's `stop_reason` recorded in telemetry.

## 8. Implementation decisions → decided by Claude (recorded, not asked)

- **The pruner:** `outline_first_read`, SELECTIVE, request scope, `prefix_stable: true`, off by
  default. It runs in the `structural` stage before the segment-level compressors (PR-010).
- **Its decision for segment j** reads only segment j and the tool records before it (PR-045).
  The same text and the same earlier records give the same outline, so the result cache applies.
- **Protected spans** stay verbatim and in order. `Read` numbering is kept on the lines that are
  kept.
- **`stop_reason`** is read by the existing usage parsers, from the same passive copy and within
  the same memory bound (AN-009).
- **The registry rejects `target_tools`** on a LOSSLESS or default-on compressor (SCR-001).

## 9. Test plan (req/AC → tests)

| Requirement / AC | Tests |
|---|---|
| PR-040, AC-PR-27 | `test_outline_off_by_default_and_declared`, `test_lossless_only_switches_outline_off` |
| PR-041, AC-PR-27 | `test_outline_candidates_and_reasons` |
| PR-042, AC-PR-28 | `test_outline_only_first_read_of_a_file` |
| PR-043, PR-044, AC-PR-29 | `test_outline_python_keeps_declarations_and_head`, `test_outline_c_family`, `test_outline_note_format_and_numbering`, `test_outline_crlf`, `test_outline_keeps_protected_spans` |
| PR-045, PR-046, AC-PR-30 | `test_outline_prefix_stable_across_turns`, `test_outline_preserves_structure` |
| CC-019, AC-PR-31 | `test_outline_later_references_forward_whole` |
| CC-021 (c), AC-PR-32 | `test_outline_applies_to_declared_verbatim_tools`, `test_target_tools_require_selective_off_by_default` |
| Shell rules, AC-PR-33 | `test_claude_code_shell_read_rules` |
| End to end | `test_outline_first_read_end_to_end` |
| AN-012, AC-AN-8 | `test_anthropic_stop_reason_non_stream`, `test_anthropic_stop_reason_stream`, plus the any-split property of the stream parser |
| TC-022, AC-TC-18 | `test_stop_reason_persisted_and_in_api`, `test_migration_v4_to_v5` |
| Replay | `tools.replay` counters with the human's consent: considered, applicable, accepted, skip reasons |

Gate 1 record:
- **Date:** 2026-10-22.
- **The human's words:** "they are fine, but I do not want Italian comments in the
  specifications" (translated from Italian), in answer to the request to approve S8i SCR-003 and S8j.
- **Condition applied:** every Italian quotation in the S8i and S8j documents and in the roadmap
  was replaced by an English translation, marked as such. `specs/` and `docs/` held none.
- **Spec delta:** SCR-001, S8i SCR-003 and the `git diff` listed in §7 and in the scope above. The
  status lines now read "approved for S8j 2026-10-22"; ADR 0015 is accepted.
