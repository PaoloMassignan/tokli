# SPEC 000 — Product scope

Status: Draft for review · Owner: product · Related: `TOKLI_SCOPE.md`, `TOKLI_VISION.md`

## Purpose
Turn the scope boundaries into testable statements, so scope creep shows up as a failing test or
a spec change rather than an accident.

## Requirements

| ID | EARS requirement |
|---|---|
| SC-001 | THE SYSTEM SHALL modify outbound requests only through registered pipeline stages whose purpose is token reduction (v1: the compression stage). |
| SC-002 | THE SYSTEM SHALL NOT block, reject or refuse a request on the basis of its content. |
| SC-003 | THE SYSTEM SHALL NOT add tools, messages, system text or cache breakpoints to a client request. |
| SC-004 | THE SYSTEM SHALL NOT modify responses or response streams. |
| SC-005 | THE SYSTEM SHALL NOT persist prompt or response content unless debug-content mode is enabled (see OB-008). |
| SC-006 | THE SYSTEM SHALL NOT perform outbound network connections other than to configured upstream endpoints. |
| SC-007 | WHEN a request is not eligible for transformation, THE SYSTEM SHALL relay it unchanged. |

## Non-requirements
Everything listed as a non-goal in `TOKLI_SCOPE.md`.

## Acceptance criteria
- AC-SC-1: The only registered transformer in v1 is `transform.compression` (SC-001).
- AC-SC-2: No code path returns 4xx/5xx based on content (SC-002): static review + `test_no_content_based_rejections`.
- AC-SC-3: For all compat fixtures, the forwarded body contains no keys, blocks or items absent from the original (SC-003).
- AC-SC-4: Response bytes equal upstream bytes (SC-004).
- AC-SC-5: Socket guard shows only upstream + loopback connections (SC-006).

## Test scenarios
`test_only_compression_transformer_registered` · `test_no_content_based_rejections` ·
`test_forwarded_body_adds_no_structure` · `test_response_bytes_identical` ·
`test_no_outbound_connections_except_upstream` · `test_passthrough_forwards_original_bytes`
