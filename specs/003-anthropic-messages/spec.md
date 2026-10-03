# SPEC 003 — Anthropic Messages adapter

Status: Draft · Slice: S1 (request), S2 (usage) · Related: SPEC 001, 002
Approved for S1 (2026-09-30): AN-001…AN-004, AN-008. Usage (AN-005…AN-007, AN-009) in S2.
Approved for S2 (2026-10-02): AN-005…AN-007, AN-009, AN-010.

## Purpose
Map `POST /v1/messages` requests to canonical segments and back, and extract provider usage from
responses and SSE streams, without changing the externally observable Anthropic contract.

## Rationale
- Tool results are nested inside user-role `tool_result` blocks and must be reachable. `cache_control`, `input_schema` and tool `name` never change.
- `system` and tool descriptions are exposed read-only in v1 (SPEC 001 Q1).
- Claude Code injects `<system-reminder>` blocks into user turns. They are protected spans (SPEC 007).
- Text blocks are never moved relative to `tool_result` blocks.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 003 rows).

## Segment mapping

| Wire location | Segment kind | Mutable (v1 default) |
|---|---|---|
| `system` (string) / `system[*].text` | SYSTEM | no |
| `tools[*].description` | TOOL_DESCRIPTION | no |
| `messages[i]` role `user`, `content` string | USER_TEXT | yes |
| `messages[i]` role `user`, `content[j]` `type:"text"` `.text` | USER_TEXT | yes |
| `messages[i]` role `user`, `content[j]` `type:"tool_result"`, `content` string | TOOL_RESULT | yes |
| … `tool_result.content[k]` `type:"text"` `.text` | TOOL_RESULT | yes |
| `messages[i]` role `assistant`, `type:"text"` | ASSISTANT_TEXT | never |
| `tool_use.input`, `thinking`, `redacted_thinking`, `image`, `document`, `search_result`, server-tool blocks, unknown types | opaque | never |

`attrs.cache_breakpoint_after = true` when the containing block carries `cache_control`.
`attrs.is_error` mirrors `tool_result.is_error`.

## Requirements

| ID | EARS requirement |
|---|---|
| AN-001 | WHEN Tokli receives a supported Anthropic Messages request, THE SYSTEM SHALL preserve the externally observable Anthropic API contract (request structure per CM-002/CM-004, response per PX-005/PX-006). |
| AN-002 | THE adapter SHALL expose segments exactly per the mapping table, and SHALL treat every other part as opaque. |
| AN-003 | THE adapter SHALL resolve `tool_result.tool_use_id` to the `name` of the matching `tool_use` block in an earlier assistant message of the same request, and set `attrs.tool_name`. |
| AN-004 | THE adapter SHALL preserve every block attribute other than the patched string, including `cache_control`, `citations`, `is_error` and `tool_use_id`. |
| AN-005 | WHEN the request has `stream: false` or no `stream`, THE usage parser SHALL read `usage.{input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens, cache_creation.ephemeral_5m_input_tokens, cache_creation.ephemeral_1h_input_tokens}` from the JSON response. |
| AN-006 | WHEN the request streams, THE usage parser SHALL read usage from `message_start.message.usage` and the last `message_delta.usage` in a passive copy of the stream, and SHALL never delay or alter the client stream. |
| AN-007 | IF the usage parser cannot obtain usage from the response or stream, THEN THE SYSTEM SHALL record `usage_source: unavailable` with the reason code `usage_unavailable(<why>)`, `<why> ∈ {upstream_status, content_encoding, buffer_limit, parse_error, no_usage, client_disconnected}` (TOKLI_OBSERVABILITY §4), and continue. |
| AN-010 | WHEN a stream ends after `message_start` without a final `message_delta` (error event, upstream break or client disconnect), THE SYSTEM SHALL record the usage seen so far with `usage_source: provider_partial`. The input categories (complete at `message_start`) are used for calibration; the output figure is labelled partial. |
| AN-008 | THE SYSTEM SHALL relay `POST /v1/messages/count_tokens` and all other `/v1/*` endpoints verbatim in v1. |
| AN-009 | THE usage parser SHALL bound its memory to `limits.usage_parser_buffer` (default 1 MiB of unparsed event data, or of a non-streaming response body) and SHALL stop parsing, not buffering, when the bound is hit. |

## Invariants
- Block order inside every `content` array is unchanged (CM-004), so `tool_result`-first ordering is always preserved.
- The number of `cache_control` markers in the forwarded request equals the number in the original.

## Failure behaviour
Parser errors on the request → verbatim (CM-007). Usage parser errors → `unavailable` with a reason (AN-007). A stream cut short → `provider_partial` (AN-010).

## Observability
Trace: segment counts by kind, `tool_name` resolution rate, number of cache breakpoints, usage source.

## Acceptance criteria
- AC-AN-1: all Anthropic compat fixtures (see TEST_STRATEGY §4) pass the invariant tests.
- AC-AN-2: `tool_name` resolved for 100 % of fixture tool results with a matching `tool_use` in the request; unresolved ones get `tool_name: null` (no guess).
- AC-AN-3: usage extracted exactly from non-stream and stream fixtures, including a stream that ends with an `error` event (usage from `message_start` only, `usage_source: provider_partial`, AN-010).
- AC-AN-6 (AN-007): each `<why>` is produced by a matching fixture (4xx response, encoded body, oversized body, malformed JSON, response without usage, client disconnect before `message_start`).
- AC-AN-4: the stream relay timing test (AC-PX-3) passes with the usage tee active.
- AC-AN-5: `count_tokens` and `models` requests are relayed byte-identically.

## Test scenarios
`test_anthropic_segment_mapping` · `test_anthropic_tool_name_resolution` ·
`test_anthropic_block_attributes_preserved` · `test_anthropic_cache_control_count_preserved` ·
`test_anthropic_usage_non_stream` · `test_anthropic_usage_stream` ·
`test_anthropic_usage_stream_with_error_event` · `test_usage_parser_failure_is_unavailable` ·
`prop_usage_stream_any_chunk_split` · `test_stream_causal_relay` (with the usage tee) ·
`test_usage_parser_memory_bounded` · `test_anthropic_other_endpoints_verbatim`

## Open questions
- ~~Q3~~ **Resolved 2026-10-03 (E4, 7 streamed Claude Code requests, OAuth):** yes. Every `message_delta.usage` repeats `input_tokens`, `cache_creation_input_tokens` and `cache_read_input_tokens` cumulatively, plus `output_tokens`, and also carries `iterations` and `output_tokens_details` (not used by Tokli). It does **not** carry the `cache_creation` 5m/1h split; the split comes from `message_start` and is kept when the delta's total matches it. Event sequence observed: `message_start`, `content_block_start`, `ping`, `content_block_delta`…, `content_block_stop`, `message_delta`, `message_stop`. Original question: is the cumulative input usage repeated in `message_delta` in the current API version? The parser takes the last non-null value per field. The fixtures must be confirmed. E4 (S2) is run with Tokli itself: the trace records SSE event types and usage fields (metadata only) for a streamed Claude Code session and a non-streaming request. A mid-stream `error` event cannot be triggered on purpose; that case stays fixture-based, from the documented event shape.
- Q4: Should `count_tokens` bodies be compressed with the same config so the client's context accounting matches what is sent? This is a product decision (see README open questions).
