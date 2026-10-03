# ADR 0010 — Request-scope compressors and reference integrity

Status: accepted (S4, 2026-10-03; approved at S4 Gate 1) · Related: SPEC 001 CM-013, SPEC 009
CC-001, CC-019, CC-021, SPEC 019

## Context

`duplicate_tool_results` decides about a segment by looking at other segments of the same request
(an earlier identical result). The S1 contract (`applicable` and `compress` on one text) cannot
express that. Its stubs also create a dependency: the target must keep its content for as long as
a stub names it (CC-019).

## Decision

- **`ToolRecord`** (CM-013), in `tokli.domain`: `call_id`, `name`, `arguments` (parsed JSON or the
  raw string), `index`, `result_segment_ids`. The Anthropic adapter builds the records, which are
  read-only.
- **A second compressor protocol, `RequestCompressor`**, in `tokli.compression.contract`:
  - `plan(refs, texts, tools, count)` returns proposals `(segment_id, new_text)`, where each ref
    carries the segment id, its `SegmentView`, its call id and whether the segment is the whole
    content of its result;
  - a proposal with no new text leaves the segment alone and carries a short reason code
    (`not_applicable(<code>)` in the stats, metadata only; added after the 2026-10-03 dogfood,
    where the trace could not say why nothing was stubbed);
  - LOSSLESS `reference` compressors also implement `decode_request(texts, refs)`;
  - two concrete behaviours (segment and request scope) justify the seam (CLAUDE.md §5).
- **Engine order:**
  - request-scope compressors first, ordered by `(stage, id)` (PR-010);
  - each proposal passes the same filters and acceptance gate as a segment result, and is
    attributed to its compressor;
  - segment-scope compressors then run on the resulting texts.
- **Reference integrity (CC-019):** the engine keeps a map from each target to its stubs. A later
  change to a target is accepted only from a compressor with equivalence `byte` or `structural`;
  any other change is `rejected_invariant(reference_target_modified)`. The check runs on the
  final output of every invocation, cache hits included, independent of `verify_lossless`.
- **Policy (SCR-001):** the engine's policy filter is removed. Enabling a compressor is the only
  gate; the request's `policy` is derived from the kinds of the enabled compressors.

## Alternatives considered

- **Running pruners as a separate pipeline stage outside the engine:** it would duplicate the
  gate, attribution and budget. Rejected.
- **Letting a request compressor patch any segment directly:** it would bypass the per-segment
  invariants. Rejected.

## Consequences

- **The result cache (CC-024) stays segment-scope only:** a request plan depends on other
  segments.
- **New property test** `prop_duplicate_pruning_decodes_whole_request`; the CC-015 contract test
  checks that every `reference` compressor has it.
- **CompressorStats is unchanged;** the engine result gains `reference_stubs`.
