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

## S5 — OpenAI Responses (Codex, API key)

- Adapter `openai_responses` (OR-*): `function_call_output`/`custom_tool_call_output`/`input_text`;
  usage from `response.completed`.
- Auth passthrough (Bearer) + **inject mode** for both providers (UP-003) — covers "OpenAI API-key
  authentication is required" for clients that cannot hold the key.
- Compat corpus: Codex Windows + Unix shapes.
- Exit: Codex (API key) session through Tokli with per-compressor attribution; E4 (Responses) done.

## S6 — Pricing and cost estimates

- Price book (dated, sourced), matching, query-time cost with method and bounds (TC-*).
- Dashboard cost cards and per-compressor estimated monetary saving.
- E2 (cache economics) executed; proportional method validated or revised.

## S7 — OpenAI Chat Completions

- Adapter `openai_chat` (OC-*): `role:"tool"` + user text; usage only when the client asked.
- Exit: SDK-based client works; compat corpus green.

## S8 — Full quality evaluation + selective compressors

- Extend the S2.5 harness to the full tier: case generators, paired bootstrap CI, multi-model and
  multi-provider runs (Tier 2), Tier 3 protocol for agent tasks. Full-tier records for every
  compressor that is default-on at v1 (QE-006).
- `diff_context_trim`, `log_filter` (SELECTIVE, off by default);
  `dictionary` and `search_group` (LOSSLESS, off by default) with decoders.
- `analyze.tool_resources` (Claude Code defaults + the shell-command classification of SPEC 019) and
  `superseded_tool_results` (SELECTIVE, off by default).
- E7, E8, E2-ext (cache cost of superseding), E10 (argument stubbing / pair removal) executed.
  Default-enabled set decided from data.

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
