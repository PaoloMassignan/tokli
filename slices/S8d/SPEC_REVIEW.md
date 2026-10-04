# S8d — Spec review: pruning old tool results when the cache is rewritten anyway

Status: **stopped 2026-10-04 by its own decision rule (E10(d) failed).** No code was written. The slice is not yet in
`TOKLI_ROADMAP.md`. The human asked for it on 2026-10-04 ("Vai con i vecchi risultati").

## Why

- **The S8c lever,** pruning only at the moments when the provider cache is rewritten anyway, is
  sound (TOKLI_EVIDENCE §2).
- **Its first form failed:** every edit of the assistant's own tool-call arguments raised provider
  refusals (S8c smoke run, E10(c)).
- **Tool results are user-side content:** replacing them drew no refusal in 132 calls (E11,
  `duplicate_tool_results`).

**Simulation on the human's sessions** (counters only, 2026-10-04): results older than 4 human
turns and above 500 tokens, pruned at resumes after more than an hour, and kept pruned afterwards.

| Results pruned | K = 4 | K = 10 |
|---|---|---|
| Read-like tools only (`Read`, `Grep`, `Glob`) | 2.3 % of total cost | 1.7 % |
| + `Bash` | 4.2 % | 3.1 % |
| All tools | 4.6 % | 3.3 % |

## Proposed behaviour

A new pruner, `results_on_resume`: SELECTIVE, request scope, `prefix_stable: false`, off by
default.
- **At a resume** (the S8c rule: the conversation was last seen more than
  `pruning.resume_after_s` ago, or is unknown), it replaces the content of every tool result that
  meets all of these:
  - its tool is in `pruning.resume_result_tools`;
  - it is followed by at least `resume_min_age_turns` human turns;
  - it is at least `pruning.resume_result_min_tokens` tokens;
  - it is not an error.
- **The stub keeps every protected span** (`<system-reminder>`) of the replaced text, as PR-015
  does.
- **Between resumes,** the same results are re-applied (PR-023). The result stays in place; only
  its content changes, as in SPEC 019.
- **A result that is the target of a duplicate stub is not pruned:** reference integrity (CC-019)
  already rejects it with `reference_target_modified`.

## Reuse and changes

- **Reused from S8c:**
  - the conversation key and store (ADR 0012);
  - the resume rule;
  - `history_rewritten`;
  - the `answer_or_read` checker.
- **Implementation:**
  - The store keeps the pruned call ids **per pruner** (today one set, for `edit_args_on_resume`).
    ADR 0012 gets an amendment.
  - The resume rule moves into one shared helper, which two pruners now justify (CLAUDE.md §5).
- **Spec delta to be written for Gate 1:**
  - SPEC 019: a new section, PR-027 onwards, and acceptance criteria;
  - SPEC 010: a catalogue row and the assumption `old_results_not_needed`;
  - SPEC 012: the family `reread_after_pruned_result`;
  - SPEC 017: keys;
  - the roadmap entry.
- **No change** to CC-006 (already covers request-scope conversation state), CM-009 (tool results
  are already mutable) or PR-005 (only result content changes).

## Hazards specific to results

1. **Re-running commands.** To see an old `Bash` output again, the model must run the command
   again. A command can have side effects (a write, a deployment, a migration). Reads are
   idempotent. This is product question P1.
2. **Refusals.** Not seen for result stubs so far, but E11 tested duplicate stubs, not this stub,
   and the S8c lesson is that 2 calls hide the risk. E10(d) checks it **before any code**, with 20
   calls per variant.
3. **Overlap with `duplicate_tool_results`:**
   - a later duplicate of a pruned result has no earlier copy left, so it is not stubbed;
   - an earlier result targeted by a duplicate stub is not pruned (CC-019).

   The interaction is safe by construction.

## E10(d) — refusals with tool-result stubs (before code)

**Script:** `evals/experiments/e10d_result_stubs.py`.
- **The conversation** (synthetic): the agent reads `<file>` with `Read`, has five unrelated
  exchanges, and is asked for a value from the file.
- **Four forms of the old `Read` result:**
  - `original` (control);
  - `descriptive`: `[tokli: earlier tool output omitted (<n> tokens)]`;
  - `hint`: `… omitted (<n> tokens) — read the file again if you need it]`;
  - `empty`.
- **Size:** 10 cases × 2 repetitions × 4 forms = 80 calls, with the `answer_or_read` outcome and
  the `stop_reason`.
- **Helper for the human:** `C:\\temp\\tokli-live-test\\e10d.cmd`.

**Decision rule:**
- **Go:** a form has no more refusals than the control (within 1 of 20), and no wrong answers.
- **Otherwise stop,** and S8d records the result.

## Product questions → for the human

1. **P1 — Which tools by default?**
   - (a) **read-like only** (`Read`, `Grep`, `Glob`): 2.3 %, nothing to re-run. **Recommended.**
   - (b) read-like plus `Bash`: 4.2 %, but the model may re-run commands with side effects.

   `Bash` could become a separate opt-in after a dedicated evaluation.
2. **P2 — The stub text:** the form that wins E10(d). If several tie, the shortest.
3. **P3 — Thresholds:** `resume_min_age_turns` shared with S8c (4); `resume_result_min_tokens`
   = 500. **Recommended: yes.**
4. **P4 — Run E10(d) first** (80 calls, a few dollars at most). **Recommended: yes.**

## E10(d) result (2026-10-04): stop

| Form of the old `Read` result (20 calls each) | Correct | Refused |
|---|---|---|
| Original (control) | 20 | 0 |
| `[tokli: earlier tool output omitted (<n> tokens)]` | 7 | 13 |
| The same + "— read the file again if you need it" | 7 | 13 |
| Empty string | 4 | 16 |

**Decision rule:**
- No form stays within one refusal of the control, so S8d stops here, as agreed before the run.
- P1…P4 are moot.
- The result is in TOKLI_EVIDENCE §2.

Gate 1 record: not reached; the slice stopped at its pre-code experiment.

