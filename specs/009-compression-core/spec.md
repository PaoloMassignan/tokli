# SPEC 009 — Compression core: contract, classification, policy, engine

Status: Draft (revised in Phase 0.1) · Slice: S1 (engine + one compressor, fixed policy), S4 (policy + registry UI) · Related: ARCH §4, PHASE0_1_REVIEW.md
Approved for S1 (2026-09-30): CC-001…CC-008, CC-010…CC-017, CC-020 (provisional record). CC-009 in S4 (decision C3); CC-018 in S8; CC-019, CC-021 and request scope in S4.
Approved for S2 (2026-10-02): CC-024.
Changed by S4 SCR-001 (2026-10-03): CC-002 (the policy is a shortcut, not a gate), AC-CC-1, AC-CC-11, the eligibility column.
Approved for S4 (2026-10-03): CC-002 (SCR-001), CC-003, CC-009, CC-015 and CC-016 for `reference`, CC-019, CC-021, the request scope.
Changed by S8a SCR-001 (approved for S8a-1, 2026-10-03): CC-021 (per-compressor opt-in for verbatim tools).

## Purpose
Define what a compressor is, what "lossless" means in Tokli, how the global policy constrains
which compressors may run, and how the engine applies them safely and measurably.

## Rationale
- "Lossless" is a property proven by a decoder and a property test, never a label.
- Cross-cutting guarantees (identity on failure, token non-increase, protected spans, timing, records) are enforced once by the engine, not per compressor.
- Savings must be attributable per compressor. A single "dominant strategy" per request cannot attribute savings.
- Compression latency is a measured product risk (TOKLI_EVIDENCE §2, E5a). The engine therefore has a runtime budget (CC-014), whose default is provisional (TOKLI_TEST_STRATEGY §8).

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 009 rows).

## Terminology — preservation model

Tokli keeps two questions apart:

1. **Information preservation.** Can Tokli *prove mechanically* that the forwarded request still
   contains the original information? This is the compressor's `kind` plus `equivalence`. It is
   the **only** input to the "Lossless only" shortcut (CC-002, S4 SCR-001).
2. **Task behaviour.** Does the model do the task as well with the transformed request? No
   transformation can prove this, not even whitespace removal. It is stated as declared
   `assumptions`, measured by evaluation (SPEC 012), and it gates **default enablement** (CC-020),
   not whether a compressor may run.

| kind | equivalence | What is proven (mechanically, on every commit) | Decoder | "Lossless only" shortcut |
|---|---|---|---|---|
| **LOSSLESS** | **byte** | `decode(compress(x)) == x` byte-for-byte, using the segment alone | segment `decode()` | kept on |
| **LOSSLESS** | **structural** | `P(compress(x)) == P(x)` for a declared parser `P`. The bytes that differ are, by the definition of `P`, insignificant (e.g. JSON whitespace outside strings). `decode()` is the identity. | identity | kept on |
| **LOSSLESS** | **reference** | Request scope only. Every replaced text is still present in an **earlier** segment of the **same forwarded request**, which the replacement names unambiguously. Decoding the whole request restores every original text (under the target's own equivalence). Runtime reference integrity (CC-019), prefix stability (CC-006) and structure preservation (PR-005) hold. | `decode_request()` | kept on |
| **SELECTIVE** | none | A declared retention rule: the named content is kept verbatim, and everything else may be removed. Not invertible. | — | switched off |
| **LOSSY** | none | Only the engine invariants (token non-increase, protected spans, structure). | — | switched off |
| **UNKNOWN** | none | Nothing. | — | switched off; never on by default (only an explicit user choice enables it) |

What LOSSLESS does **not** mean: that the model behaves identically, or that the agent can still
quote the original bytes at the original position (the verbatim-quoting hazard). Those are
behavioural assumptions. They are declared per compressor and evaluated (SPEC 012). They are not
proven.

**Composition.** When several accepted transformations touch the same information (a chain on one
segment, or a later compressor changing a reference target), the resulting guarantee is the
weakest link, in the order byte > structural > reference > selective > lossy. The trace records the
accepted chain per segment.

### Claim types (used in every spec and in the review record)

| Label | Meaning | Backed by |
|---|---|---|
| **PROVEN** | A mechanical property of the transformation | property, contract or invariant test on every commit (Tier 0) |
| **ASSUMPTION** | Behaviour of the model or agent that Tokli relies on | declared in `CompressorSpec.assumptions`, measured by an evaluation record (SPEC 012) |
| **HEURISTIC** | A rule of thumb expressed as config data (e.g. `verbatim_tools`, tool semantics) | visible in config and doctor; revised by experiments |
| **POLICY** | A product decision (thresholds, defaults, budgets) | this spec set; changed only by a spec change |
| **VALIDATED(E*n*/eval)** | An assumption or heuristic backed by a recorded experiment or evaluation report | the referenced report |

## Contract

```python
@dataclass(frozen=True)
class CompressorSpec:
    id: str                    # stable, snake_case; part of config and telemetry
    name: str                  # human-readable
    version: str               # bump on any output-changing change (fingerprint input)
    kind: Literal["LOSSLESS", "SELECTIVE", "LOSSY", "UNKNOWN"]
    equivalence: Literal["byte", "structural", "reference", "none"]
    scope: Literal["segment", "request"]   # request = pruners (SPEC 019)
    prefix_stable: bool                    # output for segment j depends only on segments 0..j
    guarantees: tuple[str, ...]            # PROVEN properties, each backed by a named test
    assumptions: tuple[str, ...]           # ASSUMPTION ids (behavioural), each covered by an eval case family (SPEC 012)
    stage: Literal["normalize", "structural", "domain", "semantic"]
    segment_kinds: frozenset[SegmentKind]
    min_tokens: int                        # default skip threshold
    cost_class: Literal["cheap", "moderate", "expensive"]
    terminal: bool
    requires: tuple[str, ...]              # importable module names
    default_enabled: bool
    config_model: type[BaseModel]          # per-compressor options (validated)

class Compressor(Protocol):
    spec: CompressorSpec
    def applicable(self, text: str, view: SegmentView, features: Features) -> Applicability: ...
    def compress(self, text: str, view: SegmentView) -> str | None: ...   # None = no change
class LosslessCompressor(Compressor, Protocol):
    def decode(self, text: str) -> str: ...

class RequestCompressor(Protocol):          # scope == "request" (pruners)
    spec: CompressorSpec
    def plan(self, segments: Sequence[SegmentView], texts: Sequence[str],
             tools: Sequence[ToolRecordView]) -> list[Proposal]: ...   # Proposal = (segment_id, new_text)
    # LOSSLESS (reference) request compressors also provide:
    def decode_request(self, texts: Mapping[str, str], views: Sequence[SegmentView]) -> dict[str, str]: ...
```

The engine runs request-scope compressors **before** segment-scope ones (PR-010). Each proposal
goes through the same acceptance gate, protected-span check and accounting as a segment result.
Attribution is per proposal.

`SegmentView` = `{kind, role, attrs.tool_name?, attrs.is_error?, protected spans}`. It has no
protocol or provider fields. `Applicability = (ok: bool, reason: str)` with a short
compressor-specific reason code.

## Engine algorithm (per request)

```text
for segment in mutable segments (document order):
    text = segment.working_text
    for c in registry ordered by (stage, id):
        filter in order → first failing filter is the skip reason:
            enabled(c)? available(c)? kind ∈ c.segment_kinds?
            tokens(text) ≥ max(c.min_tokens, config.min_segment_tokens)?
            tool_name resolved and not in config.verbatim_tools (when kind == TOOL_RESULT and
                c.spec.equivalence != "reference")?        # CC-021
            budget remaining?  previous accepted compressor on this segment not terminal?
        a = c.applicable(text, view, features)            → not_applicable(reason) if false
        out = c.compress(text, view)  (timed, exception-isolated, per-call timeout)
        if out is None or out == text:                    → rejected_no_gain
        if protected spans not preserved in order:        → rejected_invariant
        t_in, t_out = tokens(text), tokens(out)
        if t_out > t_in - max(config.min_gain_tokens, ceil(t_in * config.min_gain_ratio)):
                                                           → rejected_no_gain / below_min_gain
        if config.verify_lossless and c is LOSSLESS and decode(out) ≢ text:
                                                           → rejected_invariant(decode_mismatch)
        accept: text = out; record marginal = t_in - t_out
    if text != segment.text: emit Patch(segment.id, text, produced_by=[accepted ids])
# reference integrity (CC-019), checked for every proposal and segment result before acceptance:
#   a change to a segment that is the target of an accepted reference stub is rejected
#   (rejected_invariant(reference_target_modified)) unless it is LOSSLESS byte or structural.
```

## Requirements

| ID | EARS requirement |
|---|---|
| CC-001 | THE SYSTEM SHALL represent every compressor by a `CompressorSpec` plus `applicable()` and `compress()`, and every LOSSLESS compressor additionally by `decode()`. |
| CC-002 | THE SYSTEM SHALL run a compressor only when it is enabled (`compressors.<id>.enabled`) and available; its kind and equivalence SHALL NOT gate execution, and SHALL be shown with the compressor (UI-003). A compressor whose kind is not LOSSLESS (or whose LOSSLESS equivalence is not backed by the contract test of CC-015) SHALL never be enabled by default. THE dashboard SHALL offer the shortcut "Lossless only", which switches off every enabled compressor whose kind is not LOSSLESS (UI-004). THE request's `policy` field SHALL record `LOSSLESS_ONLY` when every enabled compressor is LOSSLESS, and `LOSSY_ALLOWED` otherwise. (S4 SCR-001.) |
| CC-003 | THE SYSTEM SHALL apply an enabled and permitted compressor to a segment only if all filters pass, `applicable()` returns true, and the acceptance gate passes (enabled ≠ forced). |
| CC-004 | WHEN a compressor's output does not reduce the segment's estimated tokens by at least `max(min_gain_tokens, ceil(t_in × min_gain_ratio))` (defaults 4 and 0.01), THE SYSTEM SHALL retain the previous text. |
| CC-005 | THE SYSTEM SHALL ensure that the estimated tokens of every forwarded segment, and of the request as a whole, are less than or equal to the original. |
| CC-006 | THE output of a segment-scope compressor for a segment SHALL depend only on the segment's text, its `SegmentView`, the effective compression config and the compressor versions. THE output of a request-scope compressor declared `prefix_stable` SHALL depend only on segments and tool records at or before that segment. No compressor SHALL depend on time, randomness, locale or host. |
| CC-018 | WHEN a compressor declared `prefix_stable: false` changes a segment, THE SYSTEM SHALL record `history_rewritten: true` for the request, and THE UI SHALL mark such compressors as "may invalidate provider cache". |
| CC-007 | IF a compressor output does not contain every protected span's text unchanged and in order, THEN THE SYSTEM SHALL reject that output (`rejected_invariant`). |
| CC-008 | IF a compressor raises or exceeds `compression.per_call_timeout_ms` (default 200), THEN THE SYSTEM SHALL keep the previous text and record `failed` with the reason. In-process calls are not preempted: a call that returns after the timeout has its result discarded (`failed(timeout)`). Protection against non-terminating compressors comes from their complexity requirements; a compressor of `cost_class: expensive` needs a design that can be preempted. |
| CC-022 | THE engine SHALL skip a compressor for a segment whose estimated tokens are below `max(compressor min_tokens, compression.min_segment_tokens)`, with `compression.min_segment_tokens` defaulting to 64 (POLICY, provisional until E5b), recording `too_small`. |
| CC-023 | WHEN a TOOL_RESULT segment's tool name cannot be resolved (CM-006), THE engine SHALL treat it as a verbatim tool: skip with reason `verbatim_tool` and detail `unresolved`, except for compressors with equivalence `reference` (CC-021). |
| CC-024 | THE engine SHALL keep an in-memory cache of segment-scope compressor results, bounded by `compression.result_cache_mb` (default 64; `0` disables it) with least-recently-used eviction. The cache key SHALL contain every input CC-006 allows (compressor id and version, the compressor's effective config, the `SegmentView` and the full segment text). THE engine SHALL apply its checks (CC-005, CC-007) to a cached result as to a computed one, SHALL record the result in `CompressorStats` exactly as if computed, and SHALL record cache hits and misses per compressor in the trace. |
| CC-009 | THE engine SHALL order compressors by `(stage, id)` and SHALL stop processing a segment after an accepted `terminal` compressor. |
| CC-010 | WHEN a compressor's `requires` modules are not importable, THE SYSTEM SHALL report it as `unavailable(<module>)` in the registry API, UI and doctor, and SHALL skip it with that reason. |
| CC-011 | THE registry SHALL be an explicit list in `tokli.compression.registry`; adding a compressor SHALL require only a new module and one registry entry. |
| CC-012 | WHEN a compressor is invoked (considered), THE SYSTEM SHALL record its per-request statistics as defined for `CompressorStats` (TOKLI_TELEMETRY_AND_COST §2). |
| CC-013 | WHEN a compressor is skipped for a segment, THE SYSTEM SHALL increment the skip-reason counter for that compressor in the request's statistics. |
| CC-014 | WHEN the request's compression time budget (`compression.request_budget_ms`, default 50, a provisional POLICY value until E9 and dogfood data exist) is exhausted, THE SYSTEM SHALL skip the remaining compressor invocations with reason `budget_exhausted`, count the skips per compressor (`skipped_budget`), and SHALL NOT fail the request. The budget is a runtime control, not an acceptance criterion for a compressor (TOKLI_TEST_STRATEGY §8). |
| CC-015 | EVERY LOSSLESS compressor SHALL ship a property test proving its declared equivalence (segment decode for `byte`/`structural`; whole-request decode plus reference integrity for `reference`), and EVERY SELECTIVE compressor SHALL ship a test per declared guarantee (contract test fails otherwise). |
| CC-016 | WHEN `compression.verify_lossless` is true (default true in tests and debug, false in normal serving), THE SYSTEM SHALL decode each accepted LOSSLESS output and reject mismatches. |
| CC-017 | THE compression packages SHALL NOT import protocol, upstream, auth, HTTP, pricing, telemetry-storage or UI modules. |
| CC-019 | WHILE a reference stub is part of the forwarded request, THE SYSTEM SHALL ensure that the named target segment precedes the stub in the same request and that the target's forwarded text equals its original text under byte or structural equivalence. IF any later transformation would violate this, THEN THE SYSTEM SHALL reject that transformation with `rejected_invariant(reference_target_modified)`. This check SHALL always run, independent of `verify_lossless`. |
| CC-020 | EVERY compressor SHALL declare its behavioural `assumptions`. A compressor with `default_enabled: true` SHALL have an evaluation record (SPEC 012, QE-016) that covers every declared assumption with verdict `no_measurable_damage`, or a `provisional` record permitted by QE-016. Whether the user may enable a compressor SHALL NOT depend on evaluation records. |
| CC-021 | THE engine SHALL apply the `verbatim_tools` filter to every compressor except (a) those with equivalence `reference`, because a reference stub leaves the original bytes verbatim in the target segment, and such compressors SHALL declare the assumption `quotes_from_reference_target`; and (b) a compressor whose option `compressors.<id>.apply_to_verbatim_tools` is true. That option SHALL default to false, SHALL exist only for compressors that declare it, and SHALL NOT be true by default for any compressor. (S8a SCR-001.) |

## Invariants (property-tested)
Token non-increase (CC-005) · determinism and context-freedom (CC-006) · protected spans (CC-007) ·
attribution sum (TOKLI_TELEMETRY_AND_COST §2) · policy (CC-002).

## Failure behaviour
A compressor failure never fails the request. An engine failure is a stage failure (PL-005), so
the request is relayed with no compression patches.

## Observability
Per-compressor aggregates in the `transform.compression` span. With `telemetry.detail: segment`,
each invocation is logged as `(segment_id, kind, compressor, decision, t_in, t_out, ms, reason)` — no text.

## Acceptance criteria
- AC-CC-1 (CC-002): a registry with fake LOSSY and UNKNOWN compressors that fail the test when called → green while they are disabled (their default). Enabled, each is called. The request's `policy` reads `LOSSLESS_ONLY` with only LOSSLESS compressors enabled, `LOSSY_ALLOWED` otherwise.
- AC-CC-2 (CC-003): an enabled compressor whose `applicable()` is false is never called with `compress()`.
- AC-CC-3 (CC-004/005): a compressor returning longer text is rejected. A Hypothesis run of 10k random texts through all registered compressors shows no increase.
- AC-CC-4 (CC-006): a segment compressed alone vs. among 50 random other segments gives the same output. Two engine instances give the same output.
- AC-CC-5 (CC-007): a compressor deleting a protected span is rejected.
- AC-CC-6 (CC-008): raise → `failed`; sleep past timeout → `failed(timeout)`; request succeeds.
- AC-CC-7 (CC-010): a compressor with `requires=("not_a_module",)` shows as `unavailable(not_a_module)` in API/doctor and is never called.
- AC-CC-8 (CC-012/013): stats rows match a hand-computed expectation for a 3-segment × 2-compressor fixture, including skip-reason histograms.
- AC-CC-9 (CC-015): the contract test enumerates the registry and fails if a LOSSLESS compressor has no `prop_<id>_decode_roundtrip` test (or `prop_<id>_decodes_whole_request` for `reference`).
- AC-CC-10 (CC-019): a fake SELECTIVE request compressor that stubs the target of a duplicate reference is rejected with `reference_target_modified`, and the target stays verbatim. A fake structural compressor that changes the target is accepted, and the trace records the chain guarantee as `structural`.
- AC-CC-11 (CC-020): a registry entry with `default_enabled: true` and an assumption without an evaluation record fails the contract test. The same entry with `default_enabled: false` passes, and the user can still enable it.
- AC-CC-12 (CC-021): a TOOL_RESULT from a tool in `verbatim_tools` that duplicates an earlier result is stubbed by `duplicate_tool_results`, while `json_minify` is skipped on it with `verbatim_tool`.
- AC-CC-13 (CC-024): the same request processed twice gives identical forwarded bytes and identical stats, and the second run records only hits. The same text with a different `SegmentView` (e.g. a verbatim tool) or a different compressor config is not served from the cache. The cache never exceeds its bound. With `result_cache_mb: 0` nothing is cached.

## Test scenarios
`test_lossless_only_never_runs_lossy_compressor` · `test_lossy_allowed_runs_selective_and_lossy` ·
`test_unknown_requires_explicit_enable` · `test_enabled_compressor_not_applied_when_not_applicable` ·
`test_longer_output_rejected` · `prop_compression_never_increases_tokens` ·
`prop_compression_is_deterministic` · `test_segment_output_independent_of_other_segments` ·
`prop_protected_spans_preserved` · `test_compressor_exception_is_recorded` · `test_compressor_timeout_is_recorded` ·
`test_missing_dependency_marks_compressor_unavailable` · `test_terminal_stops_chain` · `test_chain_order_by_stage_then_id` ·
`test_compressor_stats_expected_fixture` · `prop_marginal_savings_sum_to_total` · `test_budget_exhaustion_skips` ·
`test_registry_contract_every_lossless_has_roundtrip_property` · `test_verify_lossless_rejects_decode_mismatch` ·
`test_import_contracts` · `test_request_scope_runs_before_segment_scope` · `test_history_rewritten_flag` ·
`test_reference_target_integrity_enforced` · `test_every_compressor_declares_assumptions` ·
`test_registry_default_enabled_requires_eval_record` · `test_verbatim_tools_exempt_only_reference_equivalence` ·
`test_verbatim_opt_in_applies_compressor_to_verbatim_tool` · `test_verbatim_opt_in_defaults_off` ·
`test_verbatim_opt_in_only_for_declaring_compressors` ·
`test_min_segment_tokens_default` · `test_unresolved_tool_name_treated_as_verbatim` · `test_late_result_discarded_as_timeout` ·
`test_result_cache_hit_gives_identical_output` · `test_result_cache_key_includes_view_and_config` ·
`test_result_cache_bounded` · `test_result_cache_off`

## Open questions
- Q9: Should `min_gain_ratio` differ per compressor (spec field) rather than being global? Start global and revisit with S4 data.
