# SPEC 005 — OpenAI Responses adapter (Codex)

Status: Draft · Slice: S5 · Related: SPEC 001, 002

## Purpose
Map `POST /v1/responses` to canonical segments and back. Extract usage.

## Rationale
- Tool outputs appear as several item types (`function_call_output`, `custom_tool_call_output`, …) that share the shape `call_id` + `output`. Shape-based detection survives new item types.
- Codex sets `store:false`, resends the full history and sends `prompt_cache_key`. Prefix determinism matters.
- Codex tool shapes differ between Windows (PowerShell `shell_command` strings) and Unix (argv).
- `instructions` and `tools` stay untouched.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 005 rows).

## Segment mapping

| Wire location | Kind | Mutable (v1 default) |
|---|---|---|
| `instructions` | SYSTEM | no |
| `input` (string) | USER_TEXT | yes |
| `input[*]` `{type:"message", role:"user"}` → `content[*]` `type:"input_text"` `.text` (and string `content`) | USER_TEXT | yes |
| `input[*]` role `system`/`developer` message text | SYSTEM | no |
| `input[*]` any item with `call_id` and `output` string → `output` | TOOL_RESULT | yes |
| … `output` list → parts with `type` in {`input_text`, `output_text`, `text`} `.text` | TOOL_RESULT | yes |
| `input[*]` `type:"function_call"` / `custom_tool_call` `arguments`/`input` | TOOL_CALL_ARGS | never |
| `input[*]` `type:"reasoning"` (incl. `encrypted_content`, `summary`) | opaque | never |
| assistant `message` / `output_text` | ASSISTANT_TEXT | never |
| `tools[*].description` | TOOL_DESCRIPTION | no |
| images, files, unknown item types, `previous_response_id`, `store`, `prompt_cache_key`, `include`, all others | opaque | never |

## Requirements

| ID | EARS requirement |
|---|---|
| OR-001 | WHEN Tokli receives a Responses request, THE SYSTEM SHALL preserve the externally observable Responses contract. |
| OR-002 | THE adapter SHALL identify tool outputs by shape (an item with `call_id` and an `output` that is a string or a list), not by an allow-list of `type` values. |
| OR-003 | THE adapter SHALL resolve each tool output's `call_id` to the `name` of the matching `function_call`/`custom_tool_call` item earlier in the same `input`. |
| OR-004 | WHEN `previous_response_id` is present, THE SYSTEM SHALL process only the items present in this request and SHALL NOT attempt to resolve earlier server-side state. |
| OR-005 | THE usage parser SHALL read `usage.input_tokens`, `usage.input_tokens_details.cached_tokens`, `usage.output_tokens`, `usage.output_tokens_details.reasoning_tokens` from non-streaming responses, and from the `response.completed` event when streaming. |
| OR-006 | IF a stream ends with `response.failed`/`error` or without `response.completed`, THEN THE SYSTEM SHALL record `usage_source: unavailable`. |

## Acceptance criteria
- AC-OR-1: Responses compat fixtures (incl. Codex Windows + Unix shapes, reasoning with `encrypted_content`) pass the CM/PX invariants.
- AC-OR-2: a new, invented tool-output item type with `call_id` + `output` is treated as TOOL_RESULT.
- AC-OR-3: `reasoning` items are byte-identical after rendering (checked on the JSON value).
- AC-OR-4: growing-conversation determinism: turn N and turn N+1 bodies compress the shared prefix to identical values.

## Test scenarios
`test_responses_segment_mapping` · `test_responses_tool_output_detected_by_shape` ·
`test_responses_tool_name_resolution` · `test_responses_reasoning_untouched` ·
`test_responses_previous_response_id_passthrough` · `test_responses_usage_non_stream` ·
`test_responses_usage_stream_completed` · `test_responses_usage_stream_failed_unavailable` ·
`test_growing_conversation_prefix_stays_identical`

## Open questions
- Q6 (E6): ChatGPT-subscription Codex (`chatgpt.com/backend-api/codex/responses`) is a different upstream with a different auth header set. Out of scope until E6.
