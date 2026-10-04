# S8c — Completion report

Slice: **S8c — Pruning old edit content when the cache is rewritten anyway**. Branch
`s8c-prune-on-resume`.
- **Gate 1:** approved 2026-10-04 ("Approvo"), see `SPEC_REVIEW.md`. P5 is recorded as "an
  unknown conversation is a resume".
- **E10(a):** run by the human before code. The provider accepted the stubbed history, and the
  model then read the file instead of guessing (TOKLI_EVIDENCE §2).

## Requirements implemented

| Spec | Requirements |
|---|---|
| 019 | `edit_args_on_resume`: PR-020…PR-026, AC-PR-11…AC-PR-16; PR-005 and PR-009 as changed |
| 009 | CC-006 as changed (conversation state, read-only through the engine) |
| 001 / 003 | CM-009 as changed; the adapter exposes the strings listed in `pruning.resume_edit_fields` as `TOOL_CALL_ARGS` segments, **only while the pruner is on** |
| 012 | family `reread_after_pruned_edit` (22 cases, case set `2026-10-04.1`); checker `answer_or_read` (QE-020) |
| 017 | the six keys of "Keys added in S8c" |
| 013 | `history_rewritten` (TC-014) is now set: by a resume that newly prunes calls |
| ADR 0012 | conversation key, in-memory bounded store, resume rule, argument segments |

## How it works in the code

- **Proxy, after parse:**
  - it computes the conversation key (SHA-256 over `system` and the first message, about 0.3 ms
    for 100 KB) and reads the conversation's state;
  - it passes the state to the pipeline in `StageContext.conversation`;
  - after the request is built, it records the calls whose stubs the forwarded request
    **really** carries, which is none when the request is passed through. So the next request
    never re-applies stubs that the provider's cache does not contain.
- **The pruner** is a pure function of its inputs:
  - it receives the time since the conversation's last request and the stored call ids;
  - at a resume, it proposes stubs for calls followed by at least `resume_min_age_turns` human
    turns;
  - between resumes, it proposes exactly the stored calls.
- **The engine** passes `human_turns_after` with each tool record. The adapter counts human
  turns as SPEC 019 defines them: a message that only carries tool results, or mixes them with
  injected text, is not a human turn.
- **When the pruner is off:**
  - no argument segment is exposed, so every other compressor, the statistics and the estimates
    are unchanged;
  - the store still records the time of each request, so that switching the pruner on
    mid-conversation does not guess "resume" wrongly.

## Tests and evidence

- **Local** (Windows, CPython 3.11): `pytest tests` → **685 passed, 10 skipped**. Browser tests:
  14 passed. `ruff`, `mypy --strict` (74 files) and `lint-imports` (5 contracts) are clean.
- **CI:** run 37199624501 (commit c82097f): all 9 jobs green at the first attempt; cross-job identity check green.
- **RED first.** The modules first existed as skeletons (types, signatures, config keys with
  their defaults). Then:
  - 10 unit tests, the end-to-end resume test and 4 evaluation tests failed on behavioural
    assertions.
  - **Passed before the code, by design:** the two "off by default" tests (the key exists with
    `false`) and `test_pruned_history_is_accepted_shape` (nothing is pruned before the code).
  - **Made non-vacuous during RED:** `test_reread_cases_exercise_the_pruner`, which first passed
    because no case existed yet; an `assert cases` was added.
- **Tests changed because the spec changed:**
  - the config-loader key tables and the pinned default `config_hash`;
  - `test_keys_marked_ui_editable` (the new toggle);
  - `test_chain_order_by_stage_then_id` and `test_registry_lists_the_s8c_compressors`;
  - the doctor goldens, regenerated deliberately: the diff holds only the new keys, the new
    compressor and the hash;
  - the fake pruner in `test_eval.py`, which gained the `conversation` parameter.

  No assertion was weakened.
- **Traceability:** rows PR-020…PR-026, plus CM-009, AN-002, CC-006, PR-005, PR-009 and QE-020
  extended.

## Measured performance

- **The only addition on every request is the conversation key and one store lookup:**
  - the key takes about 0.3 ms for a 100 KB `system` plus first message;
  - the lookup is a dictionary access under a lock.
- **When the pruner is off,** parse, pipeline and render are unchanged, because no argument
  segment is exposed.
- **E9:** the benchmark times parse, pipeline and render only. It is not re-run, because the
  pipeline is unchanged when the pruner is off.

## Observability evidence (TOKLI_OBSERVABILITY §8)

- [x] **Each decision has a reason code** in the trace and the per-compressor statistics:
  `not_applicable(too_recent)`, `not_applicable(not_resume)` and
  `not_applicable(below_min_tokens)`.
- [x] **`history_rewritten`** is persisted and shown in the request view. It is true only at the
  resume that newly prunes calls.
- [x] **Content scans:** the stub holds only the template and a token count. File paths stay as
  the client sent them.
- [x] **Settings** shows the new compressor with "drops information" and its evaluation status.

## Exit criteria

1. **Tier 0 tests green:** yes.
2. **Smoke record, run by the human:** first run inconclusive, second run `damage_detected`
   through refusals (below). **Not met.**
3. **Dogfood week with the pruner on:** *not started*. The pruner must not be switched on
   until the refusals are understood. It compares, from exact provider usage, the
   cache writes and reads around resumes, and counts the extra re-reads.

## First smoke run (2026-10-04): inconclusive, because of the cases

- **Result:** `insufficient_data` (132 calls, case set `2026-10-04.1`). 17 of 22 cases were
  complete, with b = 2 and c = 3, so no sign of damage. 34 answers were `stop_reason: refusal`
  and 4 were empty, in **both** arms.
- **Cause, found in the per-case results** (synthetic answers, no prompt content):
  - The refusals concentrate in the cases that ask for a `*_LABEL` or `*_ENDPOINT` key. The
    generator gave those keys random numbers, so the cases held lines such as
    `LOGGING_ENDPOINT = 48213`.
  - Several answers were `Read` calls with empty arguments, consistent with the 200-token output
    limit cutting the call.
- **Fixes:**
  - The generator now gives realistic values per key kind (URLs, words, numbers) and
    `max_tokens: 1024` (case set `2026-10-04.2`).
  - The runner records each answer's `stop_reason` in `cases.jsonl`, so a refusal or a
    truncation can be told apart next time.
- **The report of this run** is committed as evidence (commit after c82097f). The second run
  replaces it in the same folder.

## Second smoke run (2026-10-04): `damage_detected`, through refusals

- **Run:** case set `2026-10-04.2`, 132 calls; n = 20, b = 4, c = 0. Errors: baseline 2 cases,
  candidate 6.
- **No wrong answer in either arm.** Every completed answer was a correct `Read` of the case's
  file (or, three times in the baseline, the right value).
- **All the damage is refusals** (`stop_reason: refusal`, empty content):

  | Arm | Refusals |
  |---|---|
  | Original history | 6 of 66 (9 %) |
  | Stubbed history | 17 of 66 (26 %) |

  In 3 cases the stubbed version was refused 3 times out of 3, while the original always passed.
- **Probable cause, not proven:** the stub places an imperative sentence ("read the file for its
  current state") inside a tool call that the assistant itself appears to have made. Edited
  assistant history that carries an instruction resembles prompt injection. The synthetic history
  alone already draws some refusals.
- **E10(a) did not show this** with 2 calls.
- **Consequence:** the pruner must not be used as it is. It stays off by default; its record says
  `damage_detected`, and the Settings page shows it.
- **Next:** an experiment on the stub's form (E10(c)) decides whether a different stub avoids the
  refusals. A change of the stub text needs an SCR on SPEC 019 and a new smoke run.

## E10(c): the stub's form does not matter (2026-10-04)

Run by the human, 80 calls (`evals/experiments/e10c_result.json`):

| Form of the old `Write` content (20 calls each) | Correct | Wrong | Refused |
|---|---|---|---|
| Original (control) | 16 | 2 | 2 |
| `[tokli: earlier edit content omitted (<n> tokens) — read the file for its current state]` | 12 | 0 | 8 |
| `[tokli: <n> tokens omitted]` | 9 | 0 | 11 |
| Empty string | 12 | 3 | 5 |

The hypothesis of the second run (the imperative sentence) is **refuted**: any change of the
assistant's own tool-call arguments raised the refusals, the descriptive stub most of all. The
pruner cannot be made safe by rewording, so no SCR on the stub text follows.

## Known limitations

- **After a Tokli restart** the first request of every conversation is treated as a resume (P5).
  If the provider cache was still warm, that request pays one extra cache write.
- **Only `Write`/`Edit`/`MultiEdit` arguments** are pruned (level A). Old tool results (level C,
  about 10 % in the simulation) are not; they would need their own decision.
- **The conversation key changes when the first message or the system prompt changes** (for
  example after Claude Code compacts). Tokli then sees a new conversation, which is correct,
  because the provider cache is rewritten anyway.

## Unresolved questions

1. **How to close S8c.**
   - **Option a (recommended):** accept it as delivered and evaluated. `edit_args_on_resume`
     stays available, off by default, documented as "damage detected — not recommended". The
     conversation state, the resume rule and the stable re-application stay; they are what a
     result-side pruner at resume needs.
   - **Option b:** remove the argument pruner and its argument segments, keeping only the
     conversation state.
2. **Next lever.** The simulation put old tool results at about 4–5 % of cost on top of the
   arguments (levels B/C). Tool-result stubs drew no refusal in E11. Recommendation: a slice
   for pruning old tool results at a resume, with a smoke family that watches refusals from the
   start.

Gate 2 record: **accepted 2026-10-04**, the human's words: "Accetto s8c".
- **Exit criteria:** the smoke and dogfood criteria were not met (damage detected). The
  acceptance is of the slice as delivered and evaluated.
- **Unresolved question 1:** option a, as recommended. The pruner stays available, off by
  default, "not recommended"; the conversation state stays.
- **The next lever** (old tool results at a resume) is not started; it begins only when the
  human asks.
- **Merge:** the branch is squash-merged into `main`.
