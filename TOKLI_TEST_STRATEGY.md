# TOKLI — Test Strategy

## 1. Workflow per vertical slice (SDD → TDD, human-gated)

The binding process is `CLAUDE.md §2`. In summary:

1. **Read** the approved specs, roadmap entry, ADRs and existing code for the slice.
2. **Spec review** in `slices/S<n>/SPEC_REVIEW.md`: ambiguities, contradictions, missing behaviour,
   portability, observability, architectural risks, product questions vs implementation decisions.
3. **Human gate 1:** the human answers the questions and approves the spec delta. No code before this.
4. **Freeze:** the approved spec is authoritative. It changes only through a Spec Change Request
   (`CLAUDE.md §4`), never to make code or tests pass.
5. **Derive tests** from every requirement and acceptance criterion, and update
   `TOKLI_TRACEABILITY.md`.
6. **Red:** tests are written first and fail for the expected behavioural reason (an assertion on
   behaviour, not a missing import).
7. **Green:** the smallest coherent implementation, with nothing from later slices.
8. **Refactor** with tests green.
9. **Verify:** all test categories the slice needs (§2); architecture review (import contracts
   green, and no abstraction without a current need or two concrete current behaviours,
   `CLAUDE.md §5`); observability checklist (`TOKLI_OBSERVABILITY.md §8`); portability checks;
   performance recorded per §8.
10. **Human gate 2:** completion report `slices/S<n>/COMPLETION_REPORT.md`, then wait for explicit
    acceptance. The next slice never starts automatically.

Bug workflow: every bug gets a failing regression test first, named after the behaviour, with the
root cause in the docstring.

## 2. Test categories

| Category | Folder | What it proves | Runs | Network |
|---|---|---|---|---|
| Unit | `tests/unit/` | Single functions and classes: compressors, config merge, pricing math, usage mapping | every commit | none |
| Property / invariant | `tests/property/` | Hypothesis-based: lossless decode(encode(x)) equivalence, token invariant, determinism, protected spans, attribution sum | every commit (bounded examples); nightly (large) | none |
| Contract | `tests/contract/` | Every registered compressor satisfies the compressor contract. Every adapter satisfies the adapter contract (round-trip, eligibility, opaque preservation). Import-linter dependency rules. | every commit | none |
| Protocol compatibility | `tests/compat/` | Recorded request/response/SSE fixtures per protocol replayed through the full app against a fake upstream (respx/ASGI). Asserts body equality rules and byte-identical response and stream relay. | every commit | none |
| Streaming | `tests/compat/streaming/` | Chunk timing (no buffering), client disconnect cancels upstream, upstream mid-stream error, usage tee robustness to malformed events | every commit | none |
| Integration | `tests/integration/` | Real uvicorn server on an ephemeral port + fake upstream HTTP server. Config precedence end-to-end. Telemetry persisted. API/UI endpoints. | every commit | loopback only |
| Regression | `tests/regression/` | One file per fixed bug, plus regression cases for known failure shapes, each specified in Tokli terms: conversation content duplicated by a wrong splice (CM-002), a diff detector swallowing trailing text (CP-DT-002), line-numbered file dumps losing their prefixes (CP-JM-004, `verbatim_tools`) | every commit | none |
| Golden / savings | `tests/golden/` | Deterministic savings per compressor on the golden corpus. Fails if saving changes without a deliberate expected-value update. | every commit | none |
| Portability | CI job `portability` | Fresh-machine scenarios (SPEC 018) + cross-OS fingerprint equality | every PR (3 OS × Python matrix) | loopback only |
| Evaluation (quality) | `evals/` (not pytest-collected) | Paired baseline vs compressed task quality with real models | manual / nightly, costs money | provider APIs |
| Live smoke (opt-in) | `tests/live/` (marker `live`) | One real request per protocol × auth mode through a running Tokli, with credentials supplied by the developer's environment | manual before release | provider APIs |

Mocking policy: real components everywhere inside the process (real tokenizer with provisioned
data, real SQLite in a temp dir, real pipeline). Only the upstream network boundary is replaced by
a fake upstream that records exactly what it received.

## 3. Key invariant tests (must exist from the slice in which the behaviour appears)

| Invariant | Test (name) | Technique |
|---|---|---|
| Pass-through request is byte-identical upstream | `test_passthrough_forwards_original_bytes` | fixture corpus, all protocols |
| Patched body differs only at patched string values | `test_render_changes_only_patched_values` | JSON diff: set of changed pointers == set of patch locators |
| Block count, order, types, `cache_control`, signatures unchanged | `test_structure_preserved_after_compression` | structural comparison ignoring patched text |
| Response and stream bytes relayed unchanged | `test_response_bytes_identical`, `test_stream_chunks_identical_and_unbuffered` | fake upstream with scripted chunks + timestamps |
| forwarded ≤ original (estimate) per segment and per request | `prop_compression_never_increases_tokens` | Hypothesis over text generators + corpus |
| LOSSLESS compressors are invertible | `prop_<id>_decode_roundtrip` / `prop_<id>_decodes_whole_request` | Hypothesis: `decode(compress(x)) ≡ x` under declared equivalence (byte, structural, or whole-request for reference) |
| Reference targets stay intact | `test_reference_target_integrity_enforced` | fake selective pruner targeting a referenced segment |
| Default-enabled ⇒ evaluated | `test_registry_default_enabled_requires_eval_record` | registry × `evals/records/` |
| Determinism | `prop_compression_is_deterministic`, `test_segment_output_independent_of_other_segments` | repeat and shuffle-other-segments |
| Protected spans untouched | `prop_protected_spans_preserved` | random span insertion |
| Attribution sums | `prop_marginal_savings_sum_to_total` | random chains |
| Duplicate pruning is lossless and prefix-stable | `prop_duplicate_pruning_decodes_whole_request`, `test_duplicate_pruning_prefix_stable_across_turns` | random tool histories with repeats; growing conversations |
| Policy respected | `test_lossless_only_never_runs_lossy_compressor` | registry with fake LOSSY compressor that fails the test if called |
| Enabled ≠ forced | `test_enabled_compressor_not_applied_when_not_applicable` | |
| No credentials in logs or DB | `test_logs_never_contain_credentials` | canary keys through all auth paths; scan logs + SQLite bytes |
| No prompt content by default | `test_default_logging_contains_no_prompt_text` | canary strings in segments |
| Dependency rules | `test_import_contracts` | import-linter config in `pyproject.toml` |

## 4. Protocol compatibility corpus

Fixtures are **synthetic but shaped from real traffic** (no real prompts, no developer paths),
stored as JSON + SSE transcripts under `tests/compat/fixtures/<protocol>/`:

- Anthropic: string content; block content; multi-text blocks with `cache_control`;
  `tool_use`/`tool_result` (string and block content, `is_error`); images; documents; `thinking` +
  signature; `redacted_thinking`; server tool blocks; unknown future block type; `system` as string
  and as blocks; tools with `cache_control`; Claude-Code-like request with `<system-reminder>`;
  SSE stream including `ping`, `error` event; non-stream response; 400/401/429/529 errors.
- OpenAI Chat: roles system/developer/user/assistant/tool; string and part content; `tool_calls`;
  `stream_options.include_usage` on/off; errors.
- OpenAI Responses: string `input`; item list with `message`/`input_text`, `function_call`,
  `function_call_output` (string + parts), `custom_tool_call(_output)`, `reasoning` with
  `encrypted_content`; `previous_response_id`; `store:false` + `prompt_cache_key`; Codex Windows
  and Unix shapes; SSE event stream; errors.

Before v1 release, E4 captures real transcripts (with the developer's consent, then scrubbed) to
confirm the synthetic fixtures match current API shapes.

## 5. Quality evaluation (summary; normative in `specs/012`)

- **Tier 0 — offline guarantees (CI):** property tests above. Proves lossless and selective
  guarantees. Says nothing about model behaviour.
- **Tier 1 — offline savings (CI):** golden corpus savings per compressor, isolated and chained.
- **Smoke tier (manual, from S2.5):** `tokli eval smoke`. Baseline vs candidate on ≥ 20 cases per
  declared assumption, one model, 3 repetitions. Detects gross damage only. It is enough for
  default enablement before v1 (QE-012…QE-017).
- **Tier 2 — paired fact probes (nightly/manual):** fact probes on agent-shaped content, at scale. For
  each content category (JSON tool output, grep, diff, logs, directory listings, stack traces,
  prose), ≥ 40 generated cases with a verifiable answer. Each is run baseline vs compressed on ≥ 2
  models (one Anthropic, one OpenAI), T=0, 3 repetitions. Reports accuracy delta with a
  paired-bootstrap 95 % CI.
- **Who pays and when (Q11):** Tier 2 and Tier 3 are run by a Tokli *user* with `tokli eval`,
  against their own provider account and chosen models. The tool prints an estimated cost, requires
  confirmation or `--max-cost`, and stops at the cap. Nothing runs automatically. Maintainers
  use the same tool to justify shipped defaults.
- **Tier 3 — agent task eval (manual, pre-release for any default-enabled change):** a fixed
  set of ≥ 20 small repository tasks run with Claude Code and Codex through Tokli on/off.
  Measures task success, **tool-call failure rate (Edit `old_string` not found, JSON/argument
  errors)**, turns, and total provider-reported input tokens and cost.

Acceptance thresholds (initial, to be revisited with data):

| Compressor class | To be **default-enabled** | To be **available** (off by default) |
|---|---|---|
| LOSSLESS (before v1: provisional default) | Tier 0 pass; smoke verdict `no_measurable_damage` for every declared assumption | Tier 0 pass |
| LOSSLESS (at v1 release) | Tier 0 pass; Tier 2 non-inferiority: upper bound of the 95 % CI of the accuracy drop ≤ 2 pp; Tier 3: no increase in tool-call failure rate beyond noise (≤ +1 pp) | Tier 0 pass |
| SELECTIVE / LOSSY | Not default-enabled in v1 | Tier 0 guarantees pass (CC-015). Before v1 a compressor may be available without an evaluation record (CC-020); the dashboard shows it as "not evaluated". At v1 release: Tier 2 run and published; drop CI upper bound ≤ 5 pp per category it applies to (S8a SCR-001) |

Earlier measurements (TOKLI_EVIDENCE.md §2) are inputs to prioritisation only.

## 6. Test data hygiene

- No real prompts, keys, usernames or absolute developer paths in fixtures (lint test).
- Canary strings (`TOKLI-CANARY-…`) in every fixture support the content-leak tests.
- Generated cases are seeded. The generator version is recorded in results.

## 7. Experiments (unknowns → smallest experiment that resolves them)

| ID | Question | Status | Smallest experiment | Output that decides |
|---|---|---|---|---|
| **E1** | Does Claude Code work through Tokli in passthrough mode with (a) an API key, (b) a Pro/Max OAuth login, with `ANTHROPIC_BASE_URL=http://127.0.0.1:8787/anthropic`? Which headers does it send? | REQUIRES EXPERIMENT | Slice-1 build, compression off. Run 3 prompts per auth kind. Record header *names* (not values) and status codes. | Auth support matrix row → SUPPORTED / NOT SUPPORTED. Also: path-prefix base URL works or not. |
| **E2** | Net cost effect of deterministic compression under prompt caching; cost of a mid-session config change | REQUIRES EXPERIMENT | Scripted 20-turn Claude Code session on a fixed repo, run twice (Tokli pass-through vs `json_minify` on) plus once with a config flip at turn 10. Compare provider `usage` per turn. | Proves or disproves "compression keeps cache hits"; calibrates the proportional cost method. |
| **E3** | Proxy-tokenizer error vs Claude/OpenAI real counts | REQUIRES EXPERIMENT | 200 fixture segments: local o200k/cl100k vs Anthropic `count_tokens` and OpenAI usage. | Error distribution; default tokenizer per family; whether `k` calibration is needed per request or per model. |
| **E4** | Exact SSE usage event shapes today (all three protocols), including error events mid-stream | REQUIRES EXPERIMENT | Capture 3 streams per protocol with a transcript recorder (header names + event types + usage fields only). | Usage parser requirements AN-005…007 / OC-005…007 / OR-005…006 frozen; fixtures updated. |
| **E5** | Real traffic composition: tokens by segment kind (system, tools, user text, tool_result, assistant) and by content shape (JSON, grep, diff, log, code with line numbers, prose) | **(a) DONE 2026-09-28**, see TOKLI_EVIDENCE §2: 8.1 % text-compression saving, mostly from lossy transformations; composition not answerable from the available flags. **(b) REQUIRES EXPERIMENT** | (a) Offline: aggregate existing proxy logs, **counters and flags only** (no content read); method in TOKLI_EVIDENCE §2. (b) Tokli slice 1 in pass-through with analyzers on for 1 week of dogfood. | Priority order of compressors for S4+; whether system/tool compression is worth it. |
| **E6** | Can Codex with ChatGPT-subscription auth be pointed at a proxy? | REQUIRES EXPERIMENT | Check Codex config options for a custom base URL under ChatGPT auth. Try against a Tokli verbatim route. | UP-008 stays NOT SUPPORTED or becomes a new spec. |
| **E7** | Do models use `§` dictionary legends correctly inside tool results? | REQUIRES EXPERIMENT | Tier 2 probe set restricted to dictionary-compressed tool outputs, 2 models. | Whether `dictionary` may ever be default-enabled. |
| **E8** | Does transforming tool output raise agent tool-call failures (verbatim-quoting hazard)? | REQUIRES EXPERIMENT | Tier 3 subset: 10 edit-heavy tasks with `json_minify`, then `search_group`, applied to all tool outputs (including `verbatim_tools`) vs excluded. | Default `verbatim_tools` list; go/no-go for broader scopes. |
| **E2-ext** | Cache cost of `superseded_tool_results` vs its saving, at different `min_age_turns` / `min_saving_tokens` | REQUIRES EXPERIMENT | Same 20-turn scripted session as E2 with re-reads after edits. Compare provider usage per turn (cache_write vs cache_read vs input) across three threshold settings. | Default thresholds, or "not worth it" |
| **E10** | May historical tool calls be removed structurally, or their arguments stubbed (Edit `old_string`/`new_string` were a large share of the E5a pruning saving, TOKLI_EVIDENCE §2)? | REQUIRES EXPERIMENT | (a) API acceptance: replay fixture conversations with stubbed arguments / removed pairs against both providers (400 or not). (b) Tier 3 subset on edit-heavy tasks. | Whether a `superseded_tool_args` pruner / structural removal gets a spec |
| **E9** | Overhead at scale: p95 latency of parse + pipeline + render for 200k-token requests | REQUIRES EXPERIMENT (**run in S1**, then nightly) | Benchmark script over golden corpus scaled ×N on each CI OS. | First regression baseline (§8); router budget defaults (CC-014, CC-008); whether segment-level caching is needed. Compared with the Vision target, but not gated on it. |
| **E11** | Do models use duplicate-result reference stubs correctly, including verbatim quoting from the earlier copy? | REQUIRES EXPERIMENT (S4) | Smoke tier: families `reference_fact_lookup` and `reference_verbatim_quote` (SPEC 012), Claude model used for dogfood. | `duplicate_tool_results` default on/off. A Tier 3 subset is required before v1 release. |

## 8. Performance: four classes that are never mixed

| Class | What it is | Examples | Where it is checked | Effect when violated |
|---|---|---|---|---|
| **Correctness constraint** | A property whose violation is a bug, whatever the machine | streaming is unbuffered (AC-PX-3); a hung or slow compressor is isolated by the per-call timeout (CC-008); cheap-class algorithms are linear (CP-JM-005, AC-RT-1 ratio test); nothing loads at import time (TM-007) | unit/compat tests, every commit | test fails, merge blocked |
| **Regression limit** | A relative bound against a **measured** baseline on the same runner class | nightly E9 benchmark: warn at p95 > 1.25 × baseline, fail at p95 > 2 × baseline (POLICY, provisional) | nightly job; baseline file committed in S1 and updated only deliberately, with a reason | nightly red, investigated |
| **Performance target** | A product goal | Vision: p95 overhead ≤ 25 ms, ≤ 200k tokens, default LOSSLESS ONLY pipeline | reported from S1: completion reports, dashboard (TC-013, UI-009) | a review of the default pipeline. It never rejects a compressor automatically. |
| **Router budget** | A runtime control that bounds work per request | `compression.request_budget_ms` (CC-014), `per_call_timeout_ms` (CC-008), `cost_class`, `min_tokens` | engine at run time; skips are counted (`skipped_budget`) and shown per compressor | the compressor is skipped for that request, visibly. Users can change the budget. |

Rules:

- No absolute millisecond threshold becomes a CI gate before a baseline measured by Tokli exists.
- A compressor is judged on the dashboard's efficiency figures (tokens saved per ms, zero-benefit
  rate, `skipped_budget` rate) and on its evaluation record, not on a single latency number.
- `moderate` and `expensive` compressors are never default-enabled without a latency distribution
  in their evaluation record (QE-014 `ms_total`).
