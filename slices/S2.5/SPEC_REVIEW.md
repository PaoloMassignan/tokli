# S2.5 — Spec review

Slice: **S2.5 — Minimal evaluation skeleton (smoke tier)** (`TOKLI_ROADMAP.md`).
Status: **Human Gate 1 passed 2026-10-03.** Implementation in progress.

## Scope

**Roadmap content.**
- `tokli eval smoke` (QE-012…QE-017): a baseline arm and a candidate arm with the same
  model, prompt and parameters; deterministic checkers; config hashes recorded; token saving and
  outcome recorded; manual only, with cost confirmation and caps (QE-009…QE-011).
- Case and record formats shared with S8. First case families: `json_fact_lookup` and
  `json_verbatim_quote`.
- Contract test CC-020: a default-enabled compressor needs an evaluation record.
- Not built: generators, bootstrap CIs, multi-provider runs, Tier 3, dashboards for eval results.

Exit: the harness self-test is green in CI (QE-017), and `json_minify` has a real smoke record
that replaces its `provisional` one. If the verdict is `damage_detected`, `json_minify` becomes
default-off and the result is recorded.

**Requirements in scope (proposed):**

| Spec | In S2.5 | Deferred (slice) |
|---|---|---|
| 012 evaluation | QE-001, QE-004, QE-005, QE-007, QE-009…QE-011 (as read in P2), QE-012…QE-017; families `json_fact_lookup`, `json_verbatim_quote` | QE-002, QE-003, QE-006, QE-008 and bootstrap CIs (S8); `reference_*` families (S4) |
| 009 compression core | CC-020 without the `provisional` exception once S2.5 exits | — |
| 014 observability | Eval runs never touch the proxy path (QE-011): no trace, no telemetry rows | — |

## 1. Ambiguities

| Id | Requirement | Question | Proposed reading |
|---|---|---|---|
| A1 | QE-012 | The candidate arm runs under "policy LOSSY_ALLOWED", but policy switching exists only from S4 (the policy is fixed to LOSSLESS_ONLY). | Both arms use the fixed LOSSLESS_ONLY policy in S2.5. The only compressor to evaluate is LOSSLESS, so eligibility cannot interfere. LOSSY_ALLOWED applies from S4. |
| A2 | QE-001, QE-012 | What is "the real pipeline" for the harness? | The harness builds two in-process service sets (baseline: every compressor disabled; candidate: only `<id>` enabled) with the same bootstrap as `tokli serve`. Each case runs through `parse → pipeline → render` and is sent with the upstream client of the proxy. No HTTP server, no telemetry rows. |
| A3 | QE-012 | `json_minify` never touches `Read`/`Bash` results (verbatim tools) or results under 64 tokens. | Cases use a non-verbatim tool name and results well above the threshold. A case whose candidate body equals its baseline body is reported as `not_exercised` and does not count towards n. |
| A4 | QE-014 | Where do the forwarded input tokens come from? | Requests are sent with `stream: false`; usage is read from the response body (the S2 parser). Without usage, the local estimate is used and labelled. |
| A5 | QE-015 | What exactly is a "pass"? | The checker of the case's family: `exact_value` compares the model's final answer line with the expected value after trimming whitespace and surrounding quotes or backticks. `json_structural` parses the first JSON value in the answer and compares it with the expected value (key order and whitespace ignored). An answer that cannot be parsed is a `fail`; an API error or refusal is an `error`. |
| A6 | QE-005, QE-016 | Where do results live? | `evals/results/<date>-<compressor>-<model>/`, with `report.md` (summary) and `cases.jsonl` (per case and repetition: outcome, tokens and the raw model answer to the synthetic task). `.gitignore` excludes `cases.jsonl`; the report is committed; the record's `report` field points to it. See P4. |

## 2. Contradictions

| Id | Where | Contradiction | Proposed resolution |
|---|---|---|---|
| X1 | QE-009, QE-010 (estimated cost from the price book; `--max-cost`) vs. the roadmap (price book in S6) | No prices exist in S2.5, so neither a cost estimate in money nor `--max-cost` can work. | QE-011 already covers it: without pricing, `--max-calls` is required. In S2.5 every run therefore needs `--max-calls N`. The plan shows the number of calls and the estimated input tokens before running. `--max-cost` arrives with S6. See P2. |
| X2 | Proxy credential rule (passthrough only; inherited provider env ignored, `test_inherited_provider_env_is_ignored_unless_configured`) vs. an eval that must call the provider itself | The harness has no client to pass credentials through. | The key is read only from an environment variable named explicitly on the command line (`--api-key-env NAME`), never from config files, never logged, never written to results. See P3. |

## 3. Missing behaviour

- **M1. The case files' format.** QE-013 lists the content but not the layout. Proposed: one YAML
  file per case, `evals/cases/<family>/<nn>.yaml`, with these fields:
  - `case_set` (version);
  - `family`;
  - `assumption`;
  - `checker`;
  - `request` (a Messages body without `model`, which comes from `--model`);
  - `expected`.

  The family's `README.md` describes the task.
- **M2. Case authoring.** Generators are out of scope. The 2 × 20+ cases are synthetic files,
  produced once by a small committed script (`evals/make_cases.py`) and reviewed in the pull
  request. The script is not part of the package.
- **M3. Applying a `damage_detected` verdict.** The roadmap decides it (`json_minify` becomes
  default-off). The config default and the registry flag change in the same commit as the
  record, and the change is shown at Gate 2.

## 4. Portability concerns

- **Checkers and verdicts** are pure functions of text and are tested on all CI OSes.
- **The interactive confirmation** reads stdin; with `--max-calls` and `--yes` no prompt is
  needed, so CI and Windows terminals behave the same.
- **Result files** are written in UTF-8 with LF line endings.

## 5. Observability requirements for this slice

- An eval run writes no proxy telemetry and no traces (QE-011: never on the proxy path). Its
  provenance goes into the report (QE-005, QE-014).
- **Credential scan:** a test runs a fake eval with a canary key and checks that it appears in no
  output, report or results file.
- **New reason or outcome codes:** `pass`, `fail`, `error`, `not_exercised` (results only, not the
  proxy's closed set).

## 6. Architectural risks

- **R1. New package `tokli.eval`.** It sits above `tokli.app` (it uses bootstrap and the
  protocol adapter) and below `tokli.cli`. New import contract: `tokli.http` may not import
  `tokli.eval` (AC-QE-4). ADR 0008 records the package, its layering and the credential rule (X2).
- **R2. Paid calls.** Only the product owner runs a real eval (CLAUDE.md §3). Every test uses a
  fake upstream.
- **Seams introduced:** a checker registry (two concrete checkers, more in S4). This is justified
  by two behaviours now. No other plugin points.

## 7. Product questions (for the human)

| # | Question | Recommendation |
|---|---|---|
| **P1** | **Model for the real smoke run.** Q19 says "the Claude model used for dogfood": your Claude Code traffic uses `claude-opus-5-5`. A cheaper model (Haiku) is less representative. The run has 2 families × 20 cases × 3 repetitions × 2 arms = **240 calls**, with small requests (about 1–3k input tokens each). | The dogfood model, `claude-opus-5-5`, as decided in Q19. |
| **P2** | **Cost control without a price book (X1):** `--max-calls N` is mandatory in S2.5. Before running, Tokli shows the plan (cases, repetitions, arms, calls, estimated input tokens). `--yes` skips the prompt. `--max-cost` arrives in S6. | Yes. |
| **P3** | **API key for the eval (X2):** read only from the environment variable named by `--api-key-env` (e.g. `ANTHROPIC_API_KEY`), API key only (a Pro/Max login cannot be used outside Claude Code). It is never stored, logged or shown. | Yes. |
| **P4** | **Results in git (A6):** commit the summary report (`report.md`) and the updated record; do not commit `cases.jsonl` with the raw model answers (synthetic tasks, but noise in the repository). | Yes. |
| **P5** | **Who runs the real eval:** you, with a helper script like the one in S2 that asks for the key in the terminal (the key never enters a chat). It costs a few dollars on Opus (estimate shown before running). | Yes. |
| **P6** | **Scope readings** (table above, A1–A6, X1–X2, M1–M3). | Accept as proposed. |

## 8. Implementation decisions (decided by Claude, recorded)

- **I1.** `tokli.eval` holds four parts:
  - `cases` (loading and lint);
  - `checkers` (`exact_value`, `json_structural`);
  - `runner` (arms, repetitions, call cap, usage);
  - `verdict` (QE-015) and `record` (YAML record, report).

  The CLI adds `tokli eval smoke`.
- **I2.** The model output is read from the non-streaming response's `content[*].text`, joined.
- **I3.** The runner stops before the call that would exceed `--max-calls`. The cases not
  completed are left out of n, so the verdict becomes `insufficient_data` when n < 20 (QE-007,
  QE-010).
- **I4.** The self-test (QE-017) runs the real runner against a fake upstream that answers with
  the expected value when the request body contains it in a recognisable form, and wrongly when
  it does not. A destructive fake compressor (it drops every digit) therefore yields
  `damage_detected`, and the identity compressor `no_measurable_damage`.
- **I5.** Once S2.5 exits, the CC-020 contract test rejects `provisional` records for every
  compressor, `json_minify` included (QE-016).

## 9. Test plan

| Requirement / AC | Tests |
|---|---|
| QE-001, A2 | `test_harness_uses_real_pipeline`, `test_smoke_arms_differ_only_in_candidate` |
| QE-004, A5 | `test_checker_exact_value`, `test_checker_json_structural` |
| QE-005, QE-014 | `test_harness_report_provenance` |
| QE-007, QE-015 / AC-QE-5 | `test_smoke_verdict_rule` (b = 2 → damage, b = 1 → no damage, errors rule), `test_smoke_insufficient_data` (19 cases) |
| QE-009…QE-011 / AC-QE-4, X1 | `test_eval_requires_max_calls_without_pricing`, `test_eval_stops_at_call_cap`, `test_eval_requires_confirmation_or_yes`, `test_eval_never_auto_starts` (import contract and no proxy path) |
| QE-012, A3 | `test_case_not_exercised_is_excluded` |
| QE-013 / AC-QE-6 | `test_eval_cases_lint` (assumption, checker, no canary paths or key prefixes; real case files pass) |
| QE-016 / AC-QE-7, I5 | `test_eval_record_schema_and_provisional_rule`, `test_eval_record_invalidated_by_version_bump`, `test_registry_default_enabled_requires_eval_record` (updated) |
| QE-017 | `test_smoke_harness_self_test` (identity → no damage, digit-dropper → damage) |
| P3 | `test_eval_api_key_from_named_env_only`, `test_eval_never_writes_the_key` |
| Exit | the product owner's real run (P5); its record and report committed |

Answers 2026-10-03: the product owner asked whether to do S2.5 now or after S4; Claude
recommended now (S4 needs the harness to default-enable the reference stub; the `provisional`
record must end). The answer: "No facciamo adesso. Accetto le tue proposte" — P1–P6 accepted.
Spec delta (uncommitted): SPEC 012 QE-012 (policy until S4, in-process real pipeline,
`not_exercised`), QE-013 (case file layout), QE-014 (outcomes, results layout and what is
committed), new QE-018 (`--max-calls`, plan, confirmation or `--yes`), QE-019 (API key from a named
environment variable only), QE-020 (the two checkers), AC-QE-8.

Gate 1 record: **approved 2026-10-03**, the human's words: "approvo s2.5". Spec status line set in
SPEC 012.
