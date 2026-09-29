# SPEC 007 — Analysis / transformation pipeline and extension seams

Status: Draft · Slice: S1 · Related: ARCH §4

## Purpose
Provide one small, ordered mechanism through which every pre-forward analysis and transformation
runs. Future stages (e.g. redaction) must be insertable without touching adapters or compressors.

## Rationale
- Stage ordering rules are checked by the pipeline, not written as comments. Timing and failure isolation are implemented once by the pipeline, not per stage.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 007 rows).

## Stage contract

```python
class Stage(Protocol):
    id: str                                   # unique, dotted: "analyze.reminders"
    kind: Literal["analyzer", "transformer"]
    def run(self, req: CanonicalRequest, ctx: StageContext) -> StageResult: ...

StageResult(protected_spans: dict[segment_id, list[Span]] = {},   # analyzers
            features: dict[segment_id, Features] = {},            # analyzers
            patches: list[Patch] = [],                            # transformers
            report: Any = None)                                   # stage-specific record
```

`StageContext` provides: `request_id`, effective config snapshot, `TokenCounter`, a clock, a
trace handle and a remaining time budget. It provides **no** HTTP, auth, storage or protocol access.

## Requirements

| ID | EARS requirement |
|---|---|
| PL-001 | THE SYSTEM SHALL run the configured stages in the configured order for every transformable request. |
| PL-002 | WHEN the configured stage list names an unknown stage, or places a transformer before an analyzer, THE SYSTEM SHALL refuse to start and name the offending stages. (A general `must_precede` declaration is introduced only in the slice that adds the first stage with a real ordering constraint, e.g. redaction; Phase 0.1 decision C1.) |
| PL-003 | THE analyzer stages SHALL NOT produce patches; THE transformer stages SHALL NOT alter protected spans (verified by the pipeline, see CC-007). |
| PL-004 | WHEN a transformer returns patches, THE pipeline SHALL apply them to the working segment texts before the next stage runs. |
| PL-005 | IF a stage raises or exceeds its time budget, THEN THE pipeline SHALL discard that stage's result, record `stage_exception(<id>)` or `stage_timeout(<id>)`, and continue with the next stage. |
| PL-006 | THE pipeline SHALL record a trace span per stage with duration and outcome. |
| PL-007 | WHEN a new stage is added, THE protocol adapters and compressors SHALL NOT require modification (checked by the import contracts and a test stage fixture). |
| PL-008 | THE default stage list SHALL be `[analyze.reminders, analyze.features, transform.compression]`. |

## v1 stages

| Id | Kind | Responsibility |
|---|---|---|
| `analyze.reminders` | analyzer | Marks `<system-reminder>…</system-reminder>` spans (and configured literal markers) as protected in USER_TEXT and TOOL_RESULT segments. Matching rule: a span runs from an opening tag to the **nearest** following closing tag of the same name (non-greedy), may cross line breaks, and includes both tags. An opening tag with no later closing tag produces **no** span. Tags are matched literally and case-sensitively. Nested opening tags are not interpreted, so the first closing tag ends the span. |
| `analyze.features` | analyzer | Computes cheap per-segment features (SPEC 011). |
| `analyze.tool_resources` | analyzer | Derives `resource_key`/`action` per tool record from `pruning.tool_semantics` config (SPEC 019, PR-006). Added in S8, when the first consumer (superseded pruning) arrives. |
| `transform.compression` | transformer | Runs the compression engine (SPEC 009). |

## Acceptance criteria
- AC-PL-1 (PL-002): a config listing `transform.compression` before `analyze.reminders` → startup error naming both stages. A config naming `analyze.unknown` → startup error naming it.
- AC-PL-2 (PL-005): a stage raising `RuntimeError` → its patches are absent, later stages still run, the reason is recorded.
- AC-PL-3 (PL-007): a test-only transformer that uppercases USER_TEXT is inserted through config alone. The Anthropic, Chat and Responses fixtures render correctly with no adapter change.
- AC-PL-4 (PL-003): an analyzer returning patches → pipeline error `analyzer_returned_patches` (programming error surfaced in tests).

## Test scenarios
`test_stage_order_from_config` · `test_invalid_stage_order_fails_startup` ·
`test_stage_exception_isolated` · `test_stage_timeout_isolated` · `test_patches_visible_to_later_stages` ·
`test_new_transformer_needs_no_adapter_change` · `test_analyzer_cannot_patch` · `test_reminder_spans_protected`

## Open questions
None blocking.
