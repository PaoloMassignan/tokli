# SPEC 004 — OpenAI Chat Completions adapter

Status: Draft · Slice: S7 · Related: SPEC 001, 002

## Purpose
Map `POST /v1/chat/completions` to canonical segments and back. Extract usage when the provider
sends it.

## Rationale
- Tool output in Chat Completions lives in `role:"tool"` messages. An adapter that walks only `role:"user"` misses it.
- There is no evidence of Codex using Chat Completions. Chat is used by SDK clients and other tools.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 004 rows).

## Segment mapping

| Wire location | Kind | Mutable (v1 default) |
|---|---|---|
| `messages[i]` role `system`/`developer` (string or `text` parts) | SYSTEM | no |
| `messages[i]` role `user`, string or `{"type":"text"}` part `.text` | USER_TEXT | yes |
| `messages[i]` role `tool`, string or `text` part | TOOL_RESULT | yes |
| `messages[i]` role `assistant` `content` | ASSISTANT_TEXT | never |
| `tool_calls[*].function.arguments` | TOOL_CALL_ARGS | never |
| `tools[*].function.description` | TOOL_DESCRIPTION | no |
| image/audio/file parts, unknown parts, all other fields | opaque | never |

## Requirements

| ID | EARS requirement |
|---|---|
| OC-001 | WHEN Tokli receives a Chat Completions request, THE SYSTEM SHALL preserve the externally observable Chat Completions contract. |
| OC-002 | THE adapter SHALL expose segments exactly per the mapping table. |
| OC-003 | THE adapter SHALL resolve `role:"tool"` messages' `tool_call_id` to the `function.name` of the matching earlier `tool_calls` entry. |
| OC-004 | THE SYSTEM SHALL NOT add, remove or modify `stream_options`. |
| OC-005 | WHEN the response is non-streaming, THE usage parser SHALL read `usage.prompt_tokens`, `usage.completion_tokens`, `usage.prompt_tokens_details.cached_tokens`, `usage.completion_tokens_details.reasoning_tokens`. |
| OC-006 | WHEN streaming AND the client requested `stream_options.include_usage: true`, THE usage parser SHALL read usage from the final chunk that carries `usage`; OTHERWISE THE SYSTEM SHALL record `usage_source: unavailable (not_requested_by_client)`. |
| OC-007 | THE usage parser SHALL treat `data: [DONE]` as end of stream and SHALL tolerate comment lines and unknown fields. |

## Acceptance criteria
- AC-OC-1: Chat compat fixtures pass the CM/PX invariants.
- AC-OC-2: tool-result compression reaches `role:"tool"` messages: a fixture whose only compressible content is a pretty-printed JSON `role:"tool"` message is compressed.
- AC-OC-3: the forwarded body never contains `stream_options` unless the original did, with identical value.
- AC-OC-4: usage extraction across the non-stream, stream with usage, and stream without usage cases.

## Test scenarios
`test_chat_segment_mapping` · `test_chat_tool_messages_are_mutable` · `test_chat_tool_name_resolution` ·
`test_chat_stream_options_untouched` · `test_chat_usage_non_stream` · `test_chat_usage_stream_with_include_usage` ·
`test_chat_usage_stream_without_include_usage_unavailable`

## Open questions
- Q5: Some Chat-compatible providers put usage in every chunk. The parser takes the last value seen. Is that acceptable? Proposed: yes, and documented.
