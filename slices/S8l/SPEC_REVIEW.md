# S8l — Spec review

**Slice scope** (`TOKLI_ROADMAP.md`, S8l, requested 2026-10-22): keep the provider's prompt cache
warm across the developer's pauses with keepalive requests, when that costs less than the full
rewrite the pause would cause.

**Specs in scope** (requirement text written after E12, 2026-10-22):
- SPEC 020 (new): KA-001…KA-015, AC-KA-1…AC-KA-12;
- SPEC 000 / `TOKLI_SCOPE.md`: SC-008, AC-SC-6, the scope row;
- SPEC 006: UP-002, and SPEC 019: PR-021, PR-024, changed by `SCR-001-keepalive-touches-approved-requirements.md`;
- SPEC 013: TC-023…TC-025, AC-TC-19…AC-TC-21 (schema v6, ADR 0017); TC-013, TC-015 by SCR-001;
- SPEC 014: OB-014, AC-OB-8, and the "Keepalive" reason codes in `TOKLI_OBSERVABILITY.md` §4;
- SPEC 017: "Keys added in S8l"; CF-009 by SCR-001;
- SPEC 016: UI-015, AC-UI-6;
- ADR 0016 (timer-driven upstream requests, held requests).

SPEC 002 and SPEC 003 need no change: a ping goes through the existing upstream client and
usage parser, and is not a client request.

**Out of scope:** OpenAI protocols (their caching is automatic and has no client-set lifetime);
any change to request content.

## Evidence gathered in READ (2026-10-22, counters only, with the human's consent)

**Simulation on the real pause timeline** (14 days, 24 sessions, 7,140 requests of the main model,
exact usage, `claude-opus-5-5` list prices from the shipped price book). One ping every 55
minutes (cache lifetime 1 h − 5 min) during a pause, until the developer returns or a horizon
passes. A ping costs the last request's prefix at the cache-read price. A pause bridged by pings
saves the next request's rewrite of that prefix (write price − read price).

- **Spend:** about $635 a week at list prices. Cache writes after pauses longer than 1 h are about
  $210 a week, over about 86 pauses a week.
- **Pauses by length** (14 days): 1–2 h: 80 · 2–4 h: 37 · 4–8 h: 27 · 8–16 h: 19 · 16–24 h: 2 ·
  24–72 h: 6 · over 72 h: 2. Pauses at the end of a session never end.

| Horizon | Pings/week | Ping cost $/week | Saved $/week | **Net $/week** | Bridged pauses | Wasted pings |
|---|---|---|---|---|---|---|
| 1 h | 98 | 7.03 | 79.49 | 72.46 | 78 | 119 |
| 4 h | 248 | 17.76 | 138.81 | 121.05 | 122 | 300 |
| 8 h | 386 | 27.53 | 160.65 | 133.12 | 144 | 424 |
| **12 h** | 494 | 35.67 | 182.20 | **146.53** | 160 | 481 |
| 24 h | 712 | 51.83 | 190.85 | 139.02 | 166 | 806 |
| 48 h | 1,096 | 78.16 | 196.89 | 118.73 | 169 | 1,456 |

The net saving at a 12 h horizon is about 23 % of the spend. Every compressor so far saved
1–4 %.

**Checks:**
- **Local midnight does not change the prefix.** 13 pairs of requests less than 1 h apart across
  local midnight: none was a full rewrite. On the same day: 51 of 13,179 (0.4 %).
- **A cache hit refreshes the lifetime.** Long sessions with steady requests show no rewrites at
  the hour marks (0.4 % full rewrites between requests less than 1 h apart).
- **The developer's Claude Code uses a subscription (OAuth).** The proxy telemetry shows 353 of
  387 requests with `oauth`. For a subscription the dollars are list-price equivalents: the
  effect is on usage limits, and how those limits count cache reads and writes is not published.

**Not known before E12** (answered by E12, 2026-10-22, except the second point):
- whether a keepalive request can be shaped so that it reads the whole cached prefix and costs
  almost no output (thinking settings are part of the cache key, so they cannot be dropped);
- whether an OAuth access token held from the last request is still valid hours later;
- whether the provider treats such requests as ordinary use.

## 1. Ambiguities

- **A1. "The prefix" a ping must keep.** Proposed reading: the last request of the conversation
  as Tokli forwarded it, byte for byte up to its last cache breakpoint. A ping that differs before
  that breakpoint writes a new cache entry instead of reading the old one.
- **A2. "Pause".** Proposed reading: no request in a conversation (S8i key) for longer than the
  ping interval. The S8i store already holds the time and the cache lifetime of the last request.

## 2. Contradictions

- **C1. `TOKLI_SCOPE.md`:** "any capability not listed under In scope" is a non-goal. A keepalive
  is not token reduction, and Tokli has so far never originated a request. Product question P1.
- **C2. `TOKLI_SCOPE.md` guardrails, and SPEC 006:** Tokli forwards credentials and never keeps
  them. A keepalive must keep the last request's credentials, and its body (prompt content), in
  memory for up to the horizon. Product question P5.

## 3. Missing behaviour

- **M1. The keepalive request** (shape, `max_tokens`, `stream`, thinking settings): from E12,
  now KA-004.
- **M2. Failure handling:** an error, a 401 (expired token) or a 429 stops the keepalive for that
  conversation, and nothing is retried.
- **M3. Concurrency:** several conversations at once (parallel sessions), bounded by a maximum
  number of kept conversations.
- **M4. Stopping:** when the conversation sends a real request, at the horizon, when Tokli stops,
  or when the configuration turns the feature off.
- **M5. Accounting:** a ping is a request with its own usage and cost. The saving is
  counterfactual: a bridged pause saves the rewrite it avoided, about the prefix × (write − read).

## 4. Portability concerns

- A background scheduler inside the server's event loop: no OS timers, no threads beyond the
  existing ones.
- A laptop that sleeps stops the pings. The next ping then comes late and finds a cold cache. That
  costs one useless ping, and nothing breaks.

## 5. Observability requirements

- A span per ping (`keepalive`), with the conversation's age, the prefix size and the outcome.
- Telemetry rows for pings as their own outcome, so they never mix with real requests.
- Reason codes when a keepalive stops: `client_returned`, `horizon`, `upstream_error`,
  `auth_rejected`, `disabled`.

## 6. Architectural risks

- **A new dependency direction:** the app layer starts upstream calls on a timer. That needs an
  ADR (CLAUDE.md §6).
- **Memory holds prompt content and credentials for hours.** It is memory only, bounded, and
  dropped at shutdown, but it is new (ADR, P5).
- **The seam:** one scheduler with one concrete protocol (Anthropic). No abstraction until a
  second protocol needs it (§5).

## 7. Product questions (for the human)

- **P1. Scope.** May Tokli originate keepalive requests (a SPEC 000 / `TOKLI_SCOPE.md` change),
  off by default?
  - **Recommended: yes, off by default.** It changes no content, so it carries no refusal risk.
    The simulation shows the largest saving measured so far.
- **P2. E12 before any requirement text.** A small paid experiment with real credentials, to fix
  the ping's shape and confirm the cache behaviour:
  - (a) a ping on a cached conversation reads the whole prefix and writes almost nothing;
  - (b) a real request more than 1 h after the last real request, but less than 1 h after a ping,
    is warm;
  - (c) the ping's output cost with Claude Code's thinking settings;
  - (d) the same with an OAuth token held for several hours.
  - **Recommended: yes.** Estimated cost under $5 at list prices, and about 3 hours of wall time.
    It runs with your consent, through your own credentials (as E10(f), or through a running
    Tokli for OAuth).
- **P3. Subscription (OAuth).** Your traffic uses a subscription, where the saving is on usage
  limits and not on money, and how those limits count pings is unknown.
  - **(a)** Keepalive for API keys only.
  - **(b)** API keys, and OAuth behind its own explicit opt-in.
  - **Recommended: (b),** only if E12 (d) works. Otherwise the feature does nothing for your
    traffic.
- **P4. Defaults.**
  - Horizon 12 h (the best net in the simulation).
  - Interval: cache lifetime − 5 min.
  - Only conversations with a prefix of at least 20,000 tokens.
  - At most 8 conversations kept.
  - **Recommended: as listed,** all as configuration keys.
- **P5. What Tokli keeps in memory.** The last forwarded body and the credential headers of each
  kept conversation, memory only, until the horizon, never on disk, never logged.
  - **Recommended: yes,** with an ADR. It is the only way to send a ping that matches the prefix.
- **P6. Dashboard.** **Recommended:** show pings, their cost, the bridged pauses and the
  estimated net saving, clearly marked as an estimate.

## 8. Implementation decisions (Claude)

- **D1. One new spec (SPEC 020)** holds the keepalive's behaviour; the other specs get only what
  belongs to them (telemetry, observability, dashboard, keys, scope). SPEC 002 and SPEC 003 are
  unchanged.
- **D2. The held body is the forwarded one,** after compression, because that is what the
  provider cached. A ping never runs the pipeline again (ADR 0016).
- **D3. `stream` is kept as sent.** E12 changed only `max_tokens`; a ping of a streamed request
  streams, and its stream is read by the existing usage parser and discarded (KA-015). No
  untested variation of the body.
- **D4. A late ping is not sent** (KA-006): after the machine sleeps the cache is probably gone,
  and a ping would pay the full write the feature exists to avoid.
- **D5. The prefix size is the provider's** (`cache_read + cache_creation` of the last response),
  so `keepalive.min_prefix_tokens` is in provider tokens and needs no estimate.
- **D6. Pings are `RequestRecord` rows with `outcome: keepalive`** (ADR 0017) rather than a new
  table, and every existing aggregate leaves them out (SCR-001).
- **D7. The saving is priced at query time** from the bridged request's cache read (TC-025), like
  every other cost (TC-008).
- **D8. A ping is an asyncio task per kept conversation** on the server's loop, on the wall clock
  (ADR 0016).

## 9. Test plan

| Requirement / AC | Tests |
|---|---|
| KA-001, AC-KA-1; SC-008, AC-SC-6 | `test_keepalive_off_by_default_sends_nothing`, `test_no_originated_requests_by_default` |
| KA-002, KA-010, AC-KA-2 | `test_keepalive_eligibility_reasons` |
| KA-004, AC-KA-3 | `test_ping_body_changes_only_max_tokens`, `test_ping_max_tokens_above_thinking_budget`, `test_ping_inject_mode_reads_key_at_send_time` |
| KA-005, AC-KA-4 | `test_ping_schedule_until_horizon` |
| KA-006, AC-KA-5 | `test_ping_not_sent_after_clock_jump` |
| KA-007, KA-008, AC-KA-6 | `test_ping_cache_missed_stops`, `test_ping_auth_rejected_stops`, `test_ping_upstream_error_stops_without_retry` |
| KA-009, AC-KA-7 | `test_keepalive_evicts_oldest` |
| KA-011, AC-KA-8 | `test_keepalive_disabled_at_run_time`, `test_keepalive_shutdown_drops_state` |
| KA-012, AC-KA-9 | `test_no_ping_while_client_request_in_flight` |
| KA-013, PR-021, PR-024 (SCR-001), AC-KA-10 | `test_successful_ping_prevents_resume` |
| KA-003, KA-015, UP-002 (SCR-001), AC-KA-11 | `test_keepalive_never_persists_content_or_credentials` |
| KA-014, AC-KA-12 | `test_ping_does_not_delay_client_requests` |
| TC-023, AC-TC-19 | `test_keepalive_rows_persisted` |
| TC-024, TC-025, TC-013, TC-015 (SCR-001), AC-TC-20 | `test_keepalive_summary_hand_computed`, `test_keepalive_rows_excluded_from_totals` |
| ADR 0017, AC-TC-21 | `test_schema_migration_v5_to_v6` |
| OB-014, AC-OB-8 | `test_keepalive_trace_and_log_line` |
| UI-015, CF-009 (SCR-001), AC-UI-6 | `test_ui_keepalive_card_and_toggles` (browser job), keys in `test_ui_override_only_when_not_pinned` |
| Keys added in S8l | the parametrised `test_env_overrides_file_for_every_key` |

Real-traffic check (not a gate): with the human's consent and the feature opted in, a day of real
use, with the keepalive block and the stop reasons recorded in the completion report.

## Answers (2026-10-22)

- **The human's words:** "It all seems sensible" (translated from Italian), for P1–P6 as
  recommended.
- **E12 (d), an OAuth token held for hours,** is not tested by a script, because that would read
  Claude Code's stored credentials. It is checked in real use with the keepalive opted in: a
  rejected token stops the keepalive with the reason `auth_rejected`. E12 (a)–(c) run with the
  human's API key: `evals/experiments/e12_keepalive.py` (dry run: about $1.23 for the one-hour
  run, $0.83 for the five-minute check).

## E12 result (2026-10-22)

**Go** (`TOKLI_EVIDENCE.md`, E12): a ping with `max_tokens: 1` read the whole prefix (63,915
tokens), wrote nothing, and produced one output token, with and without adaptive thinking; the
pinged returns at 110 min were warm, the control was cold. A ping cost about $0.013; the rewrite
it avoided about $0.50. The run cost about $2.11.

## Questions raised by the requirement text (for Gate 1)

- **P7. Five-minute lifetimes.** `keepalive.min_ttl_s` 3600 keeps the feature to one-hour
  markers: with 5 min markers a 12 h pause needs about 150 pings, which at the read price cost
  more than the one rewrite they avoid. **Recommended: as written.** (Claude Code sends 1 h
  markers on this machine: 2.32 M of 2.53 M cache-write tokens, S8i review.)
- **P8. The saving estimate** (TC-025) counts each bridged request's cache read at the
  write − read price. It assumes the developer would have come back anyway, which is true by
  construction for a bridged request. **Recommended: as written,** labelled an estimate.
- **P9. SCR-001** changes six approved requirements (UP-002, PR-021, PR-024, TC-013, TC-015,
  CF-009), with no change of behaviour while the feature is off. **Recommended: approve.**

**Gate 1 record:** approved 2026-10-23. The human's words: "I approve" (translated from Italian), for
the requirement text, P7–P9 as recommended and SCR-001. Spec delta: `git diff` of `specs/000…`, `013`, `014`, `016`, `017`,
`TOKLI_SCOPE.md`, `TOKLI_OBSERVABILITY.md`, `TOKLI_ARCHITECTURE.md`, the new `specs/020-cache-keepalive/spec.md`,
`SCR-001-keepalive-touches-approved-requirements.md`, ADR 0016 and ADR 0017.
