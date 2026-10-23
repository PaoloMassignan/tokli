# SPEC 020 — Cache keepalive

Status: Approved for S8l (2026-10-23): KA-001…KA-015, AC-KA-1…AC-KA-12 · Changed by S8l SCR-002 and SCR-004 (approved 2026-10-23): KA-001, AC-KA-1, AC-KA-3; AC-KA-13 is approved for the slice that builds inject mode for Anthropic (S5) · Slice: S8l · Related: SPEC 000 SC-008, SPEC 003 AN-011, SPEC 006 UP-002, SPEC 013 TC-023…TC-025, SPEC 014 OB-014, SPEC 016 UI-015, SPEC 017 "Keys added in S8l", SPEC 019 PR-021, PR-024, ADR 0016, ADR 0017

## Purpose
When a developer pauses for longer than the provider's cache lifetime, the next request writes
the whole conversation prefix to the cache again, at the cache-write price. A keepalive request
sent before the lifetime ends reads the prefix at the cache-read price and restarts its
lifetime, so the developer's return finds the cache warm. Tokli sends keepalive requests only
when the user turns the feature on, and changes nothing in the client's requests.

## Rationale
- On the developer's real traffic, rewrites after pauses longer than an hour were about a third
  of the spend; a simulation of one-hour keepalives up to a 12 h horizon saved about 23 % of the
  spend, net of the keepalives (`slices/S8l/SPEC_REVIEW.md`).
- E12 (`TOKLI_EVIDENCE.md`): a keepalive request that repeats the last request with
  `max_tokens: 1` reads the whole prefix, writes nothing and produces one output token; a return
  more than an hour after the last request and less than an hour after the keepalive was warm,
  and the unpinged control was cold. `max_tokens` is not part of the cache key; the thinking
  settings are kept as sent.
- A five-minute lifetime needs a keepalive every few minutes, and a 12 h pause then costs more
  in keepalives than the rewrite it avoids. The feature applies to one-hour lifetimes.
- A subscription (OAuth) counts usage against limits whose treatment of cache reads is not
  published, and an access token may expire during a pause. OAuth has its own opt-in, and a
  rejected credential stops the keepalive.

## Terminology
- **Kept conversation:** a conversation (key per ADR 0012) for which Tokli holds the last
  forwarded request, to send keepalive requests.
- **Keepalive request (ping):** a request Tokli originates for a kept conversation (KA-004).
- **Prefix size:** the provider-reported `cache_read_input_tokens + cache_creation_input_tokens`
  of a response.
- **Bridged request:** a client request of a kept conversation that arrives more than the cache
  lifetime plus `pruning.resume_margin_s` after the conversation's previous client request,
  after at least one successful ping (KA-007) in between.

## Requirements

| ID | EARS requirement |
|---|---|
| KA-001 | WHILE `keepalive.enabled` is false, THE SYSTEM SHALL keep no conversation and send no keepalive request. `keepalive.enabled` and `keepalive.oauth` are true by default. (S8l SCR-004.) |
| KA-002 | WHEN a client request to Anthropic Messages `POST /v1/messages` completes with a 2xx status and provider usage, AND its own `cache_ttl_s` (SPEC 003 AN-011) is present and at least `keepalive.min_ttl_s`, AND its prefix size is at least `keepalive.min_prefix_tokens`, AND the auth mode is `inject` or its `credential_kind` is `api_key`, or `oauth` with `keepalive.oauth` true, THE SYSTEM SHALL keep its conversation; OTHERWISE THE SYSTEM SHALL record `ineligible(<why>)` (KA-010) in the request's trace and SHALL stop keeping the conversation if it was kept. |
| KA-003 | FOR a kept conversation, THE SYSTEM SHALL hold in memory only the forwarded request body (after compression), the forwarded request headers (after auth, SPEC 006 UP-010), the time the request was sent, its cache lifetime and its prefix size, replacing them at each later client request of the conversation. It SHALL NOT write them to disk, logs, telemetry, traces or API responses (ADR 0016). |
| KA-004 | A keepalive request SHALL be the held body with only `max_tokens` changed: to 1, or, WHEN the body has `thinking` of type `enabled` with `budget_tokens`, to `budget_tokens + 1`. Every other member, including `stream`, `thinking`, `tools`, `system`, `messages` and every `cache_control`, SHALL be kept as held. It SHALL be sent to the same upstream path with the held headers, except that in inject mode the credential SHALL be set from the configured source at sending time (UP-003). |
| KA-005 | THE SYSTEM SHALL send the first keepalive request of a kept conversation `keepalive.lead_s` seconds before the cache lifetime ends after the last client request, and each next one `keepalive.lead_s` seconds before the lifetime ends after the previous successful ping, AS LONG AS the ping would be sent no later than `keepalive.horizon_s` seconds after the last client request; WHEN the next ping would be later, THE SYSTEM SHALL stop keeping the conversation with the reason `horizon`. |
| KA-006 | IF a ping is due but the cache lifetime since the last client request or successful ping has already passed (for example after the machine slept), THEN THE SYSTEM SHALL NOT send it, and SHALL stop keeping the conversation with the reason `expired`. |
| KA-007 | A ping SHALL be successful WHEN its status is 2xx and its provider-reported cache write is at most 5 % of the held prefix size. WHEN a ping's status is 2xx and its cache write is larger, THE SYSTEM SHALL stop keeping the conversation with the reason `cache_missed`. |
| KA-008 | IF a ping receives status 401 or 403, THEN THE SYSTEM SHALL stop keeping the conversation with the reason `auth_rejected`; IF it receives any other non-2xx status, cannot reach the upstream or times out, THEN THE SYSTEM SHALL stop keeping it with the reason `upstream_error`. THE SYSTEM SHALL NOT retry a ping. |
| KA-009 | THE SYSTEM SHALL keep at most `keepalive.max_conversations` conversations; WHEN a further conversation becomes kept, THE SYSTEM SHALL stop keeping the one whose last client request is oldest, with the reason `evicted`. |
| KA-010 | WHEN THE SYSTEM stops keeping a conversation, it SHALL drop everything held for it (KA-003) and SHALL record one reason from the closed set `horizon`, `expired`, `cache_missed`, `auth_rejected`, `upstream_error`, `evicted`, `disabled`, `shutdown`, or `ineligible(<why>)` with `<why>` ∈ `upstream_status`, `no_usage`, `short_ttl`, `too_small`, `credential_kind`, `oauth_not_enabled`. |
| KA-011 | WHEN `keepalive.enabled` becomes false at run time, THE SYSTEM SHALL stop keeping every conversation with the reason `disabled`; WHEN Tokli stops, with the reason `shutdown`. No ping SHALL be sent after either. |
| KA-012 | WHILE a client request of a kept conversation is in flight, THE SYSTEM SHALL NOT send a ping for it. |
| KA-013 | A successful ping SHALL count as the conversation's last request for SPEC 019 PR-021 (its time only; the cache lifetime and the pruned call ids stay those of the last client request). |
| KA-014 | THE scheduling and sending of pings SHALL run on the server's event loop, SHALL NOT delay the relaying of client requests (SPEC 002 PX-015), and SHALL use the upstream's configured timeouts (UP-009). |
| KA-015 | THE response of a ping SHALL be read only for its status, usage and `stop_reason` (with the bounded usage parser, SPEC 003 AN-005, AN-006, AN-009) and SHALL NOT be relayed, stored or logged. |

## Acceptance criteria
- AC-KA-1 (KA-001): with `keepalive.enabled` false, after a cached 1 h request and 2 h of fake
  time, the fake upstream received no request beyond the client's; with the default
  configuration and an eligible request with an OAuth credential, a ping is sent. (S8l SCR-004.)
- AC-KA-2 (KA-002, KA-010): with the feature on, a request with a 5 min marker, one with a
  prefix of 19,999 tokens, one with an OAuth credential and `keepalive.oauth` false, and one
  answered 429 are each not kept, with `ineligible(short_ttl)`, `ineligible(too_small)`,
  `ineligible(oauth_not_enabled)` and `ineligible(upstream_status)` in their traces.
- AC-KA-3 (KA-004): for a streamed request with adaptive thinking, two `cache_control` markers
  and `max_tokens: 32000`, the ping's JSON equals the forwarded JSON except `max_tokens: 1`, and
  its headers equal the forwarded headers; with `thinking: {type: enabled, budget_tokens: 2048}`
  it has `max_tokens: 2049`. (S8l SCR-002: the inject-mode sentence moved to AC-KA-13.)
- AC-KA-4 (KA-005): with a 1 h lifetime, `lead_s` 300 and a 12 h horizon, a pause of 12 h gives
  pings at 55 min, 1 h 50 min, … and none later than 12 h after the client request: 13 pings.
- AC-KA-5 (KA-006): a clock that jumps 2 h before a due ping gives no ping and the reason
  `expired`.
- AC-KA-6 (KA-007, KA-008): a ping answered with a cache write of 60 % of the prefix stops the
  conversation with `cache_missed`; one answered 401 with `auth_rejected`; one answered 529, and
  one that times out, with `upstream_error`; none is retried.
- AC-KA-7 (KA-009): with `max_conversations` 2, a third kept conversation evicts the oldest with
  `evicted`.
- AC-KA-8 (KA-011): turning the feature off through `PATCH /tokli/api/config` stops every kept
  conversation with `disabled` and no ping follows; stopping the server records `shutdown`.
- AC-KA-9 (KA-012): a ping due while a client request of the same conversation is in flight is
  not sent; the scheduling restarts from that request.
- AC-KA-10 (KA-013): with `edit_args_on_resume` on, a client request 1 h 50 min after the
  previous one, with a successful ping at 55 min, is not a resume, and its forwarded body is
  byte-identical in the pruned calls to the previous one.
- AC-KA-11 (KA-003, KA-015): canary credentials and canary content in a kept conversation never
  appear in logs, the database, traces or API responses, and nothing is written in the data
  directory beyond the telemetry rows.
- AC-KA-12 (KA-014): a ping whose fake upstream answers after 5 s does not delay a concurrent
  client request.
- AC-KA-13 (KA-002, KA-004; from the slice that builds inject mode for Anthropic, S5): in inject
  mode a conversation is kept, and its ping carries the key read from the configured source at
  sending time, not the client's header. (S8l SCR-002.)

## Test scenarios
`test_keepalive_off_sends_nothing` · `test_keepalive_on_by_default` · `test_keepalive_eligibility_reasons` ·
`test_ping_body_changes_only_max_tokens` · `test_ping_max_tokens_above_thinking_budget` ·
`test_ping_inject_mode_reads_key_at_send_time` · `test_ping_schedule_until_horizon` ·
`test_ping_not_sent_after_clock_jump` · `test_ping_cache_missed_stops` ·
`test_ping_auth_rejected_stops` · `test_ping_upstream_error_stops_without_retry` ·
`test_keepalive_evicts_oldest` · `test_keepalive_disabled_at_run_time` ·
`test_keepalive_shutdown_drops_state` · `test_no_ping_while_client_request_in_flight` ·
`test_successful_ping_prevents_resume` · `test_keepalive_never_persists_content_or_credentials` ·
`test_ping_does_not_delay_client_requests`
