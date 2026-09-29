# SPEC 002 — Transparent proxy and routing

Status: Draft · Slice: S1 · Related: ARCH §6

## Purpose
Accept client traffic on a local port, route it to the correct provider without guessing, and
relay responses and streams without altering them.

## Rationale
- A proxy never guesses the provider for an unknown path.
- Upstream errors reach the client unchanged, with their headers. Streamed upstream errors are visible in Tokli's own logs.
- Tokli never introduces a limit (for example a body-size limit) that the provider does not impose.

Evidence: TOKLI_EVIDENCE.md (hazards and measurements); per-requirement rationale in TOKLI_TRACEABILITY.md (SPEC 002 rows).

## Routing contract

| Client base URL | Requests | Upstream |
|---|---|---|
| `http://127.0.0.1:<port>/anthropic` | `/anthropic/<rest>` | `upstreams.anthropic.base_url` + `/<rest>` |
| `http://127.0.0.1:<port>/openai` (or `/openai/v1`) | `/openai/<rest>` | `upstreams.openai.base_url` + `/<rest>` |

Known transformable endpoints (after prefix removal and canonicalisation of trailing slash and
case; a missing `/v1` is added only for the three known endpoints): `POST /v1/messages`,
`POST /v1/chat/completions`, `POST /v1/responses`. Everything else under a known prefix is
relayed verbatim.

## Requirements

| ID | EARS requirement |
|---|---|
| PX-001 | THE SYSTEM SHALL bind to `127.0.0.1` by default; WHEN configured to bind a non-loopback address, THE SYSTEM SHALL require `--allow-remote` and log a warning at startup. |
| PX-002 | WHEN a request path starts with a configured provider prefix, THE SYSTEM SHALL route it to that provider's upstream; WHEN it matches no prefix, THE SYSTEM SHALL answer 404 with error code `tokli_unknown_route` and a hint listing the configured prefixes. |
| PX-003 | WHEN a request targets a known transformable endpoint, THE SYSTEM SHALL process it through the protocol adapter and pipeline; OTHERWISE THE SYSTEM SHALL relay it verbatim. |
| PX-004 | THE SYSTEM SHALL forward all request headers except hop-by-hop headers (`connection` and every header it names, `keep-alive`, `proxy-connection`, `proxy-authenticate`, `proxy-authorization`, `te`, `trailer`, `transfer-encoding`, `upgrade`; RFC 9110 §7.6.1), `host` and `content-length`, and except the credential headers governed by the auth mode (SPEC 006). |
| PX-005 | THE SYSTEM SHALL relay the upstream status code, headers (except hop-by-hop, and `content-length` when streaming) and body bytes unchanged. |
| PX-006 | WHEN upstream streaming is requested, THE SYSTEM SHALL relay each upstream chunk to the client as soon as it is received, without buffering or modification. |
| PX-007 | WHEN the upstream returns 4xx or 5xx, THE SYSTEM SHALL relay that response verbatim, including when streaming was requested. |
| PX-008 | WHEN the upstream cannot be reached or times out before response headers, THE SYSTEM SHALL answer 502/504 with a JSON body `{"error":{"type":"tokli_upstream_unreachable"|"tokli_upstream_timeout","source":"tokli","request_id":…}}`. |
| PX-009 | WHEN the client disconnects, THE SYSTEM SHALL cancel the upstream request within 1 second. |
| PX-010 | WHEN an internal error occurs in parse, pipeline or render, THE SYSTEM SHALL forward the original request bytes (fail to pass-through). |
| PX-011 | THE SYSTEM SHALL NOT reject a request because of its size or content (see CM-012 for the transformation limit). |
| PX-012 | THE SYSTEM SHALL add the response header `x-tokli-request-id` unless `observability.response_header` is false. |
| PX-013 | THE SYSTEM SHALL expose `GET /tokli/health` returning status and version without authentication. |
| PX-014 | THE SYSTEM SHALL request `accept-encoding: identity` from the upstream only for transformable endpoints, and SHALL otherwise forward the client's `accept-encoding`. |

Note on PX-014: Tokli needs plain-text responses only where it parses usage. For verbatim routes,
the client's own negotiation is preserved. REQUIRES VERIFICATION: some SDKs send `gzip` and
tolerate identity. E1/E4 confirm this.

## Failure behaviour
See the table in ARCH §6. Credential failures are fail-closed (SPEC 006). Everything else fails to pass-through.

## Observability
Spans: `route`, `upstream` (TTFB, total, status, upstream request-id header). Decisions: `known_endpoint`,
`verbatim_path`, `unknown_prefix`, `upstream_*`, `client_disconnected`.

## Acceptance criteria
- AC-PX-1 (PX-001): default bind is `127.0.0.1`; non-loopback without the flag fails to start.
- AC-PX-2 (PX-002, PX-003): routing table tests incl. `/anthropic/v1/messages/`, `/openai/chat/completions`, `/openai/v1/models`, `/unknown/x`.
- AC-PX-3 (PX-005, PX-006): the fake upstream emits 10 chunks 50 ms apart. The client receives the same bytes, and chunk arrival times track upstream within 20 ms.
- AC-PX-4 (PX-007): 400/401/429/529 JSON errors (stream and non-stream) arrive verbatim.
- AC-PX-5 (PX-008): connect refused → 502 with `source: tokli`.
- AC-PX-6 (PX-009): upstream observes cancellation after a client disconnect.
- AC-PX-7 (PX-010): a stage that raises results in upstream receiving the original bytes.

## Test scenarios
`test_default_bind_is_loopback` · `test_remote_bind_requires_flag` · `test_routing_table` ·
`test_unknown_prefix_returns_tokli_404` · `test_headers_forwarded_except_hop_by_hop` ·
`test_response_bytes_identical` · `test_stream_chunks_identical_and_unbuffered` ·
`test_upstream_errors_relayed_verbatim` · `test_upstream_unreachable_returns_tokli_502` ·
`test_client_disconnect_cancels_upstream` · `test_internal_error_forwards_original` ·
`test_large_body_not_rejected` · `test_request_id_header` · `test_health_endpoint`

## Open questions
- Q2: Does Claude Code accept `ANTHROPIC_BASE_URL` with a path prefix (`/anthropic`)? (E1) Fallback if not: one listener port per provider (config `listeners`).
