# SPEC 001 — Canonical request model and round-trip

Status: Draft · Slice: S1 (Anthropic subset), S5/S7 (OpenAI) · Related: ARCH §3
Approved for S1 (2026-09-30): CM-001…CM-012 (Anthropic). CM-013 deferred to S4.
Approved for S4 (2026-10-03): CM-013 (Anthropic).

## Purpose
Give every stage a protocol-independent, minimal view of the request's **text values**, and
guarantee that a transformed request can be rebuilt without losing anything else.

## Rationale
- Rewriting only string values, and leaving tool schemas, `cache_control` and all other structure untouched, is the smallest surface on which a transformation can be shown not to break a protocol.
- Flattening a conversation into one string, rebuilding messages or reordering blocks are known ways to corrupt a request. The locator-based patch model (CM-002, CM-004) makes them impossible by construction.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 001 rows).

## Terminology
- **Segment:** one JSON string value in the request that a stage may read, and possibly replace.
- **Locator:** RFC 6901 JSON Pointer to that string value in the original parsed body.
- **Opaque:** any part of the request not exposed as a mutable segment.
- **Patch:** `(segment_id, new_text, produced_by)`.

## Data model

```text
CanonicalRequest(protocol, provider, endpoint, model?, stream, segments[], original_json, original_bytes)
Segment(id, index, kind, role?, text, locator, mutable, attrs{tool_name?, tool_call_id?, is_error?,
        cache_breakpoint_after?}, protected: Span[])
SegmentKind = SYSTEM | TOOL_DESCRIPTION | USER_TEXT | ASSISTANT_TEXT | TOOL_CALL_ARGS | TOOL_RESULT | OTHER_TEXT
Span(start, end, reason)            # [start, end) character offsets into Segment.text
```

`mutable` is decided by the adapter (protocol eligibility) **and** by config
(`compression.segment_kinds`, default `{TOOL_RESULT, USER_TEXT}`). Assistant-side content,
`TOOL_CALL_ARGS`, thinking, reasoning, images and documents are never mutable in v1, whatever the config says.

## Requirements

| ID | EARS requirement |
|---|---|
| CM-001 | WHEN no patch is produced for a request, THE SYSTEM SHALL forward the original request bytes unchanged. |
| CM-002 | WHEN patches are applied, THE SYSTEM SHALL produce a body whose parsed JSON differs from the original only at the locators of patched segments. |
| CM-003 | THE adapter SHALL expose unknown fields, unknown block/item types and non-text content only as opaque data that is re-emitted unchanged. |
| CM-004 | THE SYSTEM SHALL preserve the count, order and type of messages, content blocks and input items. |
| CM-005 | THE adapter SHALL assign each segment a stable `id`, a document-order `index`, a `kind`, its `role` where applicable, and its locator. |
| CM-006 | WHEN a tool result can be linked to its tool call within the same request, THE adapter SHALL set `attrs.tool_name` and `attrs.tool_call_id`. |
| CM-007 | WHEN the body is not valid JSON, is not an object, or does not match the protocol's minimal shape, THE SYSTEM SHALL relay the request verbatim and record `passthrough(parse_error)`. |
| CM-008 | WHILE a request carries a `content-encoding` header, THE SYSTEM SHALL relay it verbatim and record `passthrough(content_encoding)`. |
| CM-009 | THE SYSTEM SHALL NOT mark as mutable: assistant-role content, thinking/redacted_thinking blocks, encrypted reasoning, tool-call arguments, image/audio/file/document parts, `cache_control`, tool `name`/`input_schema`/`parameters`. |
| CM-010 | THE `tokli.domain` package SHALL NOT import any protocol, provider, HTTP or storage module. |
| CM-011 | WHEN re-serialising a patched body, THE SYSTEM SHALL emit UTF-8 JSON with non-ASCII characters unescaped and SHALL set `content-length` from the new body. |
| CM-012 | WHEN the request body exceeds `limits.max_transform_bytes` (default 32 MiB), THE SYSTEM SHALL relay it verbatim and record `passthrough(too_large)`. |
| CM-013 | THE adapter SHALL expose, read-only, one `ToolRecord(call_id, name, arguments (parsed JSON or raw string), index, result_segment_ids)` per tool call in the request, so that analyzers and request-scope compressors can reason about tool history without protocol knowledge. |

## Invariants
- `render(original, []) == original_bytes` (byte identity).
- `set(changed_pointers(parse(render(o, P)), o)) == {p.locator for p in P if p.new_text != segment.text}`.

## Failure behaviour
Any exception in `parse` or `render` → verbatim relay of original bytes, reason recorded, request continues.

## Observability
Trace spans `parse` and `render` with segment counts, mutable counts, patch count, and body bytes before and after.

## Acceptance criteria
- AC-CM-1 (CM-001): every compat fixture with compression disabled → upstream receives byte-identical bodies.
- AC-CM-2 (CM-002, CM-004): for every fixture with forced dummy patches on all mutable segments, the JSON diff touches only patched locators, and the structure is identical.
- AC-CM-3 (CM-003): a fixture with an invented block type `{"type":"future_block",…}` and a top-level `x_future` field round-trips unchanged.
- AC-CM-4 (CM-006): Anthropic `tool_result` → `tool_name` from the preceding `tool_use`; Chat `role:"tool"` via `tool_call_id`; Responses output items via `call_id`.
- AC-CM-5 (CM-007, CM-008, CM-012): malformed JSON, gzip-encoded body and oversize body are each relayed verbatim with the correct reason.
- AC-CM-6 (CM-009): with config `segment_kinds` set to every kind, no forbidden part becomes mutable.
- AC-CM-7 (CM-010): import-linter contract.

## Test scenarios
`test_passthrough_forwards_original_bytes` · `test_render_changes_only_patched_values` ·
`test_structure_preserved_after_compression` · `test_unknown_block_types_roundtrip` ·
`test_tool_name_resolution_per_protocol` · `test_malformed_body_relayed_verbatim` ·
`test_content_encoded_body_relayed_verbatim` · `test_oversize_body_relayed_verbatim` ·
`test_forbidden_parts_never_mutable` · `test_import_contracts` · `test_patched_body_utf8_and_length` ·
`test_tool_records_per_protocol`

## Open questions
- Q1: Should `SYSTEM` and `TOOL_DESCRIPTION` segments be exposed as *mutable* at all in v1? The proposal is: exposed as segments (analysis and metrics), not mutable (pending E2/E5).
