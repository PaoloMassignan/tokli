# S8c — Spec review: pruning old history when the cache is rewritten anyway

Status: **approved 2026-10-04 (Human Gate 1).**

## Why

Measured on the developer's Claude Code sessions (TOKLI_EVIDENCE.md §2, E5b-lite):
- 92 % of the cost is the cache: 64 % reads and 27.5 % writes.
- 76 % of the cache writes, about a fifth of all cost, follow a pause of more than an hour, when
  the whole context is written again.
- The built lossless compressors save well under 1 % of cost.

A simulation pruned old history only at those rewrites, and kept it pruned afterwards:
- **old `Write`/`Edit` arguments:** 5.9 % of total cost;
- **every old tool result above 500 tokens as well:** 10.5 %.

This is the first lever measured at more than a few per cent.

## Proposed behaviour (level A first)

When a request continues a conversation whose previous request is more than
`pruning.resume_after_s` old (default 3,600 s), Tokli treats the provider cache as expired:
1. In that request, the arguments of `Write`, `Edit` and `MultiEdit` calls older than
   `pruning.resume_min_age_turns` human turns (default 4) are replaced by a short stub. The stub
   keeps `file_path`, and the replaced strings become
   `[tokli: <n> tokens of earlier edit content omitted — read the file for its current state]`.
2. Every later request of the conversation applies the same replacements, so the provider cache
   stays valid until the next pause.
3. The request records `history_rewritten: true` and the number of pruned calls.

Levels B (superseded reads) and C (old tool results) would follow only after level A is
measured.

## Requirements this would change (each needs a spec change at Gate 1)

| Where | Today | Change needed |
|---|---|---|
| SPEC 009 CC-006 | "No compressor SHALL depend on time, randomness, locale or host"; segment output depends only on the request | A request-scope pruner may depend on the **conversation's previous request time**, kept in Tokli's memory |
| SPEC 019 PR-005 | Pruners "SHALL NOT modify tool-call arguments in v1" | Allow replacing string values of the arguments of `Write`/`Edit`/`MultiEdit`, keeping keys and `file_path` |
| SPEC 001 (canonical model) | Tool-call arguments are read-only | A new mutable segment kind for selected argument strings |
| SPEC 003 adapter | Renders text segments only | Render patched argument strings in `tool_use.input` |
| TOKLI_SCOPE / non-goals | "Removing whole tool calls or shortening their arguments": not in v1 (E10 first) | Move to v1 for this pruner, after E10(a) |
| SPEC 013 | `history_rewritten` exists | Add a count of calls pruned at resume |

## Open questions found

1. **Conversation identity.** Tokli has to recognise that two requests belong to the same
   conversation.
   - **Option 1:** a hash of the conversation's first messages. It is deterministic and needs no
     header.
   - **Option 2:** a session header, if the client sends one; only its name is recorded today.

   **Proposed:** option 1.
2. **State.** The pruned call ids and the last request time per conversation live in memory.
   - After a restart the state is gone. The next request after a long pause becomes a new
     resume; one within the hour would un-prune and cost one extra cache write.
   - **Proposed:** memory only, plus a bounded store of conversation states. The persistence
     question is decided with data.
3. **A wrong guess costs money.** If the cache is still warm when Tokli prunes, the request pays a
   full cache write.
   - The data show rewrites almost only after an hour (394 of 579). One hour is therefore a safe
     default.
   - The figure is measured with exact usage (`cache_creation_input_tokens`) and shown on the
     dashboard.
4. **Model behaviour.** After pruning, the model no longer sees what it wrote. It must re-read the
   file when it needs the content. Extra reads cost tokens and turns, and the simulation does not
   include them.
   - **Proposed:** a smoke family `reread_after_pruned_edit`. A question about a file written
     long ago must be answered by reading the file, not from memory. This needs a new checker
     that accepts a correct answer or a `Read` call for the right file.
   - Tier 3 (S8b) gives the real answer.
5. **E10(a): does the API accept edited history?** The provider might reject a history whose
   `Write`/`Edit` arguments were changed.
   - The stubbed values remain strings, so the schema holds.
   - **Proposed:** a few real calls before code, run by the human (low cost).
6. **Interaction with Claude Code's own compaction.** After a compaction there is nothing old to
   prune. The two do not conflict, and the saving is measured on top of it.

## Product questions → for the human

1. **P1** — Add S8c (pruning at resume, level A) to the roadmap, before S8a-2/S8a-3?
   **Recommended: yes.** S8a-2 and S8a-3 stay in the roadmap with their measured value
   (diffs 0.4 %, superseded reads 1.7 %).
2. **P2** — Accept the spec changes in the table above in principle, so that the exact EARS text
   is written for Gate 1 approval? **Recommended: yes.**
3. **P3** — Run E10(a) first (a few calls with your key, under a dollar), before writing code?
   **Recommended: yes.**
4. **P4** — Defaults: `resume_after_s` = 3,600, `resume_min_age_turns` = 4, off by default
   (SELECTIVE). **Recommended: yes.**

### Answers (2026-10-04)

The human: "Accetto". P1…P4 are accepted as recommended:
- S8c is in the roadmap, before S8a-2;
- the spec changes are accepted in principle;
- E10(a) runs first;
- the defaults are 3,600 s, 4 turns, off.

## Spec delta (written for Gate 1; status lines read "pending S8c Gate 1")

| File | Change |
|---|---|
| SPEC 019 | New section `edit_args_on_resume`: conversation state, resume, human turn, stub, claims. PR-005 amended. New PR-020…PR-026 and AC-PR-11…AC-PR-16, with test names. |
| SPEC 009 | CC-006: a request-scope pruner may depend on the conversation state, received read-only from the engine. |
| SPEC 001 | CM-009 and the data model: selected argument strings become `TOOL_CALL_ARGS` segments, changeable only by pruners that declare them. |
| SPEC 003 | Segment mapping: the `tool_use.input` row. |
| SPEC 010 | Catalogue row and the assumption `edit_content_not_needed`. |
| SPEC 012 | Family `reread_after_pruned_edit`; checker `answer_or_read`, which accepts the right value or a `Read` of the right file. |
| SPEC 017 | "Keys added in S8c": six keys. |
| TOKLI_SCOPE | The pruner is in scope; its conversation state is operational, not a memory or a knowledge model; argument stubbing stays a non-goal otherwise. |
| TOKLI_ROADMAP | S8c entry. |
| ADR 0012 | Conversation state and argument pruning (proposed). |

PR-016 is not used here: it is kept for the superseded-read rule of S8a-3 (S8a review M1).

## E10(a), ready to run (before any code)

- **Script:** `evals/experiments/e10a_api_acceptance.py`.
- **Calls:** 4 short ones: two variants (original and stubbed history), two repetitions each.
  They show whether the provider accepts the stubbed history and whether the model re-reads the
  file or answers from memory.
- **Helper for the human:** `C:\temp\tokli-live-test\e10a.cmd` (outside the repository). The key
  is typed there and cleared.
- **Results** are recorded in TOKLI_EVIDENCE §2 and decide whether S8c goes on.

**Result (2026-10-04):**
- the provider accepted the stubbed history (HTTP 200, 2 of 2);
- the model then read the file instead of answering from memory (2 of 2);
- with the original history it answered correctly from memory.

The details are in TOKLI_EVIDENCE §2. **E10(a) supports going on.**

## New product question (found while writing the delta)

5. **P5 — A conversation Tokli has never seen: resume or not?**
   - **Why it matters:** after Tokli restarts, the state is gone.
   - **Treating it as a resume** (recommended) prunes the old edits at once. If the provider cache
     was still warm, that costs one extra cache write.
   - **Not treating it as a resume** never costs extra. But the next pause of an hour is then the
     first chance, and a conversation resumed after Tokli restarted is not pruned until then.
   - Restarts usually coincide with long pauses (reboots, a new day), so the warm-cache case should
     be rare. **Recommended: resume.**

Gate 1 record: **approved 2026-10-04**, the human's words: "Approvo" (answering the request to
approve S8c and ADR 0012, and to answer P5). P5 is recorded as the recommended answer (an
unknown conversation is a resume), which is the text of the approved AC-PR-13; the human was
told so and may still change it. Spec delta: see the table above. ADR 0012 accepted.
