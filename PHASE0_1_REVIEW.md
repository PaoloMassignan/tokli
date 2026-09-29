# TOKLI — Phase 0.1 review

Status: **approved 2026-09-29** (see §E) · Date: 2026-09-28 · Scope: documentation and specifications only.
Nothing is implemented. S0 and S1 have not started.

Claim labels used below (defined normatively in SPEC 009): **PROVEN** (mechanical, tested on every
commit) · **ASSUMPTION** (model/agent behaviour, evaluated) · **HEURISTIC** (rule of thumb in config
data) · **POLICY** (product decision) · **VALIDATED** (backed by a recorded experiment or evaluation).
No behavioural assumption in Tokli is VALIDATED yet.

---

## 1. Executive summary

- **Lossless.** The old classification mixed two questions: is the information still in the request
  (provable), and does the model still do the task (not provable)? Tokli now keeps them apart. The
  policy depends only on the first. Default enablement depends on the second, through declared
  `assumptions` and an evaluation record. `duplicate_tool_results` stays eligible under LOSSLESS
  ONLY as **LOSSLESS by reference**, with a new runtime reference-integrity invariant. It is
  enabled by default only if its evaluation passes.
- **Early evaluation.** A deliberately small **smoke tier** moves to a new slice, **S2.5**, between
  S2 (exact usage) and S4 (the first default-on compressor whose value depends on the model reading
  a Tokli notation). It compares a baseline arm with a candidate arm, is run manually, and is
  cost-capped. The S8 harness extends it with the same formats.
- **Performance.** The 25 ms figure stays a **product target**. It is measured from S1 and reported,
  never gated. Four performance classes are now kept apart: correctness constraints, regression
  limits, product targets and router budgets.
- **Self-contained specification** (added on request during this review, §B and §D). No document
  of the specification set names or depends on an earlier project. Evidence is restated neutrally
  in `TOKLI_EVIDENCE.md`. Seven places where the normative behaviour was defined only by earlier code or tests
  are now defined in Tokli terms.
- The consistency pass found and fixed 12 contradictions or gaps (§10). The architecture is
  unchanged apart from one invariant (reference integrity) and one metadata field (`assumptions`).

## 2. Decisions made

| # | Decision | Type |
|---|---|---|
| D1 | Policy eligibility depends only on the **proven** preservation class (`kind` + `equivalence`). | POLICY |
| D2 | Every compressor declares behavioural `assumptions`. `default_enabled: true` requires an evaluation record covering all of them (CC-020, QE-016). | POLICY |
| D3 | The user-facing policy stays **LOSSLESS ONLY / LOSSY ALLOWED**. The internal model is richer (three LOSSLESS equivalences plus assumptions). The UI shows the equivalence and explains the policy in fixed words (UI-003, UI-010). | POLICY |
| D4 | `duplicate_tool_results` stays LOSSLESS (reference) and eligible under LOSSLESS ONLY. It is default-on only if its S4 smoke record passes. | POLICY |
| D5 | Reference integrity becomes a runtime engine invariant that always runs (CC-019). Stubs name the earliest copy (PR-012). | PROVEN (once implemented) |
| D6 | Reference-equivalence compressors are exempt from `verbatim_tools` (CC-021, PR-013). This is paired with the assumption `quotes_from_reference_target`. | POLICY + ASSUMPTION |
| D7 | New slice **S2.5**: smoke evaluation tier (SPEC 012 QE-012…QE-017). `json_minify` is default-on only **provisionally** in S1–S2. | POLICY |
| D8 | The 25 ms overhead is a product target. No absolute millisecond CI gate exists before a Tokli-measured baseline. `request_budget_ms` is a runtime control with a provisional default. | POLICY |
| D9 | The whole specification set is self-contained. Rationale cites neutral hazards and measurements (`TOKLI_EVIDENCE.md`, SPEC 018 MD-##). | POLICY |
| D10 | Every compressor is explained one by one, with examples, in `TOKLI_COMPRESSORS.md` (explanatory; specs stay normative). | POLICY |

## 3. Lossless / preservation taxonomy — before vs after

**Before.** Four kinds: LOSSLESS / SELECTIVE / LOSSY / UNKNOWN, with `equivalence` byte / structural /
reference / none. LOSSLESS meant "a decoder exists under a declared equivalence". The spec said
comprehension was a quality question, but nothing tied that question to a gate before S8, while
two compressors were planned as default-on (S1, S4). ARCH §4 still listed only byte/structural.

**After** (SPEC 009, "Terminology — preservation model"):

| Axis | Values | Decided by | Used for |
|---|---|---|---|
| Information preservation (proven) | LOSSLESS·byte, LOSSLESS·structural, LOSSLESS·reference, SELECTIVE, LOSSY, UNKNOWN | property/contract tests; runtime invariants | **policy eligibility** |
| Task behaviour (assumed) | a list of named assumptions per compressor | evaluation records (smoke tier, then full tier) | **default enablement** |

Considered and **not** introduced:

- A "semantically preserving" class. Tokli cannot prove semantic preservation. A class that cannot
  be proven would recreate the "lossless as a label" problem that Phase 0 set out to remove.
- A separate policy value for "reference". It would split LOSSLESS ONLY into two user choices
  without a safety gain, because the behavioural risk is handled by the default-enable gate
  (D2), whatever the policy.
- A per-compressor "notation" field. Whether the output uses a Tokli notation is recorded in the
  SPEC 010 summary as documentation. The gate is the assumptions list, which is more precise.

The only new metadata is `assumptions`. The only new invariant is reference integrity.
Composition rule: a chain's guarantee is its weakest link (byte > structural > reference >
selective > lossy).

## 4. Classification of every planned v1 compressor

| Compressor | Kind · equivalence | PROVEN | ASSUMPTION | HEURISTIC | LOSSLESS ONLY | Default (POLICY) |
|---|---|---|---|---|---|---|
| `json_minify` | LOSSLESS · structural | JSON value equality under parser P (number spelling, key order, duplicates kept); O(n) | `reads_minified_json`, `not_quoted_verbatim` | `verbatim_tools` | eligible | on, **provisional** until S2.5 smoke record |
| `duplicate_tool_results` | LOSSLESS · reference | whole-request decode; reference integrity; prefix stability; structure and arguments unchanged | `resolves_result_reference`, `quotes_from_reference_target` | — (exact byte match, no heuristic) | eligible | on **only if** the S4 smoke record passes (E11) |
| `search_group` | LOSSLESS · byte | byte round-trip; unparsed lines in place | `reads_grouped_search`, `not_quoted_verbatim` | grep-line recognition is exact, not heuristic | eligible | off (E8) |
| `dictionary` | LOSSLESS · byte | byte round-trip; no substitution in excluded regions | `applies_dictionary_legend` (E7), `not_quoted_verbatim` | — | eligible | off (E7/E8) |
| `superseded_tool_results` | SELECTIVE | latest full view of each resource verbatim; unknown tools untouched; structure unchanged; `prefix_stable: false` flagged | `outdated_content_not_needed` | tool semantics and shell-command rules (config data); age/min-saving thresholds (POLICY, E2-ext) | not eligible | off |
| `diff_context_trim` | SELECTIVE | headers, `+`/`-` lines, trailing non-hunk text verbatim; omission note | `context_lines_not_needed` (the output is no longer an applicable patch) | `diff_shape` detection | not eligible | off |
| `log_filter` | SELECTIVE | severe and unleveled lines verbatim and in order; omission note | `omitted_log_lines_not_needed` | level keywords, normalisation, 10 % gate | not eligible | off |

Earlier labels were not used. `search_group` and `dictionary` are LOSSLESS because the Tokli
designs have decoders. `superseded_tool_results` is SELECTIVE because the older version is gone.

## 5. Exactly what LOSSLESS ONLY permits

A compressor may run under LOSSLESS ONLY if and only if:

1. its `kind` is LOSSLESS with `equivalence` ∈ {byte, structural, reference} (CC-002);
2. its declared equivalence is backed by the registry contract test (CC-015): a segment round-trip
   property test, or for reference the whole-request decode property test;
3. for `reference`: request scope only; target earlier in the same request; prefix-stable; no
   change of message, block, item or argument structure (PR-005); and at run time the reference
   integrity check (CC-019) passes for every stub;
4. the engine invariants hold, as under any policy: token non-increase, protected spans,
   determinism, exception/timeout isolation.

It does **not** permit SELECTIVE, LOSSY or UNKNOWN compressors under any configuration.

It does **not** promise identical model behaviour or that tool output can still be quoted at its
original position. Whether a permitted compressor is **on by default** is a separate decision
(CC-020). The user can still enable or disable any permitted compressor.

User-facing wording (UI-010): *"Tokli only applies transformations that provably keep all
information in the request: exactly, structurally (e.g. JSON whitespace), or by reference to an
identical earlier tool result. This does not guarantee identical model behaviour. Defaults are
chosen from evaluations."*

## 6. Mechanically provable (contract/property tests, Tier 0)

- Byte round-trip (`search_group`, `dictionary`); structural equality under a declared parser
  (`json_minify`); whole-request decode (`duplicate_tool_results`).
- Reference integrity (CC-019), stubs naming the earliest copy (PR-012), prefix stability (CC-006,
  PR-004), and unchanged structure and arguments (PR-005).
- Selective retention guarantees (CP-DT-*, CP-LF-*, PR-008).
- Engine invariants: token non-increase, protected spans, determinism, attribution sum, policy
  filtering, isolation.
- Metadata contracts: every compressor declares assumptions, and every default-on compressor has
  a valid evaluation record (CC-020, QE-016).
- Algorithmic complexity for cheap compressors (linear-time ratio tests).

## 7. Properties that need behavioural evaluation

Every entry in the Assumption column of §4. The two with the highest stakes before v1 are
`resolves_result_reference` and `quotes_from_reference_target` (duplicate pruning, the largest
expected lossless saving). The others are `reads_minified_json` and `not_quoted_verbatim`
(`json_minify`), and all assumptions of the S8 compressors. Tier 3 (agent tasks, tool-call
failure rate) remains the only way to measure the verbatim-quoting hazard end to end, and is
required before v1 release for tool-result compressors (QE-006).

## 8. Early evaluation slice: S2.5 (smoke tier)

**Question it answers:** "Does this compressor save tokens without measurably damaging the task?"
It answers with a stated detection limit: it detects gross damage only.

**Design** (SPEC 012 QE-012…QE-017):

- two arms through the real pipeline: baseline (all compressors off) and candidate (only the
  compressor under test on); same model, prompt, parameters, T = 0, 3 repetitions;
- a small fixed case set per declared assumption (≥ 20 cases each; synthetic,
  protocol-shaped, deterministic checkers); first families `json_fact_lookup` and
  `json_verbatim_quote` (S2.5), then `reference_fact_lookup` and `reference_verbatim_quote` (S4);
- recorded: Tokli version, both `config_hash`es, compressor version, model, case-set version,
  per-case outcomes, exact forwarded tokens per arm, saving, compressor latency;
- verdict per family from discordant pairs: `no_measurable_damage` iff `b − c ≤ 1` (plus an
  error-rate check); `insufficient_data` below n; thresholds are POLICY and provisional;
- manual only, cost estimate and confirmation or `--max-cost`, never automatic (QE-009…011
  now apply from S2.5); a free CI self-test with a fake upstream (identity vs destructive);
- output: `evals/records/<compressor>.yaml`, read by the CC-020 contract test.

**Why S2.5.** Mechanically safe transformations do not need it to be *available*. It is needed
before any *default-on* transformation whose value depends on the model. That first happens in S4
(`duplicate_tool_results`: a reference notation the model must resolve). Its dependencies are the
real pipeline (S1) and provider usage for exact token counts and cost caps (S2). It does not need
the dashboard (S3) or the config API (S4). Building it before S4, rather than inside S4:
(a) keeps S4 focused; (b) validates the harness on a low-risk compressor (`json_minify`) before it
has to judge a high-stakes one; (c) replaces `json_minify`'s provisional default with evidence
early.

**Not built early:** generators, bootstrap CIs, multi-provider runs, Tier 3, result dashboards.
S8 adds these on the same case and record formats.

## 9. Performance: target vs constraint

| Class | Definition | Tokli instances | Gate? |
|---|---|---|---|
| Correctness constraint | A violation is a bug on any machine | unbuffered streaming (AC-PX-3), per-call timeout isolation (CC-008), linear-time cheap algorithms (CP-JM-005, AC-RT-1 ratio), no import-time loading | yes, every commit |
| Regression limit | Relative to a Tokli-measured baseline on the same runner class | nightly E9: warn > 1.25×, fail > 2× p95 baseline (provisional) | nightly only, after the S1 baseline exists |
| Product target | A goal that is reported and reviewed | p95 ≤ 25 ms, ≤ 200k tokens, default LOSSLESS ONLY | no; a miss triggers a review |
| Router budget | A runtime control | `request_budget_ms` (provisional 50), `per_call_timeout_ms`, `cost_class`, `min_tokens` | no; skips are recorded and visible (`skipped_budget`, UI-009) |

Changes: the Vision row is relabelled as a target; the S1 acceptance reports (does not gate) the
overhead distribution; E9 runs in S1; AC-RT-1 no longer has a fixed 50 ms; overhead percentiles
per size bucket are in the metrics API and dashboard (TC-013, UI-009); `moderate`/`expensive`
compressors cannot be default-on without a latency distribution in their evaluation record.
Expensive compressors remain visible (cost class, latency, budget skips) and controllable
(toggle, budget).

## 10. Documents and specifications changed

| File | Change |
|---|---|
| `specs/009-compression-core` | preservation model, claim types, `assumptions`, CC-002/014/015 revised, CC-019…CC-021, AC-CC-10…12 |
| `specs/010-compressors-v1` | rewritten: classification per compressor, assumption ids, dictionary and log-filter rules fully specified, origin notes removed |
| `specs/019-tool-history-pruning` | reference claims table, verbatim exemption, default gate, PR-012…PR-014, shell-command classification and path normalisation in Tokli terms, AC-PR-8…10 |
| `specs/012-quality-evaluation` | smoke tier QE-012…QE-017, QE-003/006 scoped, AC-QE-5…7 |
| `specs/011-routing` | AC-RT-1 (no fixed ms), AC-RT-4 (closed set of routing inputs) |
| `specs/013-telemetry-and-cost` | TC-013 (overhead distribution), TC-014 (`history_rewritten`, `reference_stubs`) |
| `specs/016-dashboard` | UI-003 revised, UI-009, UI-010 |
| `specs/002`, `004`, `005`, `007` | externally-defined details replaced (hop-by-hop list, AC wording, reminder matching) |
| all `specs/*` | "Context / evidence" → Tokli-terms "Rationale"; "Migration / reuse notes" removed (moved) |
| `TOKLI_VISION.md` | "provably safe" overclaim fixed; overhead = target; quality row per tier |
| `TOKLI_SCOPE.md` | compression and pruning rows; non-goals and deferred items in Tokli terms |
| `TOKLI_ARCHITECTURE.md` | contract summary aligned with SPEC 009; three new review rows in §8 |
| `TOKLI_ROADMAP.md` | S1 performance row and reported check; **S2.5**; S4 default gate; S8 renamed |
| `TOKLI_TEST_STRATEGY.md` | new invariants, smoke tier, thresholds per tier, E9 in S1, **E11**, new §8 performance classes |
| `TOKLI_TELEMETRY_AND_COST.md` | `history_rewritten`, `reference_stubs`, overhead aggregates |
| `TOKLI_OBSERVABILITY.md` | reason code `reference_target_modified` |
| `TOKLI_TRACEABILITY.md` | rows for every new requirement, renamed tests, Phase 0.1 map |
| `TOKLI_EVIDENCE.md` (new, §D) | hazards H01…H41 and measurements (E5a) in neutral terms |
| `TOKLI_COMPRESSORS.md` (new, §D) | every compressor explained with examples |
| `specs/018` | machine-dependence checklist MD-01…MD-28, reproducibility mechanism and fresh-machine scenarios, now inside the spec (PT-011) |
| `README.md` | pointers, R7/R8, Q17–Q19 |

Consistency-pass findings (fixed):

1. ARCH §4 contract allowed only byte/structural for LOSSLESS, which contradicted SPEC 009's `reference`.
2. The interaction between `verbatim_tools` and duplicate pruning was unspecified. Read literally,
   it would have excluded `Read`/`Bash`, the main duplicate case → CC-021, PR-013.
3. A duplicate stub could end up pointing at a result that `superseded_tool_results` later
   stubbed (dangling reference) → CC-019, PR-012, AC-PR-8.
4. `json_minify` (S1) and `duplicate_tool_results` (S4) were default-on, while Vision and Test
   Strategy required evaluation before default enablement, and evaluation arrived only in S8 →
   S2.5 plus a provisional record.
5. QE-003 (≥ 40 cases, ≥ 2 models) would have forbidden any smaller early tier → scoped to the full tier.
6. PR-009's `history_rewritten` was missing from the persisted `RequestRecord` → TC-014.
7. E9 named the budget as "CC-016" (that is `verify_lossless`) → CC-014.
8. AC-RT-1 had a fixed 50 ms CI threshold before any measurement → ratio test plus regression baseline.
9. Vision promised "provably safe" compression → "provably information-preserving, effect measured".
10. SPEC 005 and SPEC 019 disagreed on whether a shell-command classifier is needed → SPEC 019 now defines its own rules.
11. The roadmap's S1 `verbatim_tools` `["Read","Bash"]` disagreed with SPEC 010's list → clarified.
12. The dictionary algorithm, log normalisation, reminder matching and shell classification were
    defined only by earlier code → defined in the specs (§B).

Observed and **not** changed (pre-existing, outside this review's scope): three tests named in
specs have no traceability row (`test_responses_segment_mapping`,
`test_responses_reasoning_untouched`, `test_ui_toggle_patches_config`). They need a one-line fix
each.

## 11. New and changed requirements and tests

- **New requirements:** CC-019, CC-020, CC-021 · PR-012, PR-013, PR-014 · QE-012…QE-017 ·
  TC-013, TC-014 · UI-009, UI-010 · CP-DT-004, CP-LF-004.
- **Changed:** CC-002, CC-014, CC-015 · QE-003, QE-006 · UI-003 · PX-004 · CP-DI-001, CP-DI-004 ·
  CP-LF-001 · AC-RT-1, AC-RT-4, AC-OC-2, AC-OR-4, AC-PR-2 · SPEC 007 `analyze.reminders` definition.
- **New acceptance criteria:** AC-CC-10…12 · AC-PR-8…10 · AC-QE-5…7 · AC-TC-7, AC-TC-8.
- **New planned tests:** `test_reference_target_integrity_enforced` ·
  `test_every_compressor_declares_assumptions` · `test_registry_default_enabled_requires_eval_record` ·
  `test_verbatim_tools_exempt_only_reference_equivalence` · `test_duplicate_stub_names_earliest_copy` ·
  `test_superseded_rejected_on_reference_target` · `test_duplicate_pruning_applies_to_verbatim_tools` ·
  `test_shell_command_classification_rules` · `test_path_normalisation` · `test_smoke_arms_differ_only_in_candidate` ·
  `test_smoke_verdict_rule` · `test_smoke_insufficient_data` · `test_eval_cases_lint` ·
  `test_eval_record_schema_and_provisional_rule` · `test_eval_record_invalidated_by_version_bump` ·
  `test_smoke_harness_self_test` · `test_overhead_percentiles_by_bucket` · `test_target_is_reference_not_status` ·
  `test_request_record_pruning_fields` · `test_ui_shows_equivalence_assumptions_and_eval_status` ·
  `test_ui_overhead_target_is_reference_line` · `test_ui_policy_explanations_text` ·
  `test_dictionary_selection_deterministic_tie_break` · `test_dictionary_nested_symbol_decode_order` ·
  `test_dictionary_no_gain_not_applied` · `test_diff_trim_false_positive_shapes` ·
  `test_log_filter_normalisation_and_sampling` · `test_log_filter_mixed_keywords_kept_as_severe`.
- **Renamed:** the shell-classifier test → `test_shell_command_classification_rules`;
  `test_no_benchmark_markers_or_ml_in_routing` → `test_routing_inputs_closed_and_no_ml`.
- **New experiment:** E11 (reference resolution). E9 moves to S1.

## 12. Remaining open questions (need a product decision)

| ID | Question | Proposal |
|---|---|---|
| P1 | `json_minify` in S1–S2: default-on as a **provisional** dogfood default (current text), or default-off until its S2.5 smoke record? | Provisional default-on. The risk is low, it is mechanically proven, and dogfood is by the developer. |
| Q18 | Smoke thresholds: n ≥ 20 per assumption, `b − c ≤ 1`, 3 repetitions. They detect only gross damage (roughly a ≥ 10–15 pp drop). Acceptable as the pre-v1 gate? | Yes, labelled "smoke" everywhere. The full tier is required at v1. |
| Q19 | Reference model for smoke runs before v1 | The Claude model used for dogfood. One model only before S8. |
| Q17 | Should the duplicate stub also name the tool and resource, to ease reference resolution? | Decide from E11 data (a stub variant can be compared in the smoke tier). |

Existing open questions Q1–Q16 are unchanged.

## 13. Disagreements with the review request

1. **"Is LOSSLESS too broad?"** I agree that the classification was too broad **as a promise**. I
   do not agree with moving `duplicate_tool_results` out of LOSSLESS ONLY. The difference from
   JSON minification is one of degree, not of kind. `json_minify` also relies on the model
   (reading minified JSON) and on the agent not quoting the original bytes. Neither transformation
   can prove task equivalence. Both can prove information preservation, and the reference proof
   is as mechanical as the JSON one. Moving duplicates to LOSSY ALLOWED would push users who want
   the largest lossless saving into a policy that also admits genuinely destructive compressors.
   That is a worse safety outcome. The real risk is addressed where it belongs: the default-enable
   gate (evaluated assumptions) and the reference-integrity invariant.
2. **"Semantically preserving" as a class:** rejected (§3). It cannot be proven, and an unproven
   class is a label.
3. **"Without measurably damaging the task":** a small smoke tier cannot show the absence of
   damage. It can show the absence of *gross* damage. The spec says so explicitly (QE-015) and
   keeps the full tier as the v1 release requirement.
4. **Performance:** the per-call timeout (CC-008) and linear-time requirements remain hard. They
   are correctness guards against hangs and pathological inputs, not latency targets.

---

## B. Reference audit of `specs/` (requested during this review)

**Rule applied:** normative text (requirements, acceptance criteria, interfaces, test
expectations, defaults) must be fully defined in Tokli terms, without pointing at earlier code,
tests or terminology.

**Places where behaviour was defined only by reference to earlier code, now defined in the spec**

| Spec | Gap | Resolution |
|---|---|---|
| 010 `dictionary` | The algorithm was described as changes to an existing implementation, with tests borrowed from it | Full algorithm: candidates, deterministic selection, output format, collision guard, decoder. New tests. |
| 010 `log_filter` | "Normalised pattern" and level detection were undefined | Keyword classes, normalisation and sampling defined (CP-LF-004). New tests. |
| 010 `diff_context_trim` | False-positive cases came from external tests | CP-DT-004 plus `test_diff_trim_false_positive_shapes` with the listed shapes |
| 019 | Shell-command semantics came from an external classifier; path normalisation was unspecified | Shell-command classification table, script extraction, simple-command rule, path normalisation (PR-014) |
| 007 | Reminder matching rules were only in a reuse note | Moved into the `analyze.reminders` definition |
| 011 | AC-RT-4 scanned for an externally defined marker | Closed set of routing inputs plus an ML-import scan |
| 000 → TOKLI_SCOPE | Non-goals were phrased as names of earlier features | Rewritten as capabilities ("any capability not listed under In scope") |

Minor wording fixed: PX-004 (hop-by-hop headers listed, RFC 9110), AC-OC-2, AC-OR-4, AC-PR-2.
Each spec now carries a short "Rationale" and points to `TOKLI_EVIDENCE.md`.

---

## C. Development process: `CLAUDE.md` (requested during this review)

**Created:** `CLAUDE.md` at the repository root. It sets:

- the mandatory 11-step slice lifecycle: read → spec review → **Gate 1** → freeze → derive tests →
  red → green → refactor → verify → **Gate 2** → completion only after acceptance, with no
  automatic next slice;
- what counts as explicit approval;
- the Spec Change Request rule and template;
- the ADR rule and template;
- YAGNI and seam rules;
- a self-contained specification (§8);
- the actions that always need the human (paid or credentialed calls, real transcripts,
  commits and pushes);
- SPEC_REVIEW and COMPLETION_REPORT templates;
- the file locations (`slices/S<n>/…`, `docs/adr/…`, created on first use);
- the spec status lifecycle (`Draft` → `Approved for S<n> (date)`, per slice).

**Consistency changes made so the other documents agree with it**

| Document | Change |
|---|---|
| `TOKLI_TEST_STRATEGY.md §1` | Rewritten as a summary of the gated lifecycle, pointing to `CLAUDE.md §2`. The seam criterion changed from "a second **known** implementation" (future ones counted) to "a current need or two **concrete current** behaviours". Bug workflow kept, without its legacy attribution. |
| `TOKLI_TEST_STRATEGY.md` §2, §5, §7, §8 | Regression row states the known failure shapes in Tokli terms. Tier 2, E5 and E10 wording is self-contained. "Demo notes" became "completion reports". |
| `TOKLI_ROADMAP.md` | The header defines each slice as Gate 1 … Gate 2, with no automatic start of the next slice. S0 import contracts cover the modules that exist and grow as modules appear. S1 performance is reported in the completion report. The "Later" list uses Tokli terms. |
| `TOKLI_ARCHITECTURE.md §4` | Seams are **allowed boundaries**, not a build list. An interface appears only when the slice needs it or two implementations exist. §9 no longer says existing compressors and tests "port directly". |
| `CLAUDE.md §8` | Superseded by §D: the whole specification set is self-contained. |

**Items for the S1 Gate 1 (not changed now, because they are spec decisions)**

| # | Finding | Recommendation |
|---|---|---|
| C1 | SPEC 007 PL-002 and AC-PL-1: the `must_precede` mechanism and its test double exist **only** for a future redaction stage. That is future-slice infrastructure under the new YAGNI rule. | In S1, reduce PL-002 to "unknown stage → refuse to start; analyzers precede transformers". Reintroduce `must_precede` in the slice that adds the first stage with a real ordering constraint. |
| C2 | PL-001 (the configured stage order) and PL-007 (a test stage inserted "through config alone"): S1 has one fixed stage list. | Keep PL-007 as a boundary test with a test-only stage built in the test. Decide at S1 Gate 1 whether `pipeline.stages` must be user-configurable in S1 or fixed until a second ordering exists. |
| C3 | SPEC 009 with one compressor in S1: `terminal`, chain ordering (CC-009) and the request budget (CC-014) have a single real consumer in S1. | Keep the contract fields (records and fingerprint need them). Review in the S1 SPEC_REVIEW whether CC-009's multi-compressor behaviour is tested with fakes in S1 or deferred to S4. |

These do not block Phase 0 approval. They are exactly what the S1 spec review exists to decide.

---

## D. Self-contained specification set and compressor guide (requested 2026-09-29)

**Request:** the specification must not refer to earlier projects. A reader must understand every
concept without knowing them. Every compression tool must be explained clearly, one by one.

**Done**

| Change | Detail |
|---|---|
| Archive removed | The pre-Tokli analysis, the portability audit of earlier code and the former Phase 0 summary were removed from the working tree on 2026-09-29 (§E). They remain only in the git history of the initial commit. |
| `TOKLI_EVIDENCE.md` (new) | The rationale the specs need, restated neutrally: 30 hazards (H01…H41), each described so that it can be understood and reproduced on its own, and the E5a measurements with their method and limits. |
| SPEC 018 | Now contains the machine-dependence checklist (MD-01…MD-28), the fingerprint mechanism and the fresh-machine scenarios (new PT-011, AC-PT-6). |
| `TOKLI_TRACEABILITY.md` | Every "Why" cell rewritten to cite H##, MD-##, E5a, the brief or a stated rationale. The "reverse view" became a hazard view generated from `TOKLI_EVIDENCE.md`. |
| Vision, Scope, Architecture, Telemetry, Test Strategy, Roadmap | Remaining names and pointers replaced by hazard ids or neutral wording. |
| `README.md` | Rewritten as the entry point of the specification (reading order, risks, open questions), with no historical content. |
| `CLAUDE.md §8` | "Self-contained specification": no document, code or test names or depends on an earlier project. |
| `TOKLI_COMPRESSORS.md` (new) | Plain-language guide to all seven compressors: problem, how it works, before/after example, what is proven, what is assumed, when it does not apply, settings, default, risks. It is explanatory; specs 009/010/019 remain normative. |

**Check:** a case-insensitive search for the earlier project names, their file
names, markers and evidence tags finds none.

---

## E. Human gate record — Phase 0.1

**Approved** by the product owner on 2026-09-29: "Approvo, accetto le tue proposte. Solo inglese.
Cancella history."

Decisions recorded with the approval:

| Item | Decision |
|---|---|
| P1 | `json_minify` is default-on **provisionally** in S1–S2 (QE-016 `provisional` record), replaced by its S2.5 smoke record |
| Q18 | Smoke thresholds as proposed: n ≥ 20 per assumption, `b − c ≤ 1`, 3 repetitions, labelled "smoke" (QE-015) |
| Q19 | Smoke reference model: the Claude model used for dogfood; one model until S8 |
| C1 | Applied: PL-002 checks unknown stages and analyzer-before-transformer order; `must_precede` waits for the first stage that needs it (SPEC 007, ARCH §4) |
| C2, C3 | No proposal was made. They stay open for the S1 spec review. |
| Language | All documentation in English only (`CLAUDE.md §8`) |
| Archive | `history/` deleted |
| Traceability | The three pre-existing untraced tests are now mapped (OR-001, UI-004) |

Still open, for later gates: Q17 (stub wording, E11, S4), the SPEC 019 age-rule ambiguity for
`superseded_tool_results` (S8 spec review), and the experiment-driven questions Q1–Q7, Q9, Q10,
Q12, Q14–Q16.
