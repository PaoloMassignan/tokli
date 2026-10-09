# TOKLI — Roadmap (vertical slices)

Every slice follows the human-gated lifecycle in `CLAUDE.md §2`. It starts with a spec review and
**Gate 1** (spec approval, no code before it). It ends with tests written first and green, the
observability checklist done, traceability updated, the portability job green on
Windows/Linux/macOS, a completion report (`slices/S<n>/COMPLETION_REPORT.md`) and **Gate 2**
(explicit human acceptance). Nothing in a later slice is built early, and no slice starts
automatically after the previous one.

## S0 — Walking skeleton (no proxying yet)

- This repository (`source/claude/Tokli`) gets package `tokli`, `pyproject.toml` (ruff, mypy --strict, import-linter
  contracts from `TOKLI_ARCHITECTURE.md §5` for the modules that exist, extended as modules appear), CI on GitHub Actions (public repository `PaoloMassignan/tokli`): matrix {Windows, Ubuntu, macOS} × {3.11, 3.12, 3.13} on every push and pull request. Licence Apache-2.0.
- `tokli.config`: schema + precedence + effective config with sources (CF-001…CF-006).
- Data/config dir resolution (CF-008). `tokli setup tokenizers` (TM-010) and the tokenizer loader check (TM-006, TM-007). `tokens.*` schema only; per-request selection (TM-002) is S1.
- `tokli doctor` (text output: version, python, platform, paths, effective config, tokenizer status).
- Tests: config precedence, no import-time side effects, CWD independence, doctor snapshot.

Exit: the normalised `tokli doctor` snapshot (without paths, Python version, OS/arch and build metadata) is identical in all 9 CI jobs (AC-PT-7). Approved scope: `slices/S0/SPEC_REVIEW.md`.

## S1 — First useful slice: Anthropic Messages, passthrough auth, one lossless compressor

Scope, exactly:

| Aspect | S1 choice | Why |
|---|---|---|
| Provider / protocol / endpoint | Anthropic, `POST /anthropic/v1/messages` (streaming + non-streaming) | Claude Code is the primary user, and it always streams |
| Auth mode | **passthrough** (client headers forwarded unchanged) | Tokli stores no secret. Covers API-key auth now. OAuth rides along, but is labelled REQUIRES VERIFICATION until E1. |
| Canonical model | Segments for `messages[*]` user text + `tool_result` content (string and text blocks), with `tool_name` resolution; everything else opaque | minimum needed for tool outputs |
| Analyzers | `analyze.reminders` (protected spans) | Claude Code injects `<system-reminder>` into user turns |
| Compressor | `json_minify` (LOSSLESS, structural equivalence), default enabled **provisionally** (QE-016 `provisional` record, replaced in S2.5); `verbatim_tools` default list from SPEC 010 (for Anthropic traffic the relevant entries are `Read`, `Bash`) | cheap, provably lossless, deterministic |
| Policy | LOSSLESS_ONLY fixed (policy switching arrives in S4) | |
| Token measurement | estimate only (o200k proxy), labelled | provider usage arrives in S2 |
| Telemetry | `RequestRecord` + `CompressorStats` as structured log lines **and** SQLite (schema v1) | the persisted schema is stable before the UI |
| Observability | request ID header, trace ring buffer, `GET /tokli/api/requests/{id}` (JSON), decision reason codes | DoD |
| Performance | `ms_tokli_overhead` and stage timings recorded per request; benchmark E9 run once on each CI OS and its results committed as the first regression baseline | measure first (TOKLI_TEST_STRATEGY §8) |
| Other paths under `/anthropic/` | verbatim relay | `count_tokens`, `models` keep working |
| Tests | compat corpus (Anthropic subset), streaming tests, invariants, credential/content leak scans, portability job | |

Acceptance for S1 (all must hold):

1. With compression disabled, 100 % of Anthropic compat fixtures forward byte-identical bodies,
   and responses/streams arrive byte-identical and unbuffered.
2. With `json_minify` on, only pretty-printed JSON tool results from non-verbatim tools change.
   Every change round-trips (`json.loads` equality). Structure is otherwise identical.
3. A Claude Code session (E1a, API key) completes 3 scripted prompts through Tokli with no
   client-visible error. Trace and records show per-compressor figures. Then the same with a
   Pro/Max login (E1b); if E1b fails, it is recorded as a finding and S1 still closes on E1a.
4. No credential or canary content appears in logs or the DB.
5. The rendered output of the Anthropic compat and golden corpus is byte-identical in all 9 CI jobs
   (the property behind the S9 fingerprint; decision P3).
6. The overhead distribution (p50/p95/max per size bucket) from the E9 run and the E1a session is
   reported in the completion report against the Vision target. This is **reported, not gated**.

## S2 — Exact usage and honest numbers (Anthropic)

- Usage parsing: non-stream body + passive SSE tee (AN-005…AN-007, AN-009); categories mapping (TM-003).
- Calibration `k` (TM-004); methods on every figure (TM-005).
- E4 (Anthropic part) executed; results recorded in the spec. (E1 was executed in S1: API key and
  Pro/Max OAuth both supported, path prefix accepted.)
- Decided at S1 Gate 2 (2026-10-02): a deterministic cache of compressor results per text (repeated
  history becomes almost free; allowed by CC-006), request header **names** persisted in the request
  record, and an optional rotating log file in the data dir (TOKLI_OBSERVABILITY §6).
- Exit: trace shows exact forwarded usage and a calibrated saving for streamed Claude Code requests.
- **Accepted 2026-10-03** (`slices/S2/COMPLETION_REPORT.md`). E4 (Anthropic) done: SPEC 003 Q3.

## S3 — Metrics API + minimal dashboard

- `MetricsQuery` + `/tokli/api/metrics/summary|timeseries|compressors|requests` (API-001…API-004).
- Dashboard v0: totals (original, forwarded, saved, %), per-compressor table (§3 of
  `TOKLI_TELEMETRY_AND_COST.md`), recent requests (metadata), method labels.
- Exit: a developer can answer "how much, and which compressor" from the UI during dogfooding.
  E5 (b) dogfood starts here.
- **Accepted 2026-10-03** (`slices/S3/COMPLETION_REPORT.md`). Dogfood E5 (b) running.

## S2.5 — Minimal evaluation skeleton (smoke tier)

Why here: it depends only on the real pipeline (S1) and on provider usage plus cost tracking (S2).
It must exist before S4, the first slice that proposes a default-on compressor whose usefulness
depends on the model interpreting a Tokli notation (the reference stub). Building it before S4
also lets the harness validate itself on a low-risk compressor first.

- `tokli eval smoke` (QE-012…QE-017): baseline vs candidate arm, same model/prompt/params,
  deterministic checkers, config hashes recorded, token saving and outcome recorded, manual
  only, cost confirmation and caps (QE-009…QE-011).
- Case and record formats shared with S8 (QE-013, QE-016). First case families:
  `json_fact_lookup`, `json_verbatim_quote`.
- Contract test CC-020: default-enabled ⇒ evaluation record.
- Not built: generators, bootstrap CIs, multi-provider runs, Tier 3, dashboards for eval results.
- Exit: the harness self-test is green in CI (QE-017). `json_minify` has a real smoke record that
  replaces its `provisional` one. If the verdict is `damage_detected`, `json_minify` becomes
  default-off and the result is recorded.
- **Accepted 2026-10-03** (`slices/S2.5/COMPLETION_REPORT.md`): `json_minify` smoke record `no_measurable_damage` on `claude-opus-5-5`; stays default-enabled.

## S4 — Compressor registry, policy and configuration API

- Per-compressor enable as the only control, with the "Lossless only" shortcut (CC-002, CC-003; S4 SCR-001).
- `ConfigService` + `/tokli/api/config` with UI-override layer and locked-key reporting
  (CF-001, CF-009, API-005, API-006 Origin checks, API-007).
- UI toggles + policy switch; compressor cards from registry metadata.
- Second LOSSLESS compressor **`duplicate_tool_results`** (SPEC 019, request scope, reference
  equivalence, prefix-stable). It exercises request-scope compressors, `ToolRecord`s (CM-013),
  chaining before segment compressors, reference integrity (CC-019) and marginal attribution.
  Case families `reference_fact_lookup` and `reference_verbatim_quote` added. **Default enabled
  only if its smoke record says `no_measurable_damage` (E11)**. Otherwise it ships available but off.
- Exit: toggling a compressor in the UI changes the next request's `config_hash` and attribution.
  The dashboard shows pruning and text-compression savings separately.
- **Accepted 2026-10-03** (`slices/S4/COMPLETION_REPORT.md`): E11 `no_measurable_damage`; `duplicate_tool_results` on by default; SCR-001 (policy as a shortcut), SCR-002.

## S4.5 — Hardening of the accepted code

Why here: a code review after S4 found two defects and several refactorings. Fixing them before
S5 keeps the second provider from building on them.

- Fix two defects: concurrent configuration changes can lose an update (API-007), and telemetry
  column types are derived from column names (TC-012).
- The request transformation (parse, pipeline, render) leaves the event loop, so one large
  request never stalls the streams of others (PX-015, ADR 0011).
- Behaviour-preserving refactorings: one acceptance gate for both compression scopes, protocol
  types instead of `Any`, record building moved out of the HTTP layer.
- No new product behaviour beyond PX-015, no new compressor, no new provider.
- Exit: regression tests for both defects; PX-015 test green; all test categories green on the CI
  matrix; overhead (E9) re-measured and compared with the S4 baseline.
- **Accepted 2026-10-03** (`slices/S4.5/COMPLETION_REPORT.md`): D1–D3 as planned, D4 (store close under a busy writer) found by CI and fixed; E9 paired local run within 1.14× of S4.

## S8a — Claude-complete compressors (before S5)

Why here: the human asked to finish the Anthropic/Claude Code side before the second provider
(2026-10-03). E5b-lite (`slices/S8a/SPEC_REVIEW.md` §10) measured the human's recent Claude Code
traffic and set the order:
- grep-shaped and log-shaped output are about 6 % each of the tool-result volume, mostly from `Bash`;
- superseded reads are 1.7 %;
- diffs are 0.4 %.

Three sub-slices, each with its own gates:

- **S8a-1:**
  - `search_group` (LOSSLESS) and `log_filter` (SELECTIVE), both off by default;
  - the per-compressor opt-in `apply_to_verbatim_tools` (S8a SCR-001) and its Settings toggle (UI-012);
  - the features `grep_lines`, `leveled_ratio`, `line_count` and `crlf`;
  - the smoke families `grep_fact_lookup`, `grep_verbatim_quote`, `log_fact_lookup` and
    `log_verbatim_quote`.

  Exit: Tier 0 tests green, smoke records for both compressors run by the human, savings measured
  on dogfood.
  **Accepted 2026-10-04** (`slices/S8a/COMPLETION_REPORT_S8a-1.md`):
  - both smoke records are `no_measurable_damage`;
  - the real saving is about 1.3 % of the tool-result volume with the opt-in;
  - SCR-001, SCR-002, SCR-003;
  - `search_group` stays off by default.
- **S8a-2:** `diff_context_trim` (SELECTIVE) and `dictionary` (LOSSLESS) with their families; E7
  as a smoke evaluation on Claude models.
- **S8a-3:**
  - `analyze.tool_resources` (Claude Code tools only);
  - `superseded_tool_results` with the rule that a weak view never supersedes (review M1);
  - `history_rewritten` and the cache marker (CC-018);
  - E2-ext measured in tokens (exact usage); money comes in S6.

Not in S8a: the arguments of `Edit`/`Write`, the largest resent item in E5b-lite. That is E10,
a candidate for its own spec after S8a.

## S8c — Pruning old edit content when the cache is rewritten anyway (before S8a-2)

Why here: the S8a measurements showed that most of the cost is the provider cache, and that
three quarters of the cache writes follow pauses of more than an hour (TOKLI_EVIDENCE §2). An
offline simulation estimated about 6 % of total cost for pruning old `Write`/`Edit` arguments
only at those moments, against well under 1 % for the built compressors. The human added the
slice on 2026-10-04.

- **E10(a) before code:** the provider accepts a history with stubbed edit arguments.
- **`edit_args_on_resume`** (SELECTIVE, off by default), with the conversation state of ADR 0012.
- **The smoke family `reread_after_pruned_edit`,** with its checker `answer_or_read`.
- **Exit:**
  - Tier 0 tests green;
  - the smoke record run by the human;
  - a dogfood week with the pruner on, comparing cache writes and reads per resume from exact
    usage.
- **Accepted 2026-10-04** (`slices/S8c/COMPLETION_REPORT.md`):
  - the pruner was built and evaluated;
  - any edit of the assistant's own tool-call history draws provider refusals
    (smoke run, E10(c)), so it is off and not recommended;
  - the conversation state stays, for a later pruner of old tool results at a resume.

## S8d — Pruning old tool results at a resume (stopped before code)

- **Requested** on 2026-10-04.
- **Stopped** by its pre-code experiment E10(d): removing an old tool result's content, with any
  stub or with nothing, drew provider refusals in 65–80 % of calls on `claude-opus-5-5`, against
  none with the original (TOKLI_EVIDENCE §2).
- **Consequence for S8a-3** (`superseded_tool_results`): it removes outdated reads, so it must
  pass the same refusal experiment before any code.

## S8e — Re-reads after an edit, sent by reference

- **Requested** by the human on 2026-10-04.
- **Pre-code experiment E10(e) passed:** a re-read that sends its changed lines and refers to the
  earlier read for the rest kept every edit anchor exact (20/20), drew no refusal, and cut the
  request by 42 %.
- **Contents:**
  - `reread_by_reference` (LOSSLESS by reference, prefix-stable, ADR 0013);
  - the smoke families `reread_fact_lookup` and `reread_edit_anchor`, with the checker
    `edit_anchor`.
- **Exit:**
  - Tier 0 tests green (decode property, integrity, prefix stability, complexity);
  - the smoke record run by the human; on by default if it says `no_measurable_damage`;
  - savings measured on dogfood.
- **Accepted 2026-10-04** (`slices/S8e/COMPLETION_REPORT.md`):
  - the smoke record says `no_measurable_damage` (no refusal; −40 % input tokens on its cases);
  - `reread_by_reference` is on by default.

## S8f — The request budget keeps history stable

- **Requested** by the human on 2026-10-04 (S8f SCR-001, from the S8e completion report).
- **Problem:** the request time budget (CC-014) made compression depend on timing. The
  same history could be forwarded differently on consecutive requests, which costs a
  provider cache rewrite.
- **Contents:** cached decisions (results and budget skips) repeat whatever the budget;
  pruners are never skipped by the budget.
- **Exit:** AC-CC-15 green on the CI matrix.
- **Accepted 2026-10-04** (`slices/S8f/COMPLETION_REPORT.md`).

## S5 — OpenAI Responses (Codex, API key)

- Adapter `openai_responses` (OR-*): `function_call_output`/`custom_tool_call_output`/`input_text`;
  usage from `response.completed`.
- Auth passthrough (Bearer) + **inject mode** for both providers (UP-003) — covers "OpenAI API-key
  authentication is required" for clients that cannot hold the key.
- Compat corpus: Codex Windows + Unix shapes.
- Exit: Codex (API key) session through Tokli with per-compressor attribution; E4 (Responses) done.

## S6 — Pricing and cost estimates

- **Price book:** dated, sourced, with matching and a user override (TC-008, TC-018).
- **Query-time cost:** with method and bounds. The **positional** method prices a saving by the
  cache region it sat in (TC-004, TC-017, ADR 0014; P1).
- **Dashboard:** the money card, per-compressor and per-request money, and the OAuth basis label
  (UI-013, TC-019).
- **`tokli eval`:** cost caps (QE-009…QE-011).
- **E2 (cache economics):** a scripted API conversation, run with compressors off and on.
  - Its dry run against a simulated cache is in the suite.
  - The real run is made by the human: the positional prediction must be within ±25 % of the
    observed saving (P6).
- **S6 SCR-001** (found by the E2 dry run): the earlier segment's change wins over a later
  reference stub (CC-019).
- **Accepted 2026-10-05** (`slices/S6/COMPLETION_REPORT.md`): the E2 real run passed (+19.8 %, tolerance 25 %).

## S6.5 — Dashboard review (simplicity)

- **Requested** by the human on 2026-10-05.
- **Done by an OpenAI Codex agent:** `AGENTS.md` and `slices/S6.5/BRIEF.md` are its
  instructions.
- **Contents:**
  - presentation, wording and layout of the dashboard only: simple, plain, not "AI-styled";
  - no API or behaviour change;
  - every SPEC 016 requirement still holds, and any wording change to approved texts needs a
    Spec Change Request.
- **Gates:**
  - Gate 1 on the agent's spec review (findings, proposals, sketches);
  - Gate 2 after the human verification in `slices/S6.5/HUMAN_REVIEW.md`, on screenshots and
    on the live dashboard.

## S6.6 — CPython 3.14

- **Requested** by the human on 2026-10-09 (S6.6 SCR-001, PT-004).
- **Contents:**
  - CPython 3.14 joins the supported set and the CI matrix (12 jobs);
  - a typing fix that newer mypy/pydantic releases need on every version;
  - release v0.1.1.
- **Accepted 2026-10-09** (`slices/S6.6/COMPLETION_REPORT.md`).

## S8h — Real agent formats

- **Requested** by the human on 2026-10-09, after the dogfood dashboard showed almost no
  saving. `reread_by_reference` had never acted: Claude Code's `Read` numbering is `"{n}\t"`.
- **Contents:**
  - SCR-001: both numbering styles (version 2);
  - format fixtures of real Claude Code shapes, with a contract test per compressor (P2);
  - the `not_applying` flag on the Compressors page and in `/tokli/health` (P3);
  - the real-traffic replay `tools/replay.py`, now part of every compressor slice (P4);
  - the reread smoke families in Claude Code's numbering (P1);
  - SCR-002: `PowerShell` is a verbatim tool by default.
- **Accepted 2026-10-09** (`slices/S8h/COMPLETION_REPORT.md`): version 2 is on by default with its smoke record.
- **Exit:**
  - the version 2 smoke record, run by the human; with `no_measurable_damage` it goes back on
    by default;
  - the replay on the human's sessions shows that it applies.

## S7 — OpenAI Chat Completions

- Adapter `openai_chat` (OC-*): `role:"tool"` + user text; usage only when the client asked.
- Exit: SDK-based client works; compat corpus green.

## S8b — Full quality evaluation (multi-provider), Tier 3, Codex pruning rules

The part of the original S8 that needs a second provider or agent tasks (split on 2026-10-03,
`slices/S8a/SPEC_REVIEW.md` P2, P7):

- Extend the S2.5 harness to the full tier: case generators, paired bootstrap CI, multi-model and
  multi-provider runs (Tier 2), Tier 3 protocol for agent tasks. Full-tier records for every
  compressor that is default-on at v1 (QE-006).
- The Codex shell-command classification (PR-014) for `analyze.tool_resources`.
- E8 (Tier 3 verbatim-quoting) and E10(b). Default-enabled set decided from data.

## S9 — Diagnostics and reproducibility polish

- Fingerprint with golden corpus (PT-006), `--explain`; Diagnostics page in UI.
- Full fresh-machine CI scenarios (SPEC 018).
- Release checklist: live smoke per protocol × auth mode.

## Later (not v1; each needs its own spec + evidence)

Prompt-cache-safe dedup (E2) · system/tool-description compression (E5) · prose compression (word deletion) for prose-only
segments · AST comment stripping (E8) · learned compressors (LLMLingua) behind `expensive` cost
class · redaction stage (future security work) · additional providers (Azure, Bedrock, Vertex) ·
OpenTelemetry sink.

## Dashboard timing rationale

The UI arrives in S3, after the persisted schema has survived S1–S2 (two real consumers: the log
and the trace API). That is early enough that dogfood savings are visible from week ~3. Building it
in S1 would freeze a schema before usage data (S2) exists.
