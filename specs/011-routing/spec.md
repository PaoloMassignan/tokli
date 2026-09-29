# SPEC 011 — Compression routing (cheap classification before transformation)

Status: Draft · Slice: S1 (minimal), S4/S8 (features for more compressors)

## Purpose
Decide cheaply, per segment, which compressors are worth attempting, and prefer pass-through when
nothing safe applies. In Tokli, "routing" is the engine's filter chain (SPEC 009) plus the
features computed by `analyze.features`. There is no separate router that picks a single
strategy.

## Rationale
- Routing is a cheap, deterministic filter chain over structural features. One-strategy-per-block routing, learned classifiers and prompt-marker heuristics are excluded.
- Structural detectors must not fire on look-alike text. For example, a diff detector must not swallow text after the last hunk.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 011 rows).

## Features (computed once per mutable segment, cached)

| Feature | Definition (cheap, O(n)) | Used by |
|---|---|---|
| `tokens` | estimate via TokenCounter | min-size filter |
| `json_candidate` | first non-ws char ∈ `{[` and last non-ws char ∈ `}]` | json_minify |
| `grep_lines` | count of lines matching the path:line: pattern (POSIX/Windows/UNC) | search_group |
| `diff_shape` | `diff --git` present, OR (`@@ ` hunk header AND ≥1 `+`/`-` line) | diff_context_trim |
| `leveled_ratio` | fraction of lines containing a log level keyword | log_filter |
| `line_count`, `crlf` | | several |

## Requirements

| ID | EARS requirement |
|---|---|
| RT-001 | THE `analyze.features` stage SHALL compute the features above for every mutable segment in O(n) of its length, without regex backtracking beyond linear bounds. |
| RT-002 | THE engine SHALL evaluate filters in the fixed order of SPEC 009 and SHALL call `applicable()` only after all cheap filters pass. |
| RT-003 | WHEN no compressor accepts a transformation for any segment, THE SYSTEM SHALL forward the original bytes and record `passthrough(no_applicable_compressor)` or `passthrough(no_gain)`. |
| RT-004 | WHEN a compressor's `cost_class` is `moderate` or `expensive`, THE compressor SHALL implement `applicable()` using features only (no full transformation). |
| RT-005 | THE routing SHALL NOT depend on benchmark prompt markers, learned models or historical telemetry in v1. |
| RT-006 | THE per-request trace SHALL show, per compressor, counts of considered/applicable/accepted and the skip-reason histogram. |

## Acceptance criteria
- AC-RT-1: feature extraction time grows linearly: for inputs of 0.5 MB and 5 MB the time ratio is ≤ 15 (correctness constraint, every commit). The absolute time on a 5 MB segment is recorded by the nightly benchmark and checked against a regression limit once a baseline exists (TOKLI_TEST_STRATEGY §8). It is not a fixed millisecond threshold.
- AC-RT-2: a spy compressor shows `applicable()` is never called for segments below `min_tokens` or in `verbatim_tools`.
- AC-RT-3: a request with only prose segments → `passthrough(no_applicable_compressor)` and upstream receives the original bytes.
- AC-RT-4: the engine's routing inputs are exactly the `Features` fields above, `SegmentView`, spec metadata and the effective config (a test enumerates the filter-chain inputs). A static scan finds no import of an ML framework (`transformers`, `torch`, `onnxruntime`, `sklearn`) under `tokli/`, and no read of telemetry storage from `tokli.compression`.

## Test scenarios
`test_features_linear_time` · `test_cheap_filters_before_applicable` · `test_prose_only_request_passthrough` ·
`test_routing_inputs_closed_and_no_ml` · `test_trace_shows_routing_counts` · `test_grep_feature_windows_paths`

## Open questions
- Q10: Should historical effectiveness (e.g. a compressor's 30-day zero-benefit rate > 95 %) automatically raise its `min_tokens`? Deferred. If adopted, it will be a read-only analyzer input with its own spec, keeping telemetry out of decision code.
